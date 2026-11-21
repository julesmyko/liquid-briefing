"""Load articles, align Invezz EN/NL/DE twins, group articles into stories, extract facts.
All steps here are local and free (rules + TF-IDF): no LLM, no API."""
from __future__ import annotations
import json, re
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from lb_numbers import extract_numbers, dedupe_numbers

FEEDS = ["invezz_en", "invezz_nl", "invezz_de", "ibtimes_uk", "actionforex", "zacks"]
SPOKEN = {"International Business Times UK": "IBTimes UK", "Zacks Investment Research": "Zacks"}
STOP = set("""the and for with from this that into over after says said say year years also more most not but than then
such about their there which would could should have has had were was are been will its his her they them what when
who how why can may new one two out all any per via amid""".split())
BOILER = re.compile(r"(zacks rank|zacks\.com|click to get|free report|want the latest|sign up|subscribe|follow us|read more|"
                    r"disclosure:|past performance|all rights reserved|wikimedia|getty images|cc by|image:|photo:|copyright|"
                    r"newsletter|investing involves risk|visit zacks|download our|reuters/|\(reuters\)|\bsource:)", re.I)
ABBR = {"mr", "mrs", "ms", "dr", "inc", "corp", "co", "ltd", "st", "vs", "jr", "sr", "no", "etc", "approx", "bv", "nv",
        "ca", "bijv", "dhr", "mevr", "prof", "sen", "rep", "gov", "gen", "u.s", "u.k", "e.g", "i.e"}


def spoken_name(outlet):
    name = SPOKEN.get(outlet, outlet)
    return re.sub(r"\s*[-–]\s*(Dutch|German|Deutsch|Nederlands)$", "", name, flags=re.I)


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def split_sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"”’]))\s+(?=[A-Z\"“‘$€£(0-9])", text)
    out = []
    for p in parts:
        if out:
            last = out[-1].rstrip(".").split(" ")[-1].lower()
            if last in ABBR or re.fullmatch(r"[A-Z]", out[-1].rstrip(".").split(" ")[-1] or "x"):
                out[-1] = out[-1] + " " + p
                continue
        out.append(p)
    return out


def load_articles(data_dir, since):
    arts = []
    for feed in FEEDS:
        path = Path(data_dir) / (feed + ".jsonl")
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    x = json.loads(line)
                except json.JSONDecodeError:
                    continue
                dt = parse_dt(x["date"])
                if dt < since:
                    continue
                outlet = (x.get("publication") or {}).get("name") or feed
                arts.append({"id": x["$id"], "feed": feed, "outlet": outlet, "spoken_outlet": spoken_name(outlet),
                             "lang": x.get("language") or "en", "date": x["date"], "dt": dt,
                             "author": (x.get("source") or "").strip(), "headline": x.get("headline") or "",
                             "excerpt": x.get("excerpt") or "", "text": x.get("text_content") or x.get("excerpt") or "",
                             "permalink": x.get("permalink"), "cats": x.get("provider_categories") or []})
    return arts


def align_invezz(arts, max_minutes=15):
    """Attach NL/DE Invezz articles to their English twin (same author, closest time <= 15 min, one-to-one)."""
    en = [a for a in arts if a["feed"] == "invezz_en"]
    pairs = []
    for t in arts:
        if t["feed"] in ("invezz_nl", "invezz_de"):
            for e in en:
                d = abs((t["dt"] - e["dt"]).total_seconds())
                if e["author"] == t["author"] and d <= max_minutes * 60:
                    pairs.append((d, t["id"], e["id"]))
    pairs.sort()
    used_t, used_slot, twins = set(), set(), {}
    by_id = {a["id"]: a for a in arts}
    for d, tid, eid in pairs:
        lang = by_id[tid]["lang"]
        if tid in used_t or (eid, lang) in used_slot:
            continue
        used_t.add(tid)
        used_slot.add((eid, lang))
        twins.setdefault(eid, {})[lang] = by_id[tid]
    return twins, used_t


def _tokens(a):
    base = (a["headline"] + " ") * 2 + a["excerpt"] + " " + a["text"][:600]
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9\-&']+", base.lower()) if w not in STOP and len(w) > 2]
    ents = ["ent:" + e.lower() for e in re.findall(r"\b[A-Z][a-zA-Z&]{2,}\b|\b[A-Z]{2,6}\b", a["headline"] + " " + a["excerpt"] + " " + a["text"][:600])]
    return words + ents + ents


def tfidf_matrix(arts):
    docs = [_tokens(a) for a in arts]
    vocab, df = {}, {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    for w, c in df.items():
        if c >= 1:
            vocab[w] = len(vocab)
    n = len(docs)
    M = np.zeros((n, len(vocab)), dtype=np.float32)
    for i, d in enumerate(docs):
        for w in d:
            M[i, vocab[w]] += 1
    M = np.log1p(M)
    idf = np.log((n + 1) / (np.array([df[w] for w in vocab], dtype=np.float32) + 1)) + 1
    M *= idf
    M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return M


def rare_entity_sets(arts, max_df=12):
    """Specific names (tickers, people, companies) used by few articles: two articles about one event must share one."""
    ents = [set(t for t in _tokens(a) if t.startswith("ent:")) for a in arts]
    df = {}
    for e in ents:
        for t in e:
            df[t] = df.get(t, 0) + 1
    return [set(t for t in e if df[t] <= max_df) for e in ents]


def gram(M):
    """M @ M.T in float64. Some macOS numpy builds (Accelerate BLAS) raise spurious floating-point warnings or even bad
    values on float32 matmul, so the result is validated and recomputed without BLAS if it looks wrong."""
    M64 = M.astype(np.float64)
    with np.errstate(all="ignore"):
        S = M64 @ M64.T
    ok = bool(np.isfinite(S).all()) and float(S.max()) <= 1.0001 and float(S.min()) >= -1e-3 and np.allclose(S, S.T, atol=1e-6)
    if not ok:
        S = np.einsum("ik,jk->ij", M64, M64)
    return S


def similarity(arts, M, require_rare_entity=True):
    S = gram(M)
    hrs = np.array([a["dt"].timestamp() for a in arts])
    gap = np.abs(hrs[:, None] - hrs[None, :]) / 3600.0
    S = S * np.where(gap <= 36, 1.0, np.where(gap <= 72, 0.8, 0.6))
    if require_rare_entity:
        rare = rare_entity_sets(arts)
        allow = np.zeros_like(S)
        for i in range(len(arts)):
            for j in range(i, len(arts)):
                if rare[i] & rare[j]:
                    allow[i, j] = allow[j, i] = 1.0
        S = S * allow
    return S


def cluster(arts, M, threshold=0.30, window_hours=96, S=None):
    """Single pass in time order. Article joins the most similar cluster (0.7*max + 0.3*mean) if >= threshold."""
    order = sorted(range(len(arts)), key=lambda i: arts[i]["dt"])
    if S is None:
        S = similarity(arts, M)
    clusters = []
    for i in order:
        best, best_s = None, 0.0
        for c in clusters:
            if (arts[i]["dt"] - arts[c[-1]]["dt"]) > timedelta(hours=window_hours):
                continue
            sims = S[i, c]
            s = 0.7 * float(sims.max()) + 0.3 * float(sims.mean())
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= threshold:
            best.append(i)
        else:
            clusters.append([i])
    return clusters, S


def merge_clusters(arts, M, clusters, threshold=0.42, window_hours=96):
    """Second pass: merge sagas whose centroids are close (e.g. one CEO exit covered from several angles)."""
    cl = [list(c) for c in clusters]
    def cen(c):
        v = M[c].mean(axis=0)
        return v / (np.linalg.norm(v) + 1e-9)
    while True:
        cens = [cen(c) for c in cl]
        best, pair = 0.0, None
        for i in range(len(cl)):
            for j in range(i + 1, len(cl)):
                gap = abs((min(arts[k]["dt"] for k in cl[j]) - max(arts[k]["dt"] for k in cl[i])).total_seconds()) if True else 0
                a_lo, a_hi = min(arts[k]["dt"] for k in cl[i]), max(arts[k]["dt"] for k in cl[i])
                b_lo, b_hi = min(arts[k]["dt"] for k in cl[j]), max(arts[k]["dt"] for k in cl[j])
                if b_lo > a_hi + timedelta(hours=window_hours) or a_lo > b_hi + timedelta(hours=window_hours):
                    continue
                sim = float(cens[i] @ cens[j])
                if sim > best:
                    best, pair = sim, (i, j)
        if pair is None or best < threshold:
            return cl
        i, j = pair
        cl[i] = cl[i] + cl[j]
        del cl[j]


def build_stories(data_dir, since, threshold=0.22, embeddings=None, merge_threshold=0.0):
    arts = load_articles(data_dir, since)
    twins, twin_ids = align_invezz(arts)
    base = [a for a in arts if a["id"] not in twin_ids]
    M = embeddings(base) if embeddings else tfidf_matrix(base)
    clusters, _ = cluster(base, M, threshold)
    if merge_threshold:
        clusters = merge_clusters(base, M, clusters, merge_threshold)
    stories = []
    for c in clusters:
        members = [base[i] for i in c]
        members.sort(key=lambda a: a["dt"])
        stories.append({"members": members, "twins": {m["id"]: twins.get(m["id"], {}) for m in members}})
    return stories, arts, twins


def article_facts(art, cap=12):
    """Candidate facts of one article = its best sentences, each with the figures it contains (cheap, rule based)."""
    out = []
    for i, s in enumerate(split_sentences(art["text"])[:45]):
        if len(s) < 35 or len(s) > 420 or BOILER.search(s):
            continue
        nums = dedupe_numbers(extract_numbers(s, art["lang"]))
        score = 3 if i == 0 else 2 if i < 3 else 1 if i < 6 else 0
        if any(n["kind"] in ("pct", "bp") or n["value"] >= 1000 for n in nums if not n["exempt"]):
            score += 2
        elif nums:
            score += 0.5
        if 60 <= len(s) <= 300:
            score += 1
        out.append({"sent": s, "pos": i, "numbers": nums, "score": score, "article_id": art["id"], "lang": art["lang"],
                    "outlet": art["spoken_outlet"], "headline": art["headline"], "permalink": art["permalink"],
                    "date": art["date"]})
    out.sort(key=lambda f: (-f["score"], f["pos"]))
    return out[:cap]


def _words(s):
    return set(w for w in re.findall(r"[a-zà-ÿ0-9]{4,}", s.lower()) if w not in STOP)


def pick_story_facts(story, lang, n_facts, per_article=None):
    """Native-language article when it exists (Invezz twin), else the article's own language. Dedupes across outlets."""
    pools = []
    if per_article is None:
        per_article = max(3, -(-n_facts // len(story["members"])))
    for m in story["members"]:
        art = story["twins"].get(m["id"], {}).get(lang) if lang != "en" else None
        art = art or m
        pools.append(article_facts(art))
    chosen, counts = [], {}
    # round-robin so every outlet is heard, best fact first
    idx = [0] * len(pools)
    while len(chosen) < n_facts and any(idx[i] < len(pools[i]) for i in range(len(pools))):
        for i, pool in enumerate(pools):
            if len(chosen) >= n_facts:
                break
            while idx[i] < len(pool):
                f = pool[idx[i]]
                idx[i] += 1
                if counts.get(f["article_id"], 0) >= per_article:
                    break
                w = _words(f["sent"])
                if any(len(w & _words(c["sent"])) / max(1, len(w | _words(c["sent"]))) > 0.55 for c in chosen):
                    continue
                chosen.append(f)
                counts[f["article_id"]] = counts.get(f["article_id"], 0) + 1
                break
    chosen.sort(key=lambda f: (f["date"], f["pos"]))
    return chosen


def find_conflicts(facts):
    """Possible disagreements: two outlets, very similar sentence, but disjoint key figures."""
    def keynums(f):
        return [n for n in f["numbers"] if not n["exempt"] and (n["kind"] in ("pct", "bp") or n["value"] >= 1000)]
    out = []
    for i, a in enumerate(facts):
        for b in facts[i + 1:]:
            if a["article_id"] == b["article_id"] or a["outlet"] == b["outlet"]:
                continue
            wa, wb = _words(a["sent"]), _words(b["sent"])
            if len(wa & wb) / max(1, len(wa | wb)) < 0.35:
                continue
            ka, kb = keynums(a), keynums(b)
            if ka and kb and not any(x["kind"] == y["kind"] and abs(x["value"] - y["value"]) < 1e-9 for x in ka for y in kb):
                out.append({"a": a["fact_id"], "b": b["fact_id"]})
    return out


def _hit(term, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) is not None


def select_stories(stories, profile, now):
    lang = profile.get("language", "en")
    topics = [t.lower() for t in profile.get("topics", [])]
    excl = [t.lower() for t in profile.get("exclude_topics", [])]
    prefs = [p.lower() for p in profile.get("preferred_outlets", [])]
    scored = []
    for s in stories:
        ms = s["members"]
        outlets = {m["outlet"] for m in ms}
        blob = " ".join(m["headline"] + " " + m["excerpt"][:300] + " " + " ".join(m["cats"]) for m in ms).lower()
        newest = max(m["dt"] for m in ms)
        age_days = (now - newest).total_seconds() / 86400.0
        recency = 1.5 * float(np.exp(-age_days / 4.0))
        importance = 4.0 * (len(outlets) - 1) + 0.7 * min(len(ms), 5) + recency
        match = sum(1 for t in topics if _hit(t, blob))
        pref = sum(1 for m in ms if any(p in m["outlet"].lower() or p in m["feed"] for p in prefs))
        native = 2.0 if lang != "en" and any(s["twins"][m["id"]].get(lang) for m in ms) else 0.0
        excluded = any(_hit(t, blob) for t in excl)
        score = importance + 3.0 * min(match, 3) + 2.0 * min(pref, 2) + native - (10 if excluded else 0)
        if topics and match == 0 and pref == 0:
            score -= 3
        scored.append((score, importance, s))
    scored.sort(key=lambda z: z[0], reverse=True)
    return scored[:profile.get("max_stories", 6)]
