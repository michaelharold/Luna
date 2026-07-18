# speech_to_text.py
"""
speech_to_text.py — Vosk STT with strict mic blocking + robust device handling.

Improvements over the old version:
  • Persistent input stream (opened once, not per-listen) — lower latency,
    no device re-open glitches between turns.
  • Auto-detects the mic's native sample rate and resamples to 16 kHz for
    Vosk with numpy interpolation — works with 16k/32k/44.1k/48k mics.
  • Graceful "microphone not found" handling: Luna keeps running (face,
    vision, gestures) and retries the mic every 5 seconds instead of crashing.
  • Multiple wake words (WAKE_WORDS in config), matched on word boundaries.
  • Respects state.mic_unblock_time — never listens while Luna speaks.
"""

import queue
import json
import time
import difflib
import threading
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

from shared_state import state
from config import (
    WAKE_WORDS,
    AUDIO_INPUT_DEVICE,
    VOSK_MODEL_PATH,
    MIC_SAMPLE_RATE,
    VOSK_SAMPLE_RATE,
    CONVO_TIMEOUT,
    POST_SPEAK_DELAY,
    DOUBLE_FLUSH,
    MIC_ENERGY_THRESHOLD,
    MIC_GATE_FACTOR,
    MIC_GATE_MAX,
    STT_CONFIDENCE_THRESHOLD,
    STT_MIN_UTTERANCE_CHARS,
    STT_DEBUG_AUDIO,
    WAKE_CONFIDENCE_THRESHOLD,
    WAKE_FUZZY_RATIO,
    REQUIRE_FACE_TO_TALK,
    FACE_RECENT_SECS,
)

_model = Model(VOSK_MODEL_PATH)
_q     = queue.Queue(maxsize=50)   # bounded — audio can't pile up unbounded

_mic_rate     = None    # actual sample rate the stream runs at
_mic_ok       = False
_stream       = None
_help_printed = False

# Sentinel returned by listen() when a wake word was heard with no question
# attached ("Luna!") — main.py answers with a short acknowledgement.
WAKE_ACK = "__WAKE_ACK__"


# ── Device + sample rate detection ────────────────────────────────────────────

def _pick_input_device():
    """Return (device_index_or_None, sample_rate) or (None, None) if no mic."""
    if AUDIO_INPUT_DEVICE is not None:
        try:
            dev = sd.query_devices(AUDIO_INPUT_DEVICE)
            if dev["max_input_channels"] > 0:
                rate = MIC_SAMPLE_RATE or int(dev["default_samplerate"])
                print(f"[STT] Using configured device {AUDIO_INPUT_DEVICE}: "
                      f"{dev['name']} @ {rate} Hz")
                return AUDIO_INPUT_DEVICE, rate
            print(f"[STT] Configured device {AUDIO_INPUT_DEVICE} has no "
                  f"input channels — falling back to auto-detect")
        except Exception as e:
            print(f"[STT] Configured device {AUDIO_INPUT_DEVICE} error: {e} "
                  f"— falling back to auto-detect")

    # auto-detect: prefer the system default input, then any input device
    candidates = []
    try:
        default_in = sd.default.device[0]
        if default_in is not None and default_in >= 0:
            candidates.append(default_in)
    except Exception:
        pass

    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[STT] Could not query audio devices: {e}")
        return None, None

    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and i not in candidates:
            candidates.append(i)

    for i in candidates:
        try:
            dev  = sd.query_devices(i)
            rate = MIC_SAMPLE_RATE or int(dev["default_samplerate"])
            # verify the device actually accepts this configuration
            sd.check_input_settings(device=i, samplerate=rate,
                                    channels=1, dtype="int16")
            print(f"[STT] Auto-detected input device {i}: "
                  f"{dev['name']} @ {rate} Hz")
            return i, rate
        except Exception:
            # try the device's own default rate before giving up on it
            try:
                dev  = sd.query_devices(i)
                rate = int(dev["default_samplerate"])
                sd.check_input_settings(device=i, samplerate=rate,
                                        channels=1, dtype="int16")
                print(f"[STT] Auto-detected input device {i}: "
                      f"{dev['name']} @ {rate} Hz (device default)")
                return i, rate
            except Exception:
                continue

    return None, None


def _print_mic_help():
    global _help_printed
    if _help_printed:
        return
    _help_printed = True
    print("=" * 60)
    print("[STT] NO MICROPHONE FOUND — voice input disabled.")
    print("[STT] Luna keeps running (face + vision + gestures).")
    print("[STT] Will retry the microphone every 5 seconds.")
    print("[STT] To fix, see the Troubleshooting section in README.md:")
    print("[STT]   python3 -c \"import sounddevice as sd; print(sd.query_devices())\"")
    print("[STT]   then set AUDIO_INPUT_DEVICE in config.py")
    print("=" * 60)


# ── Persistent stream (background thread) ─────────────────────────────────────

def _callback(indata, frames, time_info, status):
    try:
        _q.put_nowait(bytes(indata))
    except queue.Full:
        pass   # drop oldest-style: consumer is behind, losing a block is fine


def _stream_keeper():
    """Keeps a mic stream open forever; retries every 5 s if the mic vanishes."""
    global _stream, _mic_ok, _mic_rate, _help_printed

    while True:
        if _mic_ok:
            time.sleep(1.0)
            continue

        device, rate = _pick_input_device()
        if device is None and rate is None:
            _print_mic_help()
            with state.lock:
                state.mic_ok = False
            time.sleep(5.0)
            continue

        try:
            stream = sd.RawInputStream(
                samplerate=rate,
                blocksize=int(rate * 0.25),   # 250 ms blocks
                dtype="int16",
                channels=1,
                callback=_callback,
                device=device,
            )
            stream.start()
            _stream       = stream
            _mic_rate     = rate
            _mic_ok       = True
            _help_printed = False
            with state.lock:
                state.mic_ok = True
            print(f"[STT] Microphone stream running @ {rate} Hz")
        except Exception as e:
            print(f"[STT] Could not open microphone: {e} — retrying in 5s")
            _print_mic_help()
            with state.lock:
                state.mic_ok = False
            time.sleep(5.0)


threading.Thread(target=_stream_keeper, daemon=True, name="mic").start()


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _resample_to_16k(raw_bytes):
    """Resample int16 mono audio from _mic_rate to VOSK_SAMPLE_RATE."""
    audio = np.frombuffer(raw_bytes, dtype=np.int16)
    if _mic_rate == VOSK_SAMPLE_RATE or _mic_rate is None:
        return raw_bytes
    ratio   = VOSK_SAMPLE_RATE / _mic_rate
    n_out   = int(len(audio) * ratio)
    if n_out == 0:
        return b""
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out,      endpoint=False)
    resampled = np.interp(x_new, x_old, audio).astype(np.int16)
    return resampled.tobytes()


def _block_rms(raw_bytes):
    """RMS loudness of an int16 audio block (0–32767 scale)."""
    audio = np.frombuffer(raw_bytes, dtype=np.int16)
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


# ── Adaptive noise floor ──────────────────────────────────────────────────────
# Tracks ambient room loudness so the energy gate follows the environment:
# rises fast when the room gets quieter, creeps up slowly through loud stretches
# (so bursts of real speech barely move it, but a persistently noisy room lifts
# the gate above its noise). Classic asymmetric EMA.
_noise_floor = 150.0


def _update_noise_floor(rms):
    global _noise_floor
    alpha = 0.10 if rms < _noise_floor else 0.02
    _noise_floor += alpha * (rms - _noise_floor)


def _energy_gate():
    """Current RMS gate: noise_floor × factor, clamped to [threshold, max]."""
    return min(max(MIC_ENERGY_THRESHOLD, _noise_floor * MIC_GATE_FACTOR),
               MIC_GATE_MAX)


def _avg_confidence(result):
    """Mean Vosk per-word confidence for a final result (1.0 if unavailable)."""
    words = result.get("result", [])
    if not words:
        return 1.0   # no per-word info — don't reject on confidence alone
    return sum(w.get("conf", 1.0) for w in words) / len(words)


def _flush_queue():
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break


def _find_wake_word(words):
    """Locate a wake word/phrase in the token list.

    Returns (start_index, n_tokens, exact) or None. Longest wake phrase is
    tried first, so "hey luna ..." strips the whole phrase instead of leaving
    a stray "hey" in the question. If no exact match, single-word wake words
    (≥ 4 chars) are matched fuzzily so Vosk near-misses on poor capture
    (e.g. "lunar" for "luna") still summon her — the caller applies a stricter
    confidence bar to fuzzy hits so this never fires from noise."""
    for wake in sorted(WAKE_WORDS, key=lambda w: -len(w.split())):
        wake_parts = wake.split()
        n = len(wake_parts)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == wake_parts:
                return i, n, True

    for wake in WAKE_WORDS:
        if " " in wake or len(wake) < 4:
            continue
        for i, w in enumerate(words):
            if (len(w) >= 4 and
                    difflib.SequenceMatcher(None, w, wake).ratio()
                    >= WAKE_FUZZY_RATIO):
                return i, 1, False
    return None


def _wake_confidence(result, words, start, n):
    """Mean Vosk confidence of just the wake tokens (1.0 if unavailable)."""
    infos = result.get("result", [])
    if len(infos) != len(words):   # tokenisation mismatch — don't guess
        return 1.0
    confs = [w.get("conf", 1.0) for w in infos[start:start + n]]
    return sum(confs) / len(confs) if confs else 1.0


# ── Recognizer — created once, Reset() between turns (cheap on the Pi) ────────
_rec = None


def _get_recognizer():
    global _rec
    if _rec is None:
        _rec = KaldiRecognizer(_model, VOSK_SAMPLE_RATE)
        _rec.SetWords(True)   # emit per-word confidence for the noise gate
    else:
        _rec.Reset()
    return _rec


def _addressed_to_luna():
    """True when the speech we just heard was plausibly directed AT Luna.

    Uses the camera: someone talking to Luna faces her, so a face must have
    been seen within FACE_RECENT_SECS. People chatting with each other in
    front of Luna (any language) usually aren't facing her — their speech is
    ignored instead of answered. Fails open when the camera is unavailable
    (mic-only setups keep working) or the gate is disabled in config."""
    if not REQUIRE_FACE_TO_TALK:
        return True
    with state.lock:
        camera_ok = state.camera_ok
        last_face = state.last_face_time
    if not camera_ok:
        return True
    return (time.time() - last_face) <= FACE_RECENT_SECS


def _expire_conversation():
    """Conversation window ran out — back to wake-word mode.
    Stamps convo_expired_time so the face can play its subtle 'rest' cue."""
    print("[STT] Conversation timed out — waiting for wake word")
    with state.lock:
        state.conversation_active = False
        state.convo_expired_time  = time.time()
        state.listening           = False


# ── Main listen ───────────────────────────────────────────────────────────────

def listen():
    """
    Waits until the mic is allowed (Luna not speaking, echo-guard passed),
    then listens. In conversation mode no wake word is needed until timeout.
    Returns WAKE_ACK when a wake word was heard alone, the recognised text
    when actionable, "" otherwise.
    """

    # no mic? — don't spin, just idle politely (keeper thread is retrying)
    if not _mic_ok:
        time.sleep(1.0)
        return ""

    # ── Wait until mic is allowed ─────────────────────────────────────────────
    was_blocked = False
    while True:
        with state.lock:
            speaking     = state.speaking
            unblock_time = state.mic_unblock_time
        now = time.time()

        if speaking or now < unblock_time:
            was_blocked = True
            remaining = unblock_time - now
            time.sleep(min(0.1, remaining) if remaining > 0 else 0.05)
            continue
        break

    # Only pay the settle delay when Luna actually just spoke — the old code
    # added POST_SPEAK_DELAY to EVERY listen cycle, even silent ones.
    if was_blocked:
        _flush_queue()
        time.sleep(POST_SPEAK_DELAY)
        if DOUBLE_FLUSH:
            _flush_queue()

    rec = _get_recognizer()

    # check conversation timeout
    with state.lock:
        active        = state.conversation_active
        last_activity = state.last_activity_time

    if active and (time.time() - last_activity) > CONVO_TIMEOUT:
        _expire_conversation()
        active = False

    # "listening" (blue pulse on the face) means attentive conversation mode;
    # passively waiting for a wake word stays visually idle
    with state.lock:
        state.listening = active
        state.luna_mode = "listening" if active else "idle"

    utt_peak_rms = 0.0   # loudest block in the utterance being accumulated

    while True:
        try:
            data = _q.get(timeout=0.5)
        except queue.Empty:
            # mic may have vanished mid-listen
            if not _mic_ok:
                with state.lock:
                    state.listening = False
                    state.luna_mode = "idle"
                return ""
            # conversation window can also run out mid-silence
            if active and (time.time() - last_activity) > CONVO_TIMEOUT:
                _expire_conversation()
                active = False
                with state.lock:
                    state.luna_mode = "idle"
            continue

        # if Luna started speaking, abort this listen (mic gets flushed after)
        with state.lock:
            if state.speaking:
                state.listening = False
                state.luna_mode = "idle"
                return ""

        data = _resample_to_16k(data)
        if not data:
            continue

        # Energy gate (VAD): silence out ambient-level blocks so Vosk never
        # transcribes background noise into words. The gate adapts to the
        # room's noise floor (see _update_noise_floor) — rising in noisy rooms,
        # falling in quiet ones. Gated blocks are fed as digital silence so
        # utterances still get clean pauses/endpoints.
        rms = _block_rms(data)
        _update_noise_floor(rms)
        utt_peak_rms = max(utt_peak_rms, rms)
        if rms < _energy_gate():
            data = bytes(len(data))

        if rec.AcceptWaveform(data):
            result   = json.loads(rec.Result())
            text     = result.get("text", "").strip()
            peak_rms = utt_peak_rms
            utt_peak_rms = 0.0   # reset for the next utterance

            with state.lock:
                state.listening  = False
                state.luna_mode  = "processing"
                state.heard_text = text

            if not text:
                # silence chunk — also the spot to notice a timed-out window
                if active and (time.time() - last_activity) > CONVO_TIMEOUT:
                    _expire_conversation()
                    active = False
                with state.lock:
                    state.luna_mode = "idle" if not active else "listening"
                    state.listening = active
                continue   # keep listening — don't restart the whole cycle

            words   = text.split()
            wake    = _find_wake_word(words)
            cleaned = None

            # A wake word only counts when the wake tokens THEMSELVES were
            # heard confidently — so noise hallucinated as "luna" never wakes
            # her, but a clearly spoken wake word still cuts through a noisy
            # room without needing the rest of the phrase to be clean.
            # Fuzzy (misheard) wake words get a stricter bar than exact ones.
            if wake is not None:
                start, n, exact = wake
                wake_conf = _wake_confidence(result, words, start, n)
                need = (WAKE_CONFIDENCE_THRESHOLD if exact
                        else max(WAKE_CONFIDENCE_THRESHOLD,
                                 STT_CONFIDENCE_THRESHOLD))
                if wake_conf >= need:
                    cleaned = " ".join(words[:start] + words[start + n:]).strip()
                else:
                    if STT_DEBUG_AUDIO:
                        print(f"[STT] Wake ignored (conf {wake_conf:.2f} < "
                              f"{need:.2f}): \"{text}\"")
                    wake = None

            # Noise gates for everything that isn't a confident wake — must
            # look like real, confident, addressed speech before it reaches
            # the brain, so hallucinated noise-words are never answered.
            if cleaned is None:
                conf = _avg_confidence(result)
                if STT_DEBUG_AUDIO:
                    print(f"[STT] heard=\"{text}\" conf={conf:.2f} "
                          f"peak_rms={peak_rms:.0f} gate={_energy_gate():.0f}")
                if (conf < STT_CONFIDENCE_THRESHOLD
                        or len(text) < STT_MIN_UTTERANCE_CHARS):
                    print(f"[STT] Dropped (noise): \"{text}\" conf={conf:.2f}")
                    with state.lock:
                        state.luna_mode = "listening" if active else "idle"
                        state.listening = active
                    continue

            print(f"[Luna heard] {text}")

            if cleaned is not None:
                # Face gate applies to wake words too: "hello" said between
                # two people greeting each other shouldn't wake Luna. Someone
                # summoning her is in front of her camera (gate auto-disables
                # when no camera is available).
                if not _addressed_to_luna():
                    print(f"[STT] Wake ignored (nobody facing me): \"{text}\"")
                    with state.lock:
                        state.luna_mode = "listening" if active else "idle"
                        state.listening = active
                    continue
                print("[STT] Wake word — conversation active")
                with state.lock:
                    state.conversation_active = True
                    state.last_activity_time  = time.time()
                return cleaned if cleaned else WAKE_ACK

            if active:
                # Addressed-speech gate: inside the conversation window, only
                # answer speech from someone actually facing Luna — people
                # talking among themselves in the room (any language) are
                # ignored, and their chatter doesn't keep the window open.
                if not _addressed_to_luna():
                    print(f"[STT] Ignored (nobody facing me): \"{text}\"")
                    with state.lock:
                        state.luna_mode = "listening"
                        state.listening = True
                    continue
                with state.lock:
                    state.last_activity_time = time.time()
                return text

            with state.lock:
                state.luna_mode = "idle"
            return ""

        partial = json.loads(rec.PartialResult()).get("partial", "")
        if partial:
            with state.lock:
                state.heard_text = partial
