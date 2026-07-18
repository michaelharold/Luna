# brain.py
"""
brain.py — Groq API primary, local knowledge.txt fallback when offline.
All settings pulled from config.py.
"""

import re
import time
import numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq

from text_to_speech import speak
from servo_module import servo
from shared_state import state
from config import (
    FACE_OVERRIDE_SECS,
    KNOWLEDGE_PATH,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_MAX_TOKENS,
    GROQ_TEMPERATURE,
    GROQ_MAX_HISTORY,
    LOCAL_MATCH_THRESH,
    ROBOT_NAME,
)

# ── Load knowledge.txt ────────────────────────────────────────────────────────
print("[brain] Loading knowledge base...")

questions      = []
answers        = []
knowledge_text = ""

try:
    with open(KNOWLEDGE_PATH, "r") as f:
        raw            = f.read()
        knowledge_text = raw.strip()
        for line in raw.splitlines():
            if ":" not in line:
                continue
            q, a = line.split(":", 1)
            questions.append(q.strip().lower())
            answers.append(a.strip())
except OSError as e:
    # degrade gracefully — Luna still answers via Groq, offline fallback
    # just says "I don't know" instead of crashing the whole app
    print(f"[brain] Could not read {KNOWLEDGE_PATH} ({e}) — "
          f"offline knowledge base disabled")

# ── Local fallback — sentence transformer ─────────────────────────────────────
if questions:
    print("[brain] Loading sentence transformer for offline fallback...")
    _st_model = SentenceTransformer("all-MiniLM-L6-v2")

    _raw   = _st_model.encode(questions, batch_size=32, show_progress_bar=False)
    _norms = np.linalg.norm(_raw, axis=1, keepdims=True)
    question_embeddings = _raw / np.maximum(_norms, 1e-9)

    print(f"[brain] {len(questions)} knowledge entries loaded")
else:
    _st_model           = None
    question_embeddings = None
    print("[brain] Knowledge base empty — offline fallback disabled")

# ── Groq client ───────────────────────────────────────────────────────────────
if GROQ_API_KEY:
    # timeout: a network stall must never freeze Luna in "processing" —
    # after 10s we fall back to the offline knowledge base instead.
    _groq = Groq(api_key=GROQ_API_KEY, timeout=10.0, max_retries=1)
else:
    _groq = None
    print("[brain] No GROQ_API_KEY set — running fully offline "
          "(local knowledge base only). See README to enable the LLM.")
_history = []

SYSTEM_PROMPT = f"""You are Luna, a friendly robot assistant deployed at a college.
You were developed by the Computer Science Department.

You have a knowledge base about the department. Use it to answer relevant questions accurately.
For questions not in the knowledge base, answer helpfully and naturally as Luna would.
Keep responses SHORT and conversational — you are speaking out loud, not writing.
Maximum 2-3 sentences per response. Never use bullet points or markdown.

--- KNOWLEDGE BASE ---
{knowledge_text}
--- END KNOWLEDGE BASE ---
"""


# ── Groq API call ─────────────────────────────────────────────────────────────

def _ask_groq(text):
    if _groq is None:
        return None
    try:
        _history.append({"role": "user", "content": text})

        while len(_history) > GROQ_MAX_HISTORY:
            _history.pop(0)

        response = _groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *_history
            ],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=GROQ_TEMPERATURE,
        )

        reply = response.choices[0].message.content.strip()
        _history.append({"role": "assistant", "content": reply})

        print(f"[brain] Groq: {reply}")
        return reply

    except Exception as e:
        print(f"[brain] Groq error: {e}")
        if _history and _history[-1]["role"] == "user":
            _history.pop()
        return None


# ── Local fallback ────────────────────────────────────────────────────────────

def _local_fallback(text):
    if _st_model is None:
        return "I am sorry, I cannot reach my brain right now. Please try again."
    q_vec  = _st_model.encode([text], batch_size=1, show_progress_bar=False)[0]
    q_norm = q_vec / max(float(np.linalg.norm(q_vec)), 1e-9)

    scores     = question_embeddings @ q_norm
    best_index = int(np.argmax(scores))
    best_score = float(scores[best_index])

    print(f"[brain] Local match score: {best_score:.2f}")

    if best_score > LOCAL_MATCH_THRESH:
        return answers[best_index]
    return "I am sorry, I do not have an answer for that."


# ── Main process ──────────────────────────────────────────────────────────────

def process(text):
    text = text.strip()
    if not text:
        return

    print(f"[brain] Processing: {text}")

    lower = text.lower()
    words = set(re.findall(r"[a-z']+", lower))

    # servo reactions — whole-word match (old substring check waved at "this")
    # HEAD DISABLED FOR NOW — hands only. The hands still animate during the
    # spoken reply via the talking bob, so non-greetings aren't motionless.
    if words & {"hi", "hello", "hey", "bye", "goodbye"}:
        servo.wave()
    # else:
    #     servo.nod()

    # compliments → heart-eyes face for a few seconds
    if ("love you" in lower or "good job" in lower or "well done" in lower
            or words & {"cute", "awesome", "amazing", "beautiful"}):
        with state.lock:
            state.face_override       = "love"
            state.face_override_until = time.time() + FACE_OVERRIDE_SECS

    # try Groq first — fall back to local if anything fails
    reply = _ask_groq(text)

    if reply:
        print("[brain] Using Groq response")
        speak(reply)
    else:
        print("[brain] Groq failed — using local fallback")
        reply = _local_fallback(text)
        speak(reply)