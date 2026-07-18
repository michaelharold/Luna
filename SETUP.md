# Luna — Setup & Run Guide 🚀

A single, linear walkthrough: **clone → install → download models → configure → run → troubleshoot.**
Follow the steps in order. For deeper reference on any topic, the [README](README.md) has the full detail (linked throughout).

> **TL;DR** — Python **3.11**, a venv, `pip install -r requirements.txt`, download 3 model bundles (Vosk, emotion weights, Piper), add a `.env` key (optional), then `python3 main.py`.

---

## 0. What you need

| Requirement | Notes |
|---|---|
| **Python 3.11** | Pinned deps (torch 2.3.1, tensorflow 2.15.0, mediapipe 0.10.9) are built for 3.11. Newer Python may fail to install. |
| **git** | To clone the repo. |
| Microphone | Optional — Luna runs without it (retries every 5 s). |
| Camera | Optional — Luna runs without it (voice still works). |
| Speaker + **Piper** | Optional — without Piper, Luna prints replies as text instead of speaking. |

Check Python:

```bash
python3 --version     # macOS/Linux — want 3.11.x
py -3.11 --version    # Windows
```

Don't have 3.11? Install it: `brew install python@3.11` (macOS) · python.org installer (Windows) · `sudo apt install python3.11 python3.11-venv python3.11-dev` (Pi/Debian).

---

## 1. Clone the repo

```bash
git clone https://github.com/michaelharold/Luna.git
cd Luna
```

Every command below is run **from this `Luna/` project root.**

---

## 2. Create a virtual environment

**macOS / Linux / Raspberry Pi**
```bash
python3.11 -m venv venv
source venv/bin/activate
```

**Windows**
```powershell
py -3.11 -m venv venv
venv\Scripts\activate
```

Your prompt should now show `(venv)`. Confirm the right Python is active: `which python3` (macOS/Linux) / `where python` (Windows) must point inside `venv/`.

> On a Pi, install the system audio/vision libs **first**:
> ```bash
> sudo apt update && sudo apt install -y portaudio19-dev python3-pyaudio \
>     python3-opencv libatlas-base-dev libhdf5-dev
> ```
> On macOS: `brew install portaudio` (needed by `sounddevice`).

---

## 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Raspberry Pi extras:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
# if mediapipe fails on Pi:
pip install mediapipe-rpi5 --break-system-packages   # Pi 5  (use -rpi4 on Pi 4)
```

Sanity-check every import resolves before going further:

```bash
python3 -c "import torch, cv2, mediapipe, pygame, sounddevice, vosk, groq, sentence_transformers, deepface, tensorflow; print('ALL_OK')"
```

If this doesn't print `ALL_OK`, fix the failing import first (usually the venv isn't active or an install step didn't finish).

---

## 4. Download the models (not stored in git)

Three bundles are git-ignored because they're large binaries. See [README §4](README.md#4-required-downloads-not-stored-in-git) for full detail.

### 4a. Vosk speech model (required for listening)
```bash
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip && rm vosk-model-small-en-us-0.15.zip
ls vosk-model-small-en-us-0.15/     # should show am/ conf/ graph/ ivector/
```
Must extract to a folder named exactly `vosk-model-small-en-us-0.15` in the project root.

### 4b. Emotion weights (optional — face tracking still works without it)
Place `models/emotion_raf_mobilenet_finetuned.pth` (~10 MB, get it from whoever shared the repo). Without it, Luna keeps running; emotion just stays *Neutral*.
```bash
ls models/emotion_raf_mobilenet_finetuned.pth
```

### 4c. Piper voice (required for speaking) — Pi/Linux
```bash
mkdir -p /home/luna/piper && cd /home/luna/piper
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz
tar -xzf piper_linux_aarch64.tar.gz          # → /home/luna/piper/piper/piper

mkdir -p /home/luna/piper/voices && cd /home/luna/piper/voices
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium
wget $BASE/en_US-lessac-medium.onnx
wget $BASE/en_US-lessac-medium.onnx.json
cd -   # back to the Luna project root
```
Test it standalone:
```bash
echo "Hello, I am Luna." | /home/luna/piper/piper/piper \
    --model /home/luna/piper/voices/en_US-lessac-medium.onnx --output_file /tmp/t.wav
paplay /tmp/t.wav      # you should hear it
```
> **Different OS / username / paths?** Edit `PIPER_PATH`, `PIPER_MODEL`, and `TTS_PLAYER` in `config.py` (macOS: `TTS_PLAYER = "afplay"`). No Piper? Luna prints replies as text — nothing crashes. Full detail: [README §4c](README.md#4c-piper-voice-tts).

---

## 5. Add your Groq API key (optional)

With a key, Luna answers via the Groq LLM. Without one, she uses the offline knowledge base (`data/knowledge.txt`).

```bash
cp .env.example .env
# edit .env  →  GROQ_API_KEY=gsk_your_key_here   (free key at https://console.groq.com)
```

`.env` is git-ignored — never commit your real key. Verify it loads:
```bash
python3 -c "from config import GROQ_API_KEY; print('key loaded:', bool(GROQ_API_KEY))"
```

---

## 6. Configure your hardware (`config.py`)

Open `config.py` and adjust only what applies to you:

| Setting | When to change it |
|---|---|
| `AUDIO_INPUT_DEVICE` | Wrong mic picked. Find index: `python3 -c "import sounddevice as sd; print(sd.query_devices())"` |
| `MIC_SAMPLE_RATE` | Recognition sounds off — pin your mic's native rate (else leave `None` to auto-detect). |
| `MIC_ENERGY_THRESHOLD` | Minimum energy gate (it also adapts to the room automatically). Noisy room triggers Luna → raise it; quiet speaker ignored → lower it. Watch the `[STT] … peak_rms=/gate=` logs to calibrate. |
| `REQUIRE_FACE_TO_TALK` | Luna only answers people **facing her camera** (stops side conversations triggering her). Set `False` for mic-only or dim-light setups where face detection is unreliable. |
| `CAMERA_ID` / `USE_ESP32_CAM` | Wrong camera, or using an ESP32 Wi-Fi cam (`ESP32_STREAM`). |
| `ENABLE_SERVOS` | `True` only when servos are wired (Pi). Leave `False` for dev — you'll see `[SERVO] …` prints. |
| `PIPER_PATH` / `PIPER_MODEL` / `TTS_PLAYER` | Piper installed somewhere other than the defaults (see step 4c). |
| `FACE_STYLE` | `1` = Luna classic (purple), `2` = Robo (cyan). Also switchable live with keys `1`/`2`. |

**Servo wiring (Pi):** left arm → GPIO 18, right arm → GPIO 17 (BCM, 50 Hz PWM), then set `ENABLE_SERVOS = True`. (Head-pan → GPIO 27 is currently disabled in code.)

---

## 7. Run Luna

```bash
source venv/bin/activate      # Windows: venv\Scripts\activate
python3 main.py               # Windows: python main.py
```

**What you should see** — startup logs for each subsystem, then the face window opens:
```
[Luna] Running on Raspberry Pi 5
[camera] Local camera started 320x240 @ 30fps
[vision] PyTorch model ready
[vision] DeepFace ready
[brain] N knowledge entries loaded
[SERVO] Servos disabled (ENABLE_SERVOS=False)
[STT] Microphone stream running @ 32000 Hz
```

**Try it:** say **"hello"** / **"luna"** / **"hey luna"** to wake her, then ask a question. Wave 👋, thumbs-up 👍, or peace ✌ to trigger reactions.

**Stop:** press **Ctrl+C** in the terminal, or close the face window — servos re-center and GPIO releases cleanly.

---

## 8. Quick troubleshooting

Luna is built to **degrade gracefully** — a missing mic/camera/speaker/model never crashes the app. Common issues (full guide: [README §10](README.md#10-troubleshooting)):

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` on startup | venv not active, or `pip install -r requirements.txt` didn't finish. Re-check step 2–3. |
| `[STT] NO MICROPHONE FOUND` | Set `AUDIO_INPUT_DEVICE` in `config.py` (step 6). Pi: `sudo usermod -aG audio $USER` then reboot. |
| Hears random words / talks to noise | Raise `MIC_ENERGY_THRESHOLD` (and/or `STT_CONFIDENCE_THRESHOLD`) in `config.py`; watch `[STT] … peak_rms=/gate=` to calibrate. Side conversations are already ignored via the face gate (`REQUIRE_FACE_TO_TALK`). |
| Luna ignores you (`[STT] … nobody facing me` in logs) | You're not in front of the camera, or the light is too dim for face detection. Face her camera, improve lighting, or set `REQUIRE_FACE_TO_TALK = False`. |
| `[Piper] error: …`, no voice (text shows) | Piper not installed/configured — redo step 4c, check `PIPER_PATH`/`PIPER_MODEL` exist and `which paplay`. |
| `[vision] Emotion model unavailable …` | You skipped step 4b. Face tracking still works; emotion stays Neutral until you add the weights. |
| `[camera] NO CAMERA FOUND` | Set `CAMERA_ID`, or grant camera permission (macOS/Windows), or enable the Pi camera in `raspi-config`. |
| `pygame.error: No available video device` (Pi headless/SSH) | Luna needs a display — use a monitor, VNC/X-forwarding, or `SDL_VIDEODRIVER=dummy` for non-visual testing. |
| `Vosk … Model path does not exist` | The Vosk folder isn't named exactly `vosk-model-small-en-us-0.15` in the project root — redo step 4a. |

---

Built by the Computer Science Department — **Michael Harold Sony, Sreenadhana, and Devadathan**. Changes are logged in [UPDATES.txt](UPDATES.txt).
