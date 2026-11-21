#!/usr/bin/env python3
"""Cost model for the presentation. Run after the briefings:  python3 cost_report.py out_fx out_dutch
Uses measured tokens/characters from each run's cost.json when it exists, otherwise an estimate from facts.json
(4 characters ~ 1 token). Prices are NOT guessed: put your real prices in pricing.json to get dollar figures."""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from datetime import datetime, timezone
from lb_stories import build_stories

PRICING = HERE / "pricing.json"
SYSTEM_TOKENS = 800


def load_prices():
    if PRICING.exists():
        return json.loads(PRICING.read_text())
    return {}


def money(tokens_in, tokens_out, chars, p):
    if not all(p.get(k) is not None for k in ("llm_input_per_mtok", "llm_output_per_mtok", "tts_per_1k_chars")):
        return None
    return tokens_in / 1e6 * p["llm_input_per_mtok"] + tokens_out / 1e6 * p["llm_output_per_mtok"] + chars / 1e3 * p["tts_per_1k_chars"]


def run_numbers(d):
    facts = json.loads((d / "facts.json").read_text(encoding="utf-8"))
    cost = json.loads((d / "cost.json").read_text()) if (d / "cost.json").exists() else None
    calls = [c for c in (cost or {}).get("calls", []) if c["step"] in ("script", "script_repair") and c.get("input_tokens")]
    if calls:
        tin, tout, src = sum(c["input_tokens"] for c in calls), sum(c["output_tokens"] or 0 for c in calls), "measured"
    else:
        chars = sum(len(f["sent"]) + 80 for s in facts["stories"] for f in s["facts"])
        tin, tout, src = chars // 4 + SYSTEM_TOKENS, int(facts["meta"]["target_words"] * 1.5), "estimated"
    tts = [c for c in (cost or {}).get("calls", []) if c["step"] == "tts"]
    chars = tts[0]["characters"] if tts else int(facts["meta"]["target_words"] * 6.2)
    return facts["profile"].get("name", d.name), tin, tout, chars, src, facts["meta"]


def main():
    dirs = [Path(a) for a in sys.argv[1:]]
    if not dirs:
        sys.exit("usage: cost_report.py RUN_DIR [RUN_DIR ...]")
    p = load_prices()
    rows = [run_numbers(d) for d in dirs]
    meta = rows[0][5]
    t0 = time.time()
    build_stories(HERE, datetime(2026, 11, 13, tzinfo=timezone.utc))
    prep_s = time.time() - t0
    naive = meta["chars_in_window"] // 4
    out = ["# Cost report", "",
           "## Local preprocessing (grouping, facts, ranking, audit): $0 API cost",
           "- Window: %d articles, %.1fM characters (~%.2fM tokens). Measured local time: %.1f s on this machine." %
           (meta["articles_in_window"], meta["chars_in_window"] / 1e6, naive / 1e6, prep_s),
           "- Story grouping uses TF-IDF + rules, no embeddings API (optional `--embed openai`).", "",
           "## Per briefing (paid steps only)", "", "| Listener | LLM in (tokens) | LLM out (tokens) | TTS chars | source | $ |", "|---|---|---|---|---|---|"]
    tot = [0, 0, 0]
    for name, tin, tout, ch, src, _ in rows:
        m = money(tin, tout, ch, p)
        out.append("| %s | %d | %d | %d | %s | %s |" % (name, tin, tout, ch, src, "%.3f" % m if m is not None else "set pricing.json"))
        tot[0] += tin; tot[1] += tout; tot[2] += ch
    n = len(rows)
    avg = [x / n for x in tot]
    out += ["", "## Scaling", "",
            "- **Naive baseline** (every article through a large model for every listener): %.2fM input tokens per listener per run." % (naive / 1e6),
            "- **This design**: %.1fk input tokens per listener (only the selected, verified facts reach the model), i.e. %.0fx fewer." % (avg[0] / 1e3, naive / max(1, avg[0])),
            "- **Full dataset (%d articles)**: grouping and fact extraction cost nothing in API terms; cost = listeners x one briefing." % 1740,
            "- **10x volume**: preprocessing time grows with articles (the pairwise similarity step is O(n^2); NOT measured at 10x here, "
            "so expect minutes rather than seconds, and use an embedding + nearest-neighbour index beyond that). "
            "**LLM and TTS cost scale with the number of listeners, not articles.**",
            "- Daily newsroom run, L listeners: ~%d tokens in, ~%d tokens out, ~%d TTS chars per listener x L." % (avg[0], avg[1], avg[2])]
    if all(p.get(k) is not None for k in ("llm_input_per_mtok", "llm_output_per_mtok", "tts_per_1k_chars")):
        per = money(avg[0], avg[1], avg[2], p)
        naive_cost = money(naive, avg[1], avg[2], p)
        out += ["", "| | per listener | 1,000 listeners/day | 10,000 listeners/day |", "|---|---|---|---|",
                "| This design | $%.3f | $%.0f | $%.0f |" % (per, per * 1e3, per * 1e4),
                "| Naive (all articles to LLM) | $%.3f | $%.0f | $%.0f |" % (naive_cost, naive_cost * 1e3, naive_cost * 1e4)]
    (HERE / "cost_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
