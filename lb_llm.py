"""OpenAI + ElevenLabs calls (stdlib only), disk cache and cost log. Keys come from the environment or a local .env."""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"


def load_env(path=None):
    p = Path(path) if path else HERE / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class CostLog:
    """Every paid call is recorded (tokens / characters), cached calls are marked so spend vs. reference is clear."""
    def __init__(self):
        self.calls = []

    def add(self, **kw):
        self.calls.append(kw)

    def to_dict(self):
        tot = {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0, "tts_characters": 0}
        for c in self.calls:
            if c.get("cached"):
                continue
            tot["input_tokens"] += c.get("input_tokens") or 0 if c["step"] != "embeddings" else 0
            tot["output_tokens"] += c.get("output_tokens") or 0
            tot["embedding_tokens"] += (c.get("input_tokens") or 0) if c["step"] == "embeddings" else 0
            tot["tts_characters"] += c.get("characters") or 0
        return {"calls": self.calls, "billed_totals": tot}


def _post(url, body, headers, timeout=240, raw=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read() if raw else json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s from %s: %s" % (e.code, url.split("?")[0], e.read()[:600].decode("utf-8", "replace")))


def _hash(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:24]


def openai_text(system, user, step, cost, model=None, use_cache=True):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (put it in .env or export it).")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-6.2-sol")
    cf = CACHE / "llm" / (_hash(model, system, user) + ".json")
    if use_cache and cf.exists():
        d = json.loads(cf.read_text(encoding="utf-8"))
        cost.add(step=step, provider="openai", model=model, cached=True, input_tokens=d["in"], output_tokens=d["out"])
        return d["text"]
    body = {"model": model, "input": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    t0 = time.time()
    data = _post("https://api.openai.com/v1/responses", body,
                 {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    text = data.get("output_text")
    if not text:
        text = "\n".join(b.get("text", "") for it in data.get("output", []) for b in it.get("content", [])
                         if b.get("type") in ("output_text", "text"))
    if not text:
        raise RuntimeError("OpenAI returned no text: " + json.dumps(data)[:500])
    u = data.get("usage") or {}
    cost.add(step=step, provider="openai", model=model, cached=False, input_tokens=u.get("input_tokens"),
             output_tokens=u.get("output_tokens"), seconds=round(time.time() - t0, 1))
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"text": text, "in": u.get("input_tokens"), "out": u.get("output_tokens")}), encoding="utf-8")
    return text


def openai_embeddings(texts, cost, model="text-embedding-3-small"):
    """Optional backend for story grouping (default grouping is local TF-IDF, which is free). Untested here."""
    import numpy as np
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    cf = CACHE / "emb.json"
    store = json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else {}
    todo = [t for t in texts if _hash(model, t) not in store]
    for i in range(0, len(todo), 96):
        batch = todo[i:i + 96]
        d = _post("https://api.openai.com/v1/embeddings", {"model": model, "input": batch},
                  {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        for t, item in zip(batch, d["data"]):
            store[_hash(model, t)] = item["embedding"]
        cost.add(step="embeddings", provider="openai", model=model, cached=False,
                 input_tokens=(d.get("usage") or {}).get("total_tokens"))
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(store), encoding="utf-8")
    M = np.array([store[_hash(model, t)] for t in texts], dtype=np.float32)
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


def elevenlabs_tts(text, voice_id, out_path, cost, use_cache=True):
    """Text-to-speech through the ElevenLabs API. Long scripts are sent in chunks of whole paragraphs."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set (put it in .env or export it).")
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    out_path = Path(out_path)
    cf = CACHE / "tts" / (_hash(model, voice_id, text) + ".mp3")
    if use_cache and cf.exists():
        shutil.copyfile(cf, out_path)
        cost.add(step="tts", provider="elevenlabs", model=model, cached=True, characters=len(text))
        return out_path
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > 8500:
            chunks.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + para
    if cur:
        chunks.append(cur)
    audio = b""
    t0 = time.time()
    for c in chunks:
        audio += _post("https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128" % voice_id,
                       {"text": c, "model_id": model},
                       {"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, timeout=300, raw=True)
    out_path.write_bytes(audio)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_bytes(audio)
    cost.add(step="tts", provider="elevenlabs", model=model, cached=False, characters=len(text),
             seconds=round(time.time() - t0, 1))
    return out_path


def audio_seconds(path):
    """Duration of the MP3: ffprobe if installed, else macOS afinfo, else exact from size (output is constant 128 kbps)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        pass
    try:
        r = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, timeout=30)
        m = re.search(r"estimated duration:\s*([\d.]+)", r.stdout)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    try:
        return Path(path).stat().st_size * 8 / 128000.0
    except Exception:
        return None


def to_speech_text(script, lang):
    """Script -> text for the voice: no IDs, no markdown, headers become their own short paragraph."""
    pct = {"nl": " procent", "de": " Prozent"}.get(lang, " percent")
    t = re.sub(r"\s*\[s\d{2}f\d{2}\]", "", script)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = re.sub(r"\s*%", pct, t)
    out = []
    for para in [p.strip() for p in t.split("\n\n") if p.strip()]:
        if "\n" not in para and len(para.split()) <= 12 and not re.search(r"[.!?]$", para):
            para += "."
        out.append(re.sub(r"\s+", " ", para))
    return "\n\n".join(out)


HEUR = {
    "forex": ["forex", "fx", "currency", "usd", "eur", "yen", "fed", "ecb", "central bank", "inflation", "interest rate", "ppi", "cpi"],
    "crypto": ["crypto", "bitcoin", "ethereum", "solana", "xrp"],
    "stocks": ["stock", "stocks", "shares", "nasdaq", "dow", "earnings", "etf"],
    "ai": ["ai", "nvidia", "anthropic", "openai"],
    "savings": ["inflation", "interest rate", "ecb", "fed", "bank", "mortgage", "pension"],
    "general": ["trump", "senate", "court", "police", "war", "election", "world"],
}
KEYS = {"forex": r"forex|\bfx\b|currenc|trader|valuta|devies", "crypto": r"crypto|bitcoin|ethereum",
        "stocks": r"stock|share|invest|belegg|aandel|beurs|equit|anleger", "ai": r"\bai\b|artificial|tech|nvidia",
        "savings": r"pension|saving|spaar|mortgage|hypotheek|rente|retire", "general": r"general|news|nieuws|world|wereld|what happened|politic"}


def heuristic_profile(desc):
    d = desc.lower()
    lang = "nl" if re.search(r"\b(nederland|nederlands|dutch|utrecht|amsterdam|rotterdam|belegger|pensioen|spreekt nl)\b", d) else \
        "de" if re.search(r"\b(german|deutsch|berlin|münchen|anleger|frankfurt)\b", d) else "en"
    topics = []
    for k, pat in KEYS.items():
        if re.search(pat, d):
            topics += HEUR[k]
    topics = list(dict.fromkeys(topics)) or ["stocks", "inflation", "fed", "trump"]
    m = re.search(r"(\d+)\s*(?:min|minute|minutes|minuten)", d)
    prefs = []
    if re.search(KEYS["forex"], d):
        prefs.append("actionforex")
    if re.search(KEYS["general"], d) and not prefs:
        prefs.append("ibtimes")
    if re.search(KEYS["stocks"] + "|" + KEYS["crypto"] + "|" + KEYS["ai"], d):
        prefs.append("invezz")
    plain = bool(re.search(r"simple|plain|no jargon|beginner|doesn.t know|eenvoudig|geen jargon|teacher|retired|pensioen", d))
    return {"name": "wildcard", "language": lang, "description": desc, "topics": topics, "preferred_outlets": prefs,
            "max_stories": 4 if (m and int(m.group(1)) <= 4) else 5, "target_minutes": int(m.group(1)) if m else 5,
            "style": ("plain language, explain terms briefly, no jargon, calm tone" if plain else
                      "concise, assume market knowledge, figures first")}


LANG_DEFAULTS = {"en": {"voice_id": "I7qs7sGMuqqIuJ1AE3eT", "words_per_minute": 123},
                 "nl": {"voice_id": "8B6lPskx1bcErhNkFdqo", "words_per_minute": 119},
                 "de": {"voice_id": "x5q1BXyLc7tegNqnOvnx", "words_per_minute": 128}}


def apply_language(profile, language):
    """Force the briefing language (en|nl|de) and use the matching voice and pace. 'auto' keeps the detected language."""
    if language in LANG_DEFAULTS:
        profile["language"] = language
    profile.update({k: v for k, v in LANG_DEFAULTS.get(profile.get("language"), {}).items() if not profile.get(k) or language in LANG_DEFAULTS})
    return profile


def profile_from_description(desc, cost, use_llm=True, language="auto"):
    return apply_language(_profile_from_description(desc, cost, use_llm), language)


def _profile_from_description(desc, cost, use_llm=True):
    base = heuristic_profile(desc)
    if not (use_llm and os.environ.get("OPENAI_API_KEY")):
        return base
    system = ("Turn a listener description into a JSON object for a news-briefing system. Keys: language (en|nl|de), "
              "topics (8-14 lowercase keywords in English), exclude_topics (list), preferred_outlets (subset of "
              "['invezz','actionforex','ibtimes','zacks']), max_stories (3-7), target_minutes (2-10), style (one sentence). "
              "Return ONLY the JSON.")
    try:
        txt = openai_text(system, desc, "profile_from_description", cost)
        j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        base.update({k: v for k, v in j.items() if k in base or k in ("exclude_topics",)})
    except Exception as e:  # keep the rule-based profile
        base["profile_note"] = "LLM profile failed (%s); used rules" % str(e)[:80]
    return base
