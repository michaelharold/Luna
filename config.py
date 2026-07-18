# config.py

import os
import time

# Load .env file if present (simple parser — no extra dependency needed).
# .env is git-ignored, so secrets stay out of version control.
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── Pi 5 fixed config ─────────────────────────────────────────────────────────
PI_MODEL        = 5
VISION_FPS      = 8
GESTURE_FPS     = 6
RENDER_FPS      = 60
DEEPFACE_EVERY  = 4
TORCH_THREADS   = 4

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_ID      = 0
FRAME_WIDTH    = 320
FRAME_HEIGHT   = 240
FPS            = 30
ESP32_STREAM   =  "http://10.240.252.155/stream"
USE_ESP32_CAM  = False

# ── Models ────────────────────────────────────────────────────────────────────
MODEL_PATH     = "models/emotion_raf_mobilenet_finetuned.pth"
KNOWLEDGE_PATH = "data/knowledge.txt"

# ── Robot identity ────────────────────────────────────────────────────────────
ROBOT_NAME = "Luna"
WAKE_WORDS = ["hello", "luna", "hey luna"]  # any of these activates conversation

# ── Conversation mode ─────────────────────────────────────────────────────────
CONVO_TIMEOUT      = 10    # seconds of silence before deactivating conversation
POST_SPEAK_DELAY   = 0.8   # settle time after Luna speaks before listening again
DOUBLE_FLUSH       = True  # flush audio queue twice (before and after delay)
MIC_BLOCK_AFTER_SPEAK = 0.6   # echo-guard after speech ends (speech itself already
                              # blocks the mic via state.speaking)

# Some TTS drivers (notably pyttsx3's macOS "nsss" backend on a reused engine)
# can return from runAndWait() BEFORE the audio has actually finished playing
# through the speaker. If that happens the mic would unblock while Luna is
# still audibly talking and hear herself. text_to_speech.py detects an
# early return (elapsed time well under the expected speech duration) and
# pads the mic block to cover the remaining expected playback time.
TTS_EARLY_RETURN_RATIO = 0.6   # elapsed/expected below this = treat as early return

# Extra defense: if what the mic just heard closely matches what Luna just
# said (within this many seconds), it's almost certainly speaker echo/room
# reverb, not a real new utterance from the user — discard it. Both checks
# must pass (AND, not OR) to stay high-precision — heavily garbled ASR
# echoes won't always clear this, but the timing fix above (mic block
# padded to the real speech duration) prevents most of those from being
# heard in the first place; this is just cleanup for trailing echo/reverb.
ECHO_GUARD_WINDOW  = 8.0    # seconds after speaking to check for self-echo
ECHO_RUN_THRESH    = 0.5    # longest contiguous word-run shared with the reply
ECHO_OVERLAP_THRESH = 0.6   # fraction of heard words that appear in the reply

# Spoken when a wake word is heard on its own ("Luna!") with no question attached
WAKE_REPLIES = ["Yes?", "I'm listening!", "Hi! How can I help?"]

# ── Emotion smoothing ─────────────────────────────────────────────────────────
EMOTION_HISTORY_LEN  = 5
SAD_CONFIDENCE       = 55.0
SLEEP_AFTER_FRAMES   = RENDER_FPS * 30

# ── Servos ────────────────────────────────────────────────────────────────────
ENABLE_SERVOS = False   # False = testing, True = servos wired up

# ── Groq API ──────────────────────────────────────────────────────────────────
# Set via environment variable:  export GROQ_API_KEY="gsk_..."
# (never commit a real key to git — see README "API key" section)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

# ── Audio devices ─────────────────────────────────────────────────────────────
# None = auto detect, set to index if auto detect picks wrong device
# run: python3 -c "import sounddevice; print(sounddevice.query_devices())"
AUDIO_INPUT_DEVICE  = 1
AUDIO_OUTPUT_DEVICE = None

# ── STT ───────────────────────────────────────────────────────────────────────
VOSK_MODEL_PATH = "vosk-model-small-en-us-0.15"

# None = auto-detect the device's native sample rate (recommended).
# Set to a number (e.g. 48000, 44100, 32000, 16000) only if auto-detect fails.
# Find your mic's rate: python3 -c "import sounddevice as sd; print(sd.query_devices())"
MIC_SAMPLE_RATE = 32000

VOSK_SAMPLE_RATE = 16000    # vosk always needs 16000 — do not change

# ── STT noise rejection (only respond when actually addressed) ─────────────────
# Layered defence so ambient noise is never turned into words Luna answers.
#
# 1) Energy gate (VAD): audio blocks quieter than the gate are treated as
#    ambient noise and fed to Vosk as digital silence, so background sound is
#    never transcribed. The gate ADAPTS to the room: a slow-moving noise-floor
#    estimate tracks ambient loudness, and the gate sits MIC_GATE_FACTOR above
#    it — rising automatically in noisy rooms, falling in quiet ones.
#    MIC_ENERGY_THRESHOLD is the minimum gate (int16 RMS scale, 0–32767).
#    To calibrate: watch the "[STT] ... peak_rms=/gate=" debug lines — speech
#    should sit well above the gate, room noise below it.
MIC_ENERGY_THRESHOLD = 500.0    # gate never drops below this
MIC_GATE_FACTOR      = 2.5      # gate = noise_floor × this (≥ threshold above)
MIC_GATE_MAX         = 4000.0   # safety cap so speech can always get through

# 2) Confidence gate: drop a recognised phrase whose average Vosk word
#    confidence is below this (0.0–1.0). Filters low-confidence hallucinations
#    that noise produces.
STT_CONFIDENCE_THRESHOLD = 0.55

# Wake words are checked on their OWN confidence (not the whole phrase) so a
# noise-hallucinated "luna" can't wake her, while a clearly spoken wake word
# still cuts through a noisy room. Slightly-misheard wake words (e.g. Vosk
# hearing "lunar") also wake her via fuzzy matching when heard confidently.
WAKE_CONFIDENCE_THRESHOLD = 0.60
WAKE_FUZZY_RATIO          = 0.80   # difflib similarity for near-miss wake words

# 3) Minimum length: ignore stray single-character tokens ("a", "i", "o") that
#    noise commonly yields. Real short answers ("yes"/"no"/"hi") still pass.
STT_MIN_UTTERANCE_CHARS = 2

# Print per-utterance rms/confidence so the thresholds above can be tuned.
STT_DEBUG_AUDIO = True

# ── TTS ───────────────────────────────────────────────────────────────────────

TTS_RATE = 155

# Piper voice engine
PIPER_PATH = "/home/luna/piper/piper/piper"

PIPER_MODEL = (
    "/home/luna/piper/voices/"
    "en_US-lessac-medium.onnx"
)

# Higher = slower speech
# 1.0 = default
# 1.3 = natural assistant pace
PIPER_LENGTH_SCALE = 1.3

TTS_PLAYER = "paplay"

# ── Brain ─────────────────────────────────────────────────────────────────────
GROQ_MAX_TOKENS     = 150   # max tokens per response (keep short for speech)
GROQ_TEMPERATURE    = 0.7   # creativity (0.0 = factual, 1.0 = creative)
GROQ_MAX_HISTORY    = 6     # max conversation history turns to send to API
LOCAL_MATCH_THRESH  = 0.55  # min similarity score for local knowledge match

# ── Gestures / expressions ────────────────────────────────────────────────────
GESTURE_REACT_COOLDOWN = 8.0   # seconds between spoken reactions to a gesture
FACE_OVERRIDE_SECS     = 4.0   # how long gesture-triggered faces (excited/love) last

# ── Face style ────────────────────────────────────────────────────────────────
# 1 = Luna classic (purple, soft rounded)
# 2 = Robo (cyan, sharp corners, equalizer-bar mouth — NIMO/modern-robot look)
# Press 1 / 2 on the face window to switch live; this sets the startup default.
FACE_STYLE = 2
