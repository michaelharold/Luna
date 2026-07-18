# Luna Servo Setup 🦾

Hardware wiring and software configuration for Luna's three movement servos (head-pan, left arm, right arm). For general project setup, see [README.md](README.md); for other Pi tuning (swap, GPU split, governor), see [pi_inst.txt](pi_inst.txt).

## Table of contents

1. [Overview](#1-overview)
2. [Parts list](#2-parts-list)
3. [Wiring](#3-wiring)
4. [Software setup](#4-software-setup)
5. [Testing](#5-testing)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Overview

Luna moves with three standard hobby servos, driven by software PWM through [servo_module.py](servo_module.py):

| Servo | Function | BCM GPIO | Physical header pin |
|---|---|---|---|
| Head pan | look/nod — **currently disabled in code** (hands only) | GPIO 27 | pin 13 |
| Left arm | raise/lower, talking bob, arms-up celebration | GPIO 18 | pin 12 |
| Right arm | wave, raise/lower, talking bob, arms-up celebration | GPIO 17 | pin 11 |

> **Pin numbers here match the `PIN_*` constants in `servo_module.py`, which are the source of truth.** If you wire to different pins, update those constants (see [§4.3](#43-pin--frequency-constants-servo_modulepy)) and these tables together.
>
> **Head-pan is disabled in code right now** — `nod()` and `head_look()` are commented out in `servo_module.py` (look for the `HEAD DISABLED FOR NOW` markers). Only the two arm servos move today; the head wiring below is included so you can re-enable it later.

All three run at **50 Hz** PWM (the standard hobby-servo rate). Angles are 0–180°, mapped to a 2.5%–12.5% duty cycle (`angle_to_duty()` in `servo_module.py`) — this wider pulse range (~0.5 ms–2.5 ms) is needed to reach the full 0–180° sweep on most SG90/MG90-class servos; centre/rest position is 90° (7.5% duty) for all three.

Servos are only driven when `ENABLE_SERVOS = True` in `config.py` **and** the code is running on hardware with `RPi.GPIO` importable. Otherwise `servo_module.py` runs in **simulation mode** — every move prints `[SERVO SIM] <label> → <angle>°` instead of touching GPIO, so the rest of Luna (face, voice, gestures) works unchanged on a Mac/Windows dev machine.

---

## 2. Parts list

- **3× standard hobby servos** (SG90 micro servo or similar 5 V, 3-pin PWM, full 0–180° range — the code clamps to 0–180° and assumes that range)
- **External 5 V/6 V servo power supply** (a 4× AA pack, a 5V/2A+ UBEC, or a bench supply) — see the power warning below
- **Common ground wire** between the Pi's GND and the servo power supply's GND
- Jumper wires (female-to-male if wiring straight from the Pi header to servo connectors)
- Optional: a small breadboard or perma-proto board to distribute power/ground to all three servos, and a mounting bracket/frame for head + arms

---

## 3. Wiring

Each servo has a standard 3-pin connector:

| Wire colour (typical) | Connects to |
|---|---|
| Orange/yellow (signal) | The servo's BCM GPIO pin (27 / 18 / 17 — see table in §1) |
| Red (VCC) | **External** 5V/6V power rail — *not* the Pi's 5V pin |
| Brown/black (GND) | Common ground — tie the Pi's GND, the servo PSU's GND, and all three servo grounds together |

### ⚠️ Power — don't power servos from the Pi

Do **not** wire servo VCC to the Raspberry Pi's own 5V pins (physical pin 2 or 4). A single SG90 stalling, or two/three servos moving at once (e.g. `arms_up()`, which drives both arm servos simultaneously), can draw enough current to brown out the Pi — causing random reboots, SD card corruption, or silent GPIO glitches that look like a software bug but aren't.

Use a separate 5V/6V supply rated for at least ~1.5–2 A (headroom for 3 servos moving together), and **always** tie its ground to the Pi's ground — shared ground is required for the PWM signal to be read correctly, even though power comes from a separate source.

### Signal wiring summary

```
Raspberry Pi 5 (40-pin header)          Servos
─────────────────────────────           ──────────────────
GPIO 27 (physical pin 13) ───signal───▶ Head-pan servo (disabled in code)
GPIO 18 (physical pin 12) ───signal───▶ Left-arm servo
GPIO 17 (physical pin 11) ───signal───▶ Right-arm servo
GND (e.g. physical pin 9) ───────────── Common ground rail ── external PSU GND
                                          │
                          External 5V/6V ─┴── all 3 servo VCC pins
```

---

## 4. Software setup

### 4.1 Install the GPIO library (Pi only)

`RPi.GPIO` is intentionally **not** in `requirements.txt` — it only builds/works on actual Raspberry Pi hardware, and would break installs on Mac/Windows dev machines.

**Important Pi 5 note:** Luna's `config.py` is pinned to `PI_MODEL = 5`. Classic `RPi.GPIO` does **not** support the Pi 5's new RP1 I/O chip and will fail (or silently misbehave) on it. Use **`rpi-lgpio`** instead — a drop-in replacement that exposes the exact same `import RPi.GPIO as GPIO` API `servo_module.py` already uses, backed by `lgpio`:

```bash
# On the Pi, inside the activated venv:
pip install rpi-lgpio --break-system-packages
```

If real `RPi.GPIO` is already installed, remove it first — the two packages conflict since they both provide the `RPi.GPIO` module name:

```bash
pip uninstall RPi.GPIO -y
pip install rpi-lgpio --break-system-packages
```

(On a Pi 4, real `RPi.GPIO` works fine — `pip install RPi.GPIO --break-system-packages` — but since this project targets Pi 5, `rpi-lgpio` is the recommended path either way.)

### 4.2 Enable servos in `config.py`

```python
# ── Servos ────────────────────────────────────────────────────────────────
ENABLE_SERVOS = True   # False = simulation only, True = servos wired up
```

Leave this `False` while developing off the robot (Mac/Windows, or a Pi with no servos wired yet) — everything else in Luna runs identically either way.

### 4.3 Pin / frequency constants (`servo_module.py`)

If your wiring uses different GPIO pins, update these constants at the top of `servo_module.py` (BCM numbering):

```python
PIN_HEAD_PAN  = 27
PIN_LEFT_ARM  = 18
PIN_RIGHT_ARM = 17

PWM_FREQ = 50   # Hz — standard servo frequency, don't change unless your servos require it
```

### 4.4 Behavior summary

| State | What happens |
|---|---|
| `ENABLE_SERVOS = False` | Simulation mode — `[SERVO SIM] <label> → <angle>°` printed for every move, no GPIO touched |
| `ENABLE_SERVOS = True` + `RPi.GPIO`/`rpi-lgpio` importable | Real PWM output on the three pins |
| `ENABLE_SERVOS = True` + import fails | Automatically falls back to simulation mode with a `[SERVO] RPi.GPIO not found — falling back to simulation` warning — Luna keeps running either way |

On shutdown (Ctrl+C or closing the face window), `main.py` calls `servo.cleanup()`, which first returns all servos to centre (90°) so nothing is left frozen mid-gesture, waits briefly for them to travel, then stops all PWM output and releases GPIO cleanly (`GPIO.cleanup()`) so pins aren't left driven.

---

## 5. Testing

### 5.1 Quick per-servo test

With `ENABLE_SERVOS = True` and the Pi wired up, run each arm gesture directly from a Python REPL (venv activated) to confirm wiring before running all of Luna. (Head-pan methods are commented out in code, so there's nothing to test on GPIO 27 yet.)

```bash
python3 -c "
from servo_module import servo
import time

servo.wave()            # right-arm servo (GPIO 17)
time.sleep(3)
servo.arm_up('left')    # left-arm servo (GPIO 18)
time.sleep(2)
servo.arm_up('right')   # right-arm servo (GPIO 17)
time.sleep(2)
servo.arms_up()         # both arms together — also checks power headroom
time.sleep(3)
"
```

Watch for: the correct servo moving for each call, smooth motion (not jittery), and no Pi reboot/brownout when `arms_up()` drives both arms at once.

### 5.2 Full run

```bash
source venv/bin/activate
python3 main.py
```

Startup logs should show the servo controller initializing with no `RPi.GPIO not found` warning. Say **"hello"** and wave at the camera — Luna's face should react and the right-arm servo should wave back.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `[SERVO] Servos disabled (ENABLE_SERVOS=False)` even though you set it `True` | You edited a stale copy, or didn't restart `main.py` after saving `config.py` — config is only read at startup. |
| `[SERVO] RPi.GPIO not found — falling back to simulation` on the Pi | GPIO library isn't installed in the active venv, or you're on Pi 5 with plain `RPi.GPIO` installed instead of `rpi-lgpio` — see [§4.1](#41-install-the-gpio-library-pi-only). |
| Servo doesn't move at all, but no errors printed | Check signal wire is on the correct BCM pin (not just the correct physical position), and that servo VCC actually has power (measure with a multimeter — a dead/underpowered rail won't show up as a Python error). |
| Servo jitters/buzzes constantly instead of holding position | Usually a shared-ground problem (Pi GND not tied to servo PSU GND) or a marginal power supply under load — verify wiring against [§3](#3-wiring). |
| Pi reboots or the SD card corrupts when servos move (especially `arms_up()`) | Servos are powered from the Pi's own 5V rail. Move them to a separate 5V/6V supply — see the power warning in [§3](#3-wiring). |
| `RuntimeError` mentioning `/dev/gpiomem` or permissions | Add your user to the `gpio` group: `sudo usermod -aG gpio $USER`, then log out/in (or reboot). |
| Works on Pi 4, fails on Pi 5 with cryptic `lgpio`/chip errors | Confirms the `RPi.GPIO` vs `rpi-lgpio` issue in [§4.1](#41-install-the-gpio-library-pi-only) — Pi 5's GPIO chip needs `rpi-lgpio`. |
| Angles look inverted or the servo strains at one end of travel | Your specific servo's real range may be narrower than 0–180°, or mounted rotated 180°. Adjust the target angles in the relevant method in `servo_module.py` (e.g. swap/clamp the `wave()`/`arm_up()` ranges) rather than changing `angle_to_duty()`. |
