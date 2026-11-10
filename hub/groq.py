"""AI through the Groq API (OpenAI-compatible chat endpoint): meal ideas, recipes, workouts,
Ask AI replies, lessons and more."""
from __future__ import annotations

import json
import re
import time

import requests

from .config import WORKOUT_TYPES, cfg

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
# Tried in this order if the configured model has been retired.
GROQ_PREFERRED = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
_state: dict = {}


def pick_model(key: str) -> str:
    """Ask Groq which models are live and pick a chat model."""
    r = requests.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Groq: could not list models (HTTP {r.status_code})")
    ids = [str(m.get("id", "")) for m in r.json().get("data", [])]
    chat = [i for i in ids if not re.search(r"whisper|tts|guard|embed|orpheus|compound|playai|distil", i, re.I)]
    pick = next((m for m in GROQ_PREFERRED if m in chat), None) or (sorted(chat)[0] if chat else None)
    if not pick:
        raise RuntimeError("Groq: no chat models available on this account")
    print(f"[groq] using model {pick} (available: {', '.join(chat)})")
    return pick


def current_model() -> str:
    return _state.get("model") or cfg("GROQ_MODEL", GROQ_DEFAULT_MODEL)


GROQ_RATE_TRIES = 3          # tries when Groq says the per-minute limit is reached (HTTP 429)
GROQ_MAX_WAIT_S = 60         # longest single wait before trying again


def rate_limit_wait(message: str, retry_after: str | None = None) -> float:
    """Seconds to wait after a 429, from Groq's 'try again in 1m2.5s / 862.5ms / 7s' or Retry-After."""
    m = re.search(r"try again in\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)(ms|s))?", message or "", re.I)
    if m and (m.group(1) or m.group(2)):
        secs = int(m.group(1) or 0) * 60
        if m.group(2):
            secs += float(m.group(2)) / (1000 if m.group(3).lower() == "ms" else 1)
        return min(GROQ_MAX_WAIT_S, round(secs + 0.5, 1))       # half a second to spare
    try:
        return min(GROQ_MAX_WAIT_S, float(retry_after)) if retry_after else 5.0
    except ValueError:
        return 5.0


def _post(key, model, messages, temperature, as_json):
    body = {"model": model, "temperature": temperature, "messages": messages}
    if as_json:
        body["response_format"] = {"type": "json_object"}
    for attempt in range(2):
        try:
            return requests.post(f"{GROQ_BASE}/chat/completions", json=body, timeout=90,
                                 headers={"Authorization": f"Bearer {key}"})
        except requests.RequestException:
            if attempt:
                raise
            time.sleep(1)


def request(messages: list[dict], temperature: float = 0.7, as_json: bool = False) -> str:
    """One chat completion; falls back to a live model if the configured one was retired."""
    key = cfg("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set in the app's secrets")
    model = current_model()
    t0 = time.time()
    print(f"[groq] request started (model {model})")
    r = _post(key, model, messages, temperature, as_json)
    body = _json(r)
    for _ in range(GROQ_RATE_TRIES - 1):
        if r.status_code != 429:
            break
        wait = rate_limit_wait(str(((body or {}).get("error") or {}).get("message", "")), r.headers.get("retry-after"))
        print(f"[groq] per-minute limit reached; waiting {wait:g}s and trying again")
        time.sleep(wait)
        r = _post(key, model, messages, temperature, as_json)
        body = _json(r)
    err = (body.get("error") or {}) if isinstance(body, dict) else {}
    msg = str(err.get("message", ""))
    if r.status_code in (400, 404) and re.search("model", str(err.get("code", "")) + msg, re.I) and \
            re.search(r"not exist|not found|decommission|deprecat|no access|do not have access", msg, re.I):
        print(f"[groq] model {model} unavailable: {msg}")
        model = pick_model(key)
        _state["model"] = model
        print(f"[groq] retrying with {model} (set GROQ_MODEL = \"{model}\" in secrets to make this permanent)")
        r = _post(key, model, messages, temperature, as_json)
        body = _json(r)
    if r.status_code >= 300:
        raise RuntimeError(f"Groq error (HTTP {r.status_code}, model {model}): "
                           f"{((body or {}).get('error') or {}).get('message', 'unknown error')}")
    print(f"[groq] response received in {time.time() - t0:.1f}s")
    return ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _json(r):
    try:
        return r.json()
    except ValueError:
        return {}


def chat_json(system_prompt: str, user_prompt: str, temperature: float = 0.8) -> dict:
    txt = request([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                  temperature=temperature, as_json=True)
    return json.loads(txt)


def chat_reply(history: list[dict]) -> str:
    """Free-form answer for the Ask AI page. history: [{role, content}]."""
    sys = ("You are a friendly, practical assistant for a busy family. "
           "Answer clearly and concisely. Use short paragraphs or bullet lists when helpful. "
           "For medical, legal or financial questions, give general information and suggest "
           "checking with a professional when it matters.")
    msgs = [{"role": "system", "content": sys}] + [{"role": h["role"], "content": h["content"]} for h in history]
    return request(msgs, temperature=0.6)


def _flat(x) -> str:
    if isinstance(x, (list, tuple)):
        return " ".join(_flat(i) for i in x)
    if isinstance(x, dict):
        return " ".join(_flat(v) for v in x.values())
    return "" if x is None else str(x)


MEAL_JSON_SPEC = ('Each meal is an object with keys: '
                  '"name" (string), "description" (one sentence), "prep_minutes" (integer), '
                  '"healthy" (boolean), "ingredients" (array of strings with quantities, e.g. "1 lb chicken thighs"), '
                  '"instructions" (string, numbered steps separated by newlines).')


def clean_meal(m: dict) -> dict:
    """Normalise one meal object coming back from the model."""
    ing = [_flat(x).strip() for x in (m.get("ingredients") or [])]
    instr = m.get("instructions") or ""
    if isinstance(instr, list):
        instr = "\n".join(_flat(x) for x in instr)
    try:
        prep = int(m.get("prep_minutes")) if m.get("prep_minutes") not in (None, "") else None
    except (TypeError, ValueError):
        prep = None
    healthy = m.get("healthy", True)
    return {"name": str(m.get("name") or "Untitled meal"), "description": str(m.get("description") or ""),
            "prep_minutes": prep, "healthy": healthy is True or str(healthy).lower() == "true",
            "ingredients": [i for i in ing if i], "instructions": str(instr)}


def meal_ideas(n: int = 4, request_text: str = "", healthy: bool = True, avoid: str = "",
               household: str = "", recent: list[str] | None = None, seasonal: str = "") -> list[dict]:
    sys = ("You are a practical family meal planner. Reply with JSON only, no prose. "
           'Return {"meals": [...]} with exactly the requested number of meals. ' + MEAL_JSON_SPEC)
    parts = [f"Suggest {int(n)} different meal ideas.",
             f"About our household: {household}" if household else "",
             "Every meal must be a genuinely healthy option: vegetables, whole grains or lean protein, not fried."
             if healthy else "",
             f"We are in the mood for: {request_text}" if request_text else "",
             f"Avoid: {avoid}" if avoid else "", seasonal or "",
             ("We recently had these, so suggest something different: " + "; ".join((recent or [])[:15]))
             if recent else ""]
    out = chat_json(sys, "\n".join(parts))
    return [clean_meal(m) for m in (out.get("meals") or [])]


def recipe_for(meal_name: str, household: str = "", healthy: bool = True) -> dict:
    sys = ("You are a practical family cook. Reply with JSON only, no prose. "
           "Return one meal object for the dish the user names. " + MEAL_JSON_SPEC)
    usr = "\n".join([f"Dish: {meal_name}", f"About our household: {household}" if household else "",
                     "Prefer a healthier version of the dish where it is easy to do." if healthy else ""])
    out = chat_json(sys, usr, temperature=0.4)
    if out.get("meals"):
        out = out["meals"][0]
    return clean_meal(out)


def workout(wtype: str, minutes: int, intensity: str, equipment: list[str] | None = None, focus: str = "") -> dict:
    sys = ("You are a certified personal trainer writing a single workout for a busy parent. Reply with JSON only: "
           '{"title": string, "workout_type": string, "duration_min": integer, "intensity": string, '
           '"summary": one sentence, "steps": [strings, each one block with sets/reps or time/pace, '
           "including a warm-up first and a cool-down last]}. "
           "Keep it safe and realistic for the stated intensity.")
    usr = "\n".join([f"Type: {wtype}. Time available: {int(minutes)} minutes total. Intensity: {intensity}.",
                     "Equipment: " + (", ".join(equipment) if equipment else "none (bodyweight only)"),
                     f"Focus or avoid: {focus}" if focus else ""])
    w = chat_json(sys, usr, temperature=0.7)
    steps = [_flat(x) for x in (w.get("steps") or [])]
    try:
        dur = int(w.get("duration_min") or minutes)
    except (TypeError, ValueError):
        dur = int(minutes)
    details = "\n".join(([w["summary"]] if w.get("summary") else []) + [f"{i}. {s}" for i, s in enumerate(steps, 1)])
    return {"title": str(w.get("title") or f"{intensity} {wtype}"),
            "type": wtype if wtype in WORKOUT_TYPES else "Other",
            "duration_min": dur, "intensity": intensity, "details": details}
