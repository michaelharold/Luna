"""
piper_tts.py — Piper neural TTS for Luna.

Low-latency + lip-sync:
  Instead of rendering the whole sentence to a wav and only then playing it
  (which left the lips flapping for several silent seconds on the Pi while
  Piper synthesised), we STREAM Piper's raw audio straight into the player, so
  playback begins on the first synthesised chunk (sub-second). The moment real
  audio starts we call `on_audio_start()` so the caller can start the lip
  animation + servo bob exactly in sync with the sound.

  Whether streaming works (correct binary, `--output_raw` flag, raw-capable
  player) is probed ONCE at startup; if not, we fall back to the original
  reliable file-based synth+play. Either way `on_audio_start()` fires right
  before audio actually begins.
"""

import os
import json
import tempfile
import subprocess
import threading

from config import (
    PIPER_PATH,
    PIPER_MODEL,
    PIPER_LENGTH_SCALE,
    TTS_PLAYER,
)


def _model_sample_rate():
    """Voice sample rate from <model>.json (Piper voice config); default 22050."""
    try:
        with open(PIPER_MODEL + ".json") as f:
            cfg = json.load(f)
        rate = cfg.get("audio", {}).get("sample_rate") or cfg.get("sample_rate")
        return int(rate) if rate else 22050
    except Exception:
        return 22050


class PiperTTS:

    def __init__(self):
        self.lock        = threading.Lock()
        self.sample_rate = _model_sample_rate()
        self._raw_cmd    = self._build_raw_player_cmd()
        self._can_stream = self._probe_streaming()
        print(f"[Piper] mode: {'streaming' if self._can_stream else 'file'} "
              f"@ {self.sample_rate} Hz")

    # ── player command for raw PCM on stdin ─────────────────────────────────
    def _build_raw_player_cmd(self):
        player = os.path.basename(TTS_PLAYER).lower()
        if player.startswith("paplay"):
            return [TTS_PLAYER, "--raw", f"--rate={self.sample_rate}",
                    "--format=s16le", "--channels=1"]
        if player.startswith("aplay"):
            return [TTS_PLAYER, "-q", "-r", str(self.sample_rate),
                    "-f", "S16_LE", "-c", "1", "-t", "raw", "-"]
        if player.startswith("ffplay"):
            return [TTS_PLAYER, "-autoexit", "-nodisp", "-loglevel", "quiet",
                    "-f", "s16le", "-ar", str(self.sample_rate), "-ac", "1", "-"]
        return None   # unknown player → can't stream raw, use file mode

    def _piper_cmd(self, raw):
        cmd = [PIPER_PATH, "--model", PIPER_MODEL,
               "--length_scale", str(PIPER_LENGTH_SCALE)]
        cmd.append("--output_raw" if raw else "--output_file")
        return cmd

    # ── one-time probe: does `piper --output_raw` actually work here? ────────
    def _probe_streaming(self):
        if self._raw_cmd is None:
            return False
        try:
            r = subprocess.run(
                self._piper_cmd(raw=True),
                input=b"ok",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            return r.returncode == 0
        except Exception:
            return False

    # ── public ──────────────────────────────────────────────────────────────
    def speak(self, text, on_audio_start=None):
        with self.lock:
            if self._can_stream:
                self._speak_streaming(text, on_audio_start)
            else:
                self._speak_file(text, on_audio_start)

    # ── streaming: piper --output_raw → (python pump) → player(raw stdin) ───
    def _speak_streaming(self, text, on_audio_start):
        """Pump Piper's raw PCM into the player chunk by chunk. The pump lets
        us fire on_audio_start on the FIRST audio chunk — the exact moment
        sound begins — so lips/servos sync to audio, not to synth start."""
        piper = player = None
        try:
            piper = subprocess.Popen(
                self._piper_cmd(raw=True),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            player = subprocess.Popen(
                self._raw_cmd, stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            piper.stdin.write(text.encode("utf-8"))
            piper.stdin.close()

            started = False
            while True:
                chunk = piper.stdout.read(4096)
                if not chunk:
                    break
                if not started:
                    started = True
                    if on_audio_start:
                        on_audio_start()
                player.stdin.write(chunk)

            player.stdin.close()
            player.wait()
            piper.wait()
            if not started and on_audio_start:
                on_audio_start()   # keep caller's state machine consistent
        except Exception as e:
            print(f"[Piper] streaming error: {e}")
            if on_audio_start:
                on_audio_start()   # never leave the caller waiting for sync
            for p in (player, piper):
                try:
                    if p and p.poll() is None:
                        p.kill()
                except Exception:
                    pass

    # ── file-based (fallback, always available) ─────────────────────────────
    def _speak_file(self, text, on_audio_start):
        wav_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_file = f.name
            subprocess.run(
                self._piper_cmd(raw=False) + [wav_file],
                input=text.encode("utf-8"), check=True,
            )
            if on_audio_start:      # sync lips to the actual playback, not synth
                on_audio_start()
            subprocess.run([TTS_PLAYER, wav_file], check=True)
        except Exception as e:
            print(f"[Piper] error: {e}")
            if on_audio_start:      # keep face/mic state consistent even on error
                on_audio_start()
        finally:
            if wav_file and os.path.exists(wav_file):
                os.remove(wav_file)


tts = PiperTTS()
