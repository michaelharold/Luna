# shared_state.py
from threading import Lock
import time


class SharedState:

    __slots__ = (
        "lock",
        "frame",
        "face_detected", "face_x", "face_y",
        "emotion",
        "frozen_emotion",        # emotion locked while speaking
        "gesture",
        "heard_text", "response",
        "speaking", "listening",
        "audio_energy",
        "audio_playing",         # True only while real TTS audio is playing
                                 # (drives lip sync; speaking stays True for the
                                 # whole call so the mic stays blocked)
        "look_dir",
        "servo_action",
        "conversation_active",
        "convo_expired_time",    # time.time() when conversation last timed out
        "last_activity_time",
        "mic_unblock_time",      # time.time() after which mic is allowed
        "luna_mode",             # "idle" | "listening" | "processing" | "speaking"
        "face_override",         # temporary face state ("excited" | "love" | None)
        "face_override_until",   # time.time() when the override expires
        "mic_ok",                # False when no working microphone was found
        "camera_ok",             # False when no working camera was found
        "last_spoken_text",      # Luna's most recent utterance (lowercased)
        "last_spoken_time",      # time.time() when that utterance finished
    )

    def __init__(self):
        self.lock                = Lock()
        self.frame               = None
        self.face_detected       = False
        self.face_x              = 0.5
        self.face_y              = 0.5
        self.emotion             = "Neutral"
        self.frozen_emotion      = None
        self.gesture             = None
        self.heard_text          = ""
        self.response            = ""
        self.speaking            = False
        self.listening           = False
        self.audio_energy        = 0.0
        self.audio_playing       = False
        self.look_dir            = None
        self.servo_action        = None
        self.conversation_active = False
        self.convo_expired_time  = 0.0
        self.last_activity_time  = 0.0
        self.mic_unblock_time    = 0.0
        self.luna_mode           = "idle"
        self.face_override       = None
        self.face_override_until = 0.0
        self.mic_ok              = True
        self.camera_ok           = True
        self.last_spoken_text    = ""
        self.last_spoken_time    = 0.0


state = SharedState()