"""
servo_module.py — Luna servo controller.

ENABLE_SERVOS = False  → silent simulation mode (Mac / dev)
ENABLE_SERVOS = True   → real GPIO PWM on Pi

GPIO pins (BCM numbering) — these constants are the single source of truth;
the wiring docs (README, SERVO_SETUP.md) match them. If you wire differently,
change PIN_* below and the docs' pin numbers accordingly.
  HEAD_PAN  → GPIO 27   (currently disabled in code — hands only)
  LEFT_ARM  → GPIO 18
  RIGHT_ARM → GPIO 17
"""

import math
import threading
import time
from config import ENABLE_SERVOS

if ENABLE_SERVOS:
    try:
        import RPi.GPIO as GPIO
        RPI = True
    except ImportError:
        print("[SERVO] RPi.GPIO not found — falling back to simulation")
        RPI = False
else:
    RPI = False
    print("[SERVO] Servos disabled (ENABLE_SERVOS=False)")

# ── Pin assignments ───────────────────────────────────────────────────────────
PIN_HEAD_PAN  = 27
PIN_LEFT_ARM  = 18
PIN_RIGHT_ARM = 17

PWM_FREQ = 50   # Hz — standard servo frequency


def angle_to_duty(angle):
    """Convert 0-180° to 2.5-12.5% duty cycle."""
    return 2.5 + (angle / 180.0) * 10.0


# ── Controller ────────────────────────────────────────────────────────────────

class ServoController:

    def __init__(self):
        self.running         = True
        self._queue          = []
        self._lock           = threading.Lock()
        self._talking        = False   # drives the subtle talking bob
        self._action_running = False   # a queued gesture is mid-motion

        if RPI:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in [PIN_HEAD_PAN, PIN_LEFT_ARM, PIN_RIGHT_ARM]:
                GPIO.setup(pin, GPIO.OUT)

            self.pwm_head  = GPIO.PWM(PIN_HEAD_PAN,  PWM_FREQ)
            self.pwm_left  = GPIO.PWM(PIN_LEFT_ARM,  PWM_FREQ)
            self.pwm_right = GPIO.PWM(PIN_RIGHT_ARM, PWM_FREQ)

            for pwm in [self.pwm_head, self.pwm_left, self.pwm_right]:
                pwm.start(angle_to_duty(90))   # centre position
        else:
            self.pwm_head  = None
            self.pwm_left  = None
            self.pwm_right = None

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._talk_worker, daemon=True).start()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _set_angle(self, pwm, angle, label=""):
        if not ENABLE_SERVOS:
            return
        angle = max(0, min(180, angle))
        if RPI:
            pwm.ChangeDutyCycle(angle_to_duty(angle))
        else:
            print(f"  [SERVO SIM] {label} → {angle:.1f}°")

    def _smooth_move(self, pwm, start, end, steps=20, delay=0.02, label=""):
        if not ENABLE_SERVOS:
            return
        for i in range(steps + 1):
            angle = start + (end - start) * (i / steps)
            self._set_angle(pwm, angle, label)
            time.sleep(delay)

    def _worker(self):
        while self.running:
            action = None
            with self._lock:
                if self._queue:
                    action = self._queue.pop(0)
            if action:
                # flag the gesture as running so the talking bob yields the
                # arms while it moves (no two threads driving one servo).
                self._action_running = True
                try:
                    action()
                finally:
                    self._action_running = False
            else:
                time.sleep(0.05)

    def _talk_worker(self):
        """Subtle up/down bob on both arms while Luna talks.

        Driven directly by the `_talking` flag (set from state.speaking) instead
        of a duration estimate, so it starts and stops exactly with the speech —
        the arms never keep moving after Luna goes quiet, and never freeze
        mid-sentence. When talking stops it eases the arms back to rest once."""
        REST     = 90
        AMPL     = 12.0    # degrees — small, gentle bob
        INC      = 0.15    # phase step → ~1.3 s per up/down cycle
        STEP     = 0.03
        phase    = 0.0
        last_off = 0.0
        moving   = False

        while self.running:
            # A queued gesture (wave / arm_up / arms_up) owns the arms while it
            # runs — pause the bob so two threads never drive the same servo at
            # once (which jitters/strains it on real hardware).
            gesture_busy = self._action_running or bool(self._queue)

            if self._talking and ENABLE_SERVOS and not gesture_busy:
                moving   = True
                phase   += INC
                off      = AMPL * math.sin(phase)
                self._set_angle(self.pwm_left,  REST + off, "left_arm")
                self._set_angle(self.pwm_right, REST + off, "right_arm")
                last_off = off
                time.sleep(STEP)
            elif self._talking and gesture_busy:
                # still talking, but a gesture is moving the arms — don't touch
                # the servos; resume the bob cleanly from rest once it finishes.
                phase    = 0.0
                last_off = 0.0
                moving   = False
                time.sleep(0.03)
            else:
                if moving and ENABLE_SERVOS:
                    # ease both arms symmetrically back to rest
                    for i in range(11):
                        a = (REST + last_off) + (REST - (REST + last_off)) * (i / 10)
                        self._set_angle(self.pwm_left,  a, "left_arm")
                        self._set_angle(self.pwm_right, a, "right_arm")
                        time.sleep(0.02)
                    phase    = 0.0
                    last_off = 0.0
                moving = False
                time.sleep(0.03)

    def talk_start(self):
        """Begin the talking bob — called when Luna starts speaking."""
        self._talking = True

    def talk_stop(self):
        """Stop the talking bob and let the arms ease back to rest."""
        self._talking = False

    def queue(self, fn):
        with self._lock:
            self._queue.append(fn)

    # ── Actions ───────────────────────────────────────────────────────────────

    def wave(self):
        """Wave right arm — triggered by hi/hello or WAVE gesture."""
        def _do():
            print("[SERVO] wave()")
            for _ in range(3):
                self._smooth_move(self.pwm_right, 90, 150, steps=15, delay=0.02, label="right_arm")
                self._smooth_move(self.pwm_right, 150, 110, steps=10, delay=0.02, label="right_arm")
            self._smooth_move(self.pwm_right, 110, 90, steps=15, delay=0.02, label="right_arm")
        self.queue(_do)

    # HEAD DISABLED FOR NOW — hands only. Uncomment to re-enable the head nod.
    # def nod(self):
    #     """Head pan nod — before Luna speaks."""
    #     def _do():
    #         print("[SERVO] nod()")
    #         self._smooth_move(self.pwm_head, 90, 75,  steps=12, delay=0.02, label="head")
    #         self._smooth_move(self.pwm_head, 75,  105, steps=15, delay=0.02, label="head")
    #         self._smooth_move(self.pwm_head, 105, 90,  steps=12, delay=0.02, label="head")
    #     self.queue(_do)

    def arm_up(self, side="right"):
        """Raise one arm smoothly (90° rest → 160° up), hold, then lower."""
        pwm   = self.pwm_right if side == "right" else self.pwm_left
        label = f"{side}_arm"
        def _do():
            print(f"[SERVO] arm_up({side})")
            self._smooth_move(pwm, 90, 160, steps=18, delay=0.02, label=label)
            time.sleep(0.6)
            self._smooth_move(pwm, 160, 90, steps=18, delay=0.02, label=label)
        self.queue(_do)

    def arm_down(self, side="right"):
        """Lower one arm below rest (90° → 30°), hold, then return to rest."""
        pwm   = self.pwm_right if side == "right" else self.pwm_left
        label = f"{side}_arm"
        def _do():
            print(f"[SERVO] arm_down({side})")
            self._smooth_move(pwm, 90, 30, steps=18, delay=0.02, label=label)
            time.sleep(0.4)
            self._smooth_move(pwm, 30, 90, steps=18, delay=0.02, label=label)
        self.queue(_do)

    def arms_up(self):
        """Raise both arms together — celebration / thank-you gesture."""
        def _do():
            print("[SERVO] arms_up()")
            for i in range(19):
                a = 90 + (160 - 90) * (i / 18)
                self._set_angle(self.pwm_left,  a, "left_arm")
                self._set_angle(self.pwm_right, a, "right_arm")
                time.sleep(0.02)
            time.sleep(0.8)
            for i in range(19):
                a = 160 - (160 - 90) * (i / 18)
                self._set_angle(self.pwm_left,  a, "left_arm")
                self._set_angle(self.pwm_right, a, "right_arm")
                time.sleep(0.02)
        self.queue(_do)

    # HEAD DISABLED FOR NOW — hands only. Uncomment to re-enable head turns.
    # def head_look(self, direction="left"):
    #     """Turn the head toward a pointed direction, hold, then re-center."""
    #     target = 115 if direction == "left" else 65
    #     def _do():
    #         print(f"[SERVO] head_look({direction})")
    #         self._smooth_move(self.pwm_head, 90, target, steps=15, delay=0.02, label="head")
    #         time.sleep(0.5)
    #         self._smooth_move(self.pwm_head, target, 90, steps=15, delay=0.02, label="head")
    #     self.queue(_do)

    def idle_sway(self):
        """Slow breathing sway when idle."""
        def _do():
            print("[SERVO] idle_sway()")
            self._smooth_move(self.pwm_left,  90, 100, steps=30, delay=0.04, label="left_arm")
            self._smooth_move(self.pwm_right, 90,  80, steps=30, delay=0.04, label="right_arm")
            self._smooth_move(self.pwm_left,  100, 90, steps=30, delay=0.04, label="left_arm")
            self._smooth_move(self.pwm_right,  80,  90, steps=30, delay=0.04, label="right_arm")
        self.queue(_do)

    def cleanup(self):
        self.running  = False
        self._talking = False
        if RPI:
            # return everything to centre (90°) so nothing is left frozen
            # mid-gesture, give the servos a moment to travel, then release.
            for pwm in [self.pwm_head, self.pwm_left, self.pwm_right]:
                self._set_angle(pwm, 90, "center")
            time.sleep(0.4)
            for pwm in [self.pwm_head, self.pwm_left, self.pwm_right]:
                pwm.stop()
            GPIO.cleanup()


# Singleton — import this everywhere
servo = ServoController()