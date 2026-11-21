#!/usr/bin/env python3
"""Liquid Briefing v2: news -> verified facts -> personal audio briefing.

Cheap steps (local, free): parsing, Invezz EN/NL/DE alignment, TF-IDF story grouping, rule-based fact extraction,
ranking, the trust audit.  Paid steps: ONE script-writing LLM call per briefing (+1 repair if the audit finds problems)
and ElevenLabs text-to-speech.  Article text never leaves the machine except the few selected fact sentences.
"""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lb_llm
from lb_audit import parse_script, audit_blocks, rebuild, counters, normalize_ids
from lb_stories import build_stories, select_stories, pick_story_facts, find_conflicts, split_sentences
from lb_numbers import extract_numbers, dedupe_numbers
import lb_disagree
from generate_source_page import render_page

LANG_NAME = {"en": "English", "nl": "Dutch", "de": "German"}
DISCLOSURE = {"en": "This briefing was written by AI and is read by a synthetic voice.",
              "nl": "Deze briefing is gemaakt met AI en wordt voorgelezen door een synthetische stem.",
              "de": "Dieses Briefing wurde mit KI erstellt und von einer synthetischen Stimme gesprochen."}

SYSTEM = """You write the script of a spoken news briefing for ONE listener. It will be read aloud by a synthetic voice.

LISTENER: {listener}
LANGUAGE: write the entire script in {language}.
LENGTH: about {words} words (between {lo} and {hi}). Cover every story, spending more time on the first ones.
STYLE: {style}

FORMAT
- Plain text. First line, exactly: {disclosure}
- Then for each story: a header line like **Short title** (the title must contain NO digits), then its sentences.
- Last line: one short closing sentence (max 10 words, no figures, no source).

HARD RULES (a script that breaks them is rejected by an automatic audit, and rejected sentences are deleted)
1. Use ONLY the supplied facts. Add no number, name, date, cause, forecast or background of your own.
2. EVERY sentence about the news ends with the IDs of the facts it uses, before the final punctuation, e.g. "... [s01f02]." or "... [s01f02][s01f05]." No other sentence may be without IDs (except the disclosure and the closing line).
3. Write each figure as DIGITS, exactly as supplied. Never round, convert or spell out a figure ("0,3 procent", not "drie tiende"). Use a decimal comma in Dutch and German. Do not write counts that are not in the facts as digits; spell those out in words.
4. Paraphrase. Never copy 8 or more consecutive words from a fact.
5. Name the outlet in words at the start of each story and whenever the source changes, NOT in every sentence (the IDs already carry the source). If two outlets give different figures or claims about the same thing (see possible_conflicts), say plainly that the sources differ, give each outlet's figure with its ID, and do not decide which one is right.
6. Link cause and reaction (for example a data release and the market move) only when both are in the supplied facts of the same story.
7. Inform, do not advise: no buy/sell/hold, no personal predictions, no "you should".
8. Written for the ear: short sentences, one idea each, no lists, no parentheses, no abbreviations the listener would not say aloud."""


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


DIS_HEADLINE = {"en": "%s: sources differ on the analyst benchmark",
                "nl": "%s: bronnen verschillen over de analistenverwachting",
                "de": "%s: Quellen weichen bei der Analystenerwartung ab"}


def disagreement_story(dis, by_id, twins):
    """A 'sources differ' finding as its own story: members = the articles that give the differing benchmarks."""
    members = [by_id[i] for i in dict.fromkeys(b["article_id"] for b in dis["benchmarks"]) if i in by_id]
    return {"members": members, "twins": {m["id"]: twins.get(m["id"], {}) for m in members}, "disagreement": dis}


def disagreement_facts(dis):
    out = []
    for b in dis["benchmarks"][:3]:  # each differing benchmark as its own sourced fact
        out.append({"sent": b["sentence"], "pos": 0, "numbers": dedupe_numbers(extract_numbers(b["sentence"], "en")), "score": 9,
                    "article_id": b["article_id"], "lang": "en", "outlet": b["outlet"], "headline": b["headline"],
                    "permalink": b["permalink"], "date": b["date"] + "T00:00:00+00:00"})
    return out


def build_selection(profile, data_dir, since, threshold=0.22, embeddings=None):
    lang = profile.get("language", "en")
    stories, arts, twins = build_stories(data_dir, since, threshold, embeddings=embeddings)
    now = max(a["dt"] for a in arts)
    by_id = {a["id"]: a for a in arts}
    stories = stories + [disagreement_story(d, by_id, twins) for d in lb_disagree.detect(arts, split_sentences)]
    ranked = select_stories(stories, profile, now)
    words = profile.get("target_minutes", 6) * profile.get("words_per_minute", 110)
    per_story = max(60, (words - 40) / max(1, len(ranked)))
    n_facts = clamp(round(per_story / 22), 3, 9)
    selected = []
    for rank, (score, importance, s) in enumerate(ranked, 1):
        dis = s.get("disagreement")
        facts = disagreement_facts(dis) if dis else pick_story_facts(s, lang, n_facts)
        if not facts:
            continue
        sid = "s%02d" % (len(selected) + 1)
        for k, f in enumerate(facts, 1):
            f["fact_id"] = "%sf%02d" % (sid, k)
        first = s["members"][0]
        native = next((s["twins"][m["id"]][lang] for m in s["members"] if lang != "en" and s["twins"].get(m["id"], {}).get(lang)), None)
        if dis:
            headline = DIS_HEADLINE.get(lang, DIS_HEADLINE["en"]) % dis["entity"]
            conflicts = [{"a": facts[0]["fact_id"], "b": f["fact_id"], "note": "%s %s: the benchmark differs, %s (%s) vs %s (%s)" % (
                dis["entity"], dis["anchor"], dis["benchmarks"][0]["raw"], dis["benchmarks"][0]["outlet"], dis["benchmarks"][i + 1]["raw"],
                dis["benchmarks"][i + 1]["outlet"])} for i, f in enumerate(facts[1:])]
        else:
            headline, conflicts = (native or first)["headline"], find_conflicts(facts)
        used = {f.get("article_id") for f in facts}
        group = [{"article_id": m["id"], "outlet": m["spoken_outlet"], "headline": m["headline"], "permalink": m["permalink"],
                  "date": m["date"][:10], "lang": m["lang"],
                  "cited": bool(m["id"] in used or any((t or {}).get("id") in used for t in s["twins"].get(m["id"], {}).values()))}
                 for m in sorted(s["members"], key=lambda x: x["date"])]
        selected.append({"story_id": sid, "headline": headline, "facts": facts, "group": group,
                         "outlets": sorted({f["outlet"] for f in facts}), "articles_in_story": len(s["members"]),
                         "score": round(score, 2), "importance": round(importance, 2),
                         "conflicts": conflicts})
    meta = {"articles_in_window": len(arts), "chars_in_window": sum(len(a["text"]) for a in arts),
            "stories_total": len(stories), "twins_aligned": sum(len(v) for v in twins.values()),
            "target_words": words, "facts_per_story": n_facts}
    return selected, meta


def speakable(t):
    """'USD 125.1B' -> 'USD 125.1 billion' so the model writes a figure the voice can read ('125,1 miljard'), never a spoken 'B'."""
    return re.sub(r"(?<=\d)B\b", " billion", t)


def llm_payload(selected):
    return json.dumps([{"story_id": s["story_id"], "headline": s["headline"],
                        "facts": [{"id": f["fact_id"], "outlet": f["outlet"], "date": f["date"][:10], "text": speakable(f["sent"]),
                                   "figures": [speakable(n["raw"]) for n in f["numbers"] if not n["exempt"]]} for f in s["facts"]],
                        "possible_conflicts": s["conflicts"]} for s in selected], ensure_ascii=False)


def system_prompt(profile, target_words):
    lang = profile.get("language", "en")
    listener = profile.get("description") or profile.get("name", "general listener")
    return SYSTEM.format(listener=listener, language=LANG_NAME.get(lang, lang), words=target_words,
                         lo=int(target_words * 0.9), hi=int(target_words * 1.1),
                         style=profile.get("style", "clear and neutral"), disclosure=DISCLOSURE.get(lang, DISCLOSURE["en"]))


def write_and_audit(profile, selected, target_words, cost, use_cache, mock_script=None):
    """Draft -> audit -> (one repair with the exact failures) -> delete what still fails."""
    lang = profile.get("language", "en")
    facts = {f["fact_id"]: f for s in selected for f in s["facts"]}
    system, user = system_prompt(profile, target_words), llm_payload(selected)
    history, caught = [], {"unsupported_figures": 0, "invalid_sentences": 0, "attempts": 0}
    draft = Path(mock_script).read_text(encoding="utf-8") if mock_script else lb_llm.openai_text(system, user, "script", cost, use_cache=use_cache)
    for attempt in (1, 2):
        caught["attempts"] = attempt
        blocks = parse_script(draft)
        results = audit_blocks(blocks, facts, lang)
        bad = [r for r in results if not r["passed"]]
        words = len(re.findall(r"\w+", re.sub(r"\[s\d{2}f\d{2}\]", "", draft)))
        history.append({"attempt": attempt, "failed": len(bad), "words": words})
        caught["invalid_sentences"] += len(bad)
        caught["unsupported_figures"] += sum(1 for r in bad for x in r["reasons"] if x.startswith(("unsupported_number", "figure_written")))
        short = words < 0.75 * target_words
        if attempt == 2 or mock_script or not (bad or short) or not os.environ.get("OPENAI_API_KEY"):
            break
        notes = ["- %s -> %s" % (r["sentence"][:140], "; ".join(r["reasons"])) for r in bad[:10]]
        if short:
            notes.append("- The script has %d words; it must have about %d. Use more of the supplied facts." % (words, target_words))
        draft = lb_llm.openai_text(system, user + "\n\nPREVIOUS DRAFT (rejected by the audit):\n" + draft +
                                   "\n\nPROBLEMS TO FIX (rewrite the whole script, change nothing else):\n" + "\n".join(notes),
                                   "script_repair", cost, use_cache=use_cache)
    final_text = rebuild(blocks, results)
    final_results = audit_blocks(parse_script(final_text), facts, lang)
    return final_text, final_results, results, caught, history, facts


def run_briefing(profile, out_dir, data_dir=HERE, since="2026-11-13", no_audio=False, use_cache=True, mock_script=None,
                 facts_only=False, embed="tfidf", threshold=0.22):
    lb_llm.load_env()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cost = lb_llm.CostLog()
    lang = profile.get("language", "en")
    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    emb = None
    if embed == "openai":
        emb = lambda base: lb_llm.openai_embeddings([a["headline"] + ". " + a["excerpt"] for a in base], cost)
    selected, meta = build_selection(profile, data_dir, since_dt, threshold, emb)
    (out / "facts.json").write_text(json.dumps({"profile": profile, "meta": meta, "stories": [
        {**s, "facts": [{k: v for k, v in f.items() if k != "dt"} for f in s["facts"]]} for s in selected]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if facts_only:
        return {"stories": len(selected), "facts": sum(len(s["facts"]) for s in selected), "meta": meta}
    final, final_res, first_res, caught, history, facts = write_and_audit(profile, selected, meta["target_words"], cost, use_cache, mock_script)
    (out / "script.txt").write_text(final, encoding="utf-8")
    readable = lb_llm.to_speech_text(final, lang)
    (out / "script_readable.txt").write_text(readable, encoding="utf-8")
    cnt = counters(final_res)
    cited = []
    for r in final_res:
        for i in r["fact_ids"]:
            if i not in cited and i in facts:
                cited.append(i)
    claims = []
    for i in cited:
        f = facts[i]
        words = f["sent"].split()
        pos = next((k for k, w in enumerate(words) if re.search(r"\d", w)), 0)
        a = max(0, min(pos - 6, len(words) - 14))
        claims.append({"fact_id": i, "outlet": f["outlet"], "headline": f["headline"], "permalink": f["permalink"],
                       "article_id": f["article_id"], "lang": f["lang"], "date": f["date"],
                       "snippet": ("… " if a else "") + " ".join(words[a:a + 14]) + (" …" if a + 14 < len(words) else ""),
                       "numbers": [n["raw"] for n in f["numbers"] if not n["exempt"]]})
    all_conf = [c for s in selected for c in s["conflicts"]]
    counters_full = {**cnt, "facts_supplied": len(facts), "facts_cited": len(cited), "stories": len(selected),
                     "sentences_dropped": caught["invalid_sentences"] if caught["attempts"] == 1 else
                     sum(1 for r in first_res if not r["passed"]),
                     "figures_caught_before_speech": caught["unsupported_figures"], "llm_attempts": caught["attempts"],
                     "sources_differ_flags": len(all_conf)}
    sources = {"profile": {k: profile.get(k) for k in ("name", "language", "description", "target_minutes")},
               "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "counters": counters_full,
               "claims": claims, "conflicts": all_conf, "stories": [{"story_id": s["story_id"], "headline": s["headline"],
               "outlets": s["outlets"], "group": s.get("group", [])} for s in selected]}
    audit = {"passed": all(r["passed"] for r in final_res), "history": history, "sentences": final_res,
             "dropped": [{"sentence": r["sentence"], "reasons": r["reasons"]} for r in first_res if not r["passed"]]}
    (out / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "script_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "sources.html").write_text(render_page(sources, audit, "Briefing: " + (profile.get("name") or "briefing")), encoding="utf-8")
    spoken_words = len(readable.split())
    result = {"out_dir": str(out), "stories": len(selected), "spoken_words": spoken_words,
              "estimated_minutes": round(spoken_words / profile.get("words_per_minute", 110), 1),
              "counters": counters_full, "audit_passed": audit["passed"], "audio": None}
    if cnt["claim_sentences"] < 3:
        result["error"] = "Too few verified sentences; no audio generated."
    elif not no_audio:
        mp3 = lb_llm.elevenlabs_tts(readable, profile.get("voice_id"), out / "briefing.mp3", cost, use_cache)
        secs = lb_llm.audio_seconds(mp3)
        result["audio"] = str(mp3)
        result["audio_minutes"] = round(secs / 60, 2) if secs else None
        if secs:
            result["measured_words_per_minute"] = round(spoken_words / (secs / 60))
    c = cost.to_dict()
    c["meta"] = meta
    (out / "cost.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    result["billed_totals"] = c["billed_totals"]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="profile JSON file")
    ap.add_argument("--describe", help="plain-language listener description (wildcard)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--data-dir", default=str(HERE))
    ap.add_argument("--since", default="2026-11-13")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--facts-only", action="store_true", help="stop after story grouping and fact extraction (free)")
    ap.add_argument("--mock-script", help="use this script file instead of calling the LLM (testing)")
    ap.add_argument("--embed", choices=["tfidf", "openai"], default="tfidf")
    a = ap.parse_args()
    lb_llm.load_env()
    if a.describe:
        profile = lb_llm.profile_from_description(a.describe, lb_llm.CostLog())
    elif a.profile:
        profile = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    else:
        ap.error("give --profile or --describe")
    print(json.dumps(run_briefing(profile, a.out_dir, a.data_dir, a.since, a.no_audio, not a.no_cache, a.mock_script,
                                  a.facts_only, a.embed), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
