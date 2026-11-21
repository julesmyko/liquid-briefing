"""'Sources differ' detector (rule based, free, no LLM).

Idea: two articles quote the SAME headline figure (the anchor, e.g. 'revenue forecast of $130 billion') but give a
DIFFERENT benchmark for it (the comparator: the consensus / analyst expectation / estimate). The comparison is precision-aware
('about $109 billion' and 'USD 109.10B' agree; 'USD 125.1B' and '$125.3 billion' do not). Works on English text and runs over the
whole week, independent of the story clusters.
"""
from __future__ import annotations
import re

MONEY = re.compile(r"(?:\$|USD\s?|US\$|€|EUR\s?)\s?(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s?(?P<unit>billion|bn|B|million|mn|M)?\b", re.I)
UNITS = {"billion": 1.0, "bn": 1.0, "b": 1.0, "million": 1e-3, "mn": 1e-3, "m": 1e-3}
CUE_BEFORE = re.compile(r"(expectations?|estimates?|consensus|expected|forecasts?|benchmark|FactSet|analysts?|forecast|projections?)\b[^$€\d]{0,22}$", re.I)
CUE_AFTER = re.compile(r"^\s*(consensus|expected|estimates?|forecast)\b", re.I)
CAPS_STOP = {"The", "Why", "What", "How", "Wall", "Street", "This", "That", "These", "With", "After", "Before", "Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December", "Evening", "Morning", "Key", "Here", "Its", "And", "But", "For", "Also", "Global", "Markets",
             "Stock", "Stocks", "Shares", "Company", "Third", "Fourth", "Second", "First", "Results", "Earnings", "Revenue", "Will", "Are", "Is",
             "USD", "EUR", "Nasdaq", "Dow", "Fed", "Federal", "Reserve", "Bank", "Five", "Things", "Know", "Opens", "Hours"}


def money_figures(sentence):
    out = []
    for m in MONEY.finditer(sentence):
        unit = (m.group("unit") or "").lower()
        if unit not in UNITS:
            continue
        num = m.group("num").replace(",", "")
        dec = len(num.split(".")[1]) if "." in num else 0
        before = sentence[max(0, m.start() - 30):m.start()]
        after = sentence[m.end():m.end() + 16]
        comparator = bool(CUE_BEFORE.search(before) or CUE_AFTER.search(after))
        out.append({"pos": m.start(), "raw": m.group(0).strip(), "value": float(num) * UNITS[unit], "dec": dec, "comparator": comparator})
    return out


def equal(a, b):
    """Precision-aware equality in billions: compare at the precision of the less precise figure."""
    d = min(a["dec"], b["dec"])
    return abs(a["value"] - b["value"]) <= 10 ** (-d) + 1e-9  # one unit of the less precise figure (rounding or truncation)


def entities(sentence, headline):
    toks = set(re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", sentence + " " + (headline or "")))
    return {t for t in toks if t not in CAPS_STOP}


def short_sentence(text, raw, split_sentences, fallback):
    """The shortest clean sentence of the article that contains the benchmark figure (good for speech and for display)."""
    cands = [x.strip() for x in split_sentences(text) if raw in x and 35 <= len(x.strip()) <= 320]
    return min(cands, key=len) if cands else fallback


def detect(articles, split_sentences):
    """articles: dicts with id, outlet(spoken), lang, headline, date, permalink, text. Returns a list of disagreements."""
    recs = []
    for a in articles:
        if a.get("lang", "en") != "en":
            continue
        for s in split_sentences(a["text"]):
            figs = money_figures(s)
            comps = [f for f in figs if f["comparator"]]
            anchors = [f for f in figs if not f["comparator"]]
            if comps and anchors:
                ents = entities(s, a["headline"])
                for c in comps:  # each benchmark belongs to the nearest figure before it (else after it)
                    before = [x for x in anchors if x["pos"] < c["pos"]]
                    an = max(before, key=lambda x: x["pos"]) if before else min(anchors, key=lambda x: x["pos"])
                    if abs(c["value"] - an["value"]) / max(an["value"], 1e-9) < 0.15:  # a benchmark is close to its anchor
                        recs.append({"art": a, "sent": s.strip(), "anchor": an, "comp": c, "ents": ents})
    found = {}
    for i, r in enumerate(recs):
        for q in recs[i + 1:]:
            if r["art"]["id"] == q["art"]["id"] or not (r["ents"] & q["ents"]) or not equal(r["anchor"], q["anchor"]):
                continue
            if equal(r["comp"], q["comp"]):
                continue
            key = (round(r["anchor"]["value"]), tuple(sorted(r["ents"] & q["ents"]))[:1])
            g = found.setdefault(key, {"anchor": r["anchor"]["raw"], "entity": sorted(r["ents"] & q["ents"])[0], "members": {}})
            for x in (r, q):
                k = (x["art"]["id"], round(x["comp"]["value"], 6))
                g["members"].setdefault(k, x)
    out = []
    for g in found.values():
        mem = sorted(g["members"].values(), key=lambda x: (x["art"]["date"], x["art"]["id"]))
        vals = []
        for x in mem:  # one entry per distinct benchmark value, best sourced first
            if not any(v["value"] == x["comp"]["value"] and v["outlet"] == x["art"]["outlet"] for v in vals):
                vals.append({"raw": x["comp"]["raw"], "value": x["comp"]["value"], "outlet": x["art"]["outlet"], "article_id": x["art"]["id"],
                             "permalink": x["art"]["permalink"], "headline": x["art"]["headline"], "date": x["art"]["date"][:10],
                             "sentence": short_sentence(x["art"]["text"], x["comp"]["raw"], split_sentences, x["sent"])})
        if len({v["value"] for v in vals}) >= 2:
            out.append({"entity": g["entity"], "anchor": g["anchor"], "benchmarks": vals,
                        "cross_outlet": len({v["outlet"] for v in vals}) > 1})
    out.sort(key=lambda c: (not c["cross_outlet"], -len(c["benchmarks"])))
    return out
