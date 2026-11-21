#!/usr/bin/env python3
"""Offline tests: no API, no keys. Run: python3 tests_offline.py"""
import json, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lb_numbers import extract_numbers, check_spoken_numbers
from lb_audit import parse_script, audit_blocks, rebuild
import liquid_briefing as LB


def test_numbers():
    g = lambda t, l: [(n["value"], n["kind"]) for n in extract_numbers(t, l) if not n["exempt"]]
    assert g("rose 0.3% and $1.2 billion", "en") == [(0.3, "pct"), (1.2e9, "num")]
    assert g("steeg 0,3 procent en 2,5 miljard", "nl") == [(0.3, "pct"), (2.5e9, "num")]
    assert g("Prozent 3,5 Prozent und 1.234 Punkte", "de") == [(3.5, "pct"), (1234.0, "num")]
    assert g("in 2026 op 13 november", "nl") == []
    ok, bad, words = check_spoken_numbers("Het steeg 0,3 procent.", "nl", extract_numbers("rose 0.3%", "en"))
    assert not bad and not words
    assert check_spoken_numbers("Het steeg 0,4 procent.", "nl", extract_numbers("rose 0.3%", "en"))[1]
    assert check_spoken_numbers("Drie procent hoger.", "nl", [])[2]
    print("numbers ok")


def test_pipeline():
    if not (HERE / "invezz_en.jsonl").exists():
        print("pipeline test skipped: put the Newstex .jsonl files in this folder to run it")
        return
    prof = json.loads((HERE / "profile_fx.json").read_text())
    out = Path(tempfile.mkdtemp())
    facts_run = LB.run_briefing(prof, out, HERE, facts_only=True)
    d = json.loads((out / "facts.json").read_text())
    lines = [prof and "This briefing was written by AI and is read by a synthetic voice.", ""]
    for s in d["stories"]:
        lines += ["**Story**", ""]
        sents = []
        for f in s["facts"]:
            nums = [n["raw"] for n in f["numbers"] if not n["exempt"]]
            if nums:
                sents.append("According to %s, a figure of %s was reported [%s]." % (f["outlet"], nums[0], f["fact_id"]))
        lines.append(" ".join(sents[:3]))
        lines.append("")
    first_id = d["stories"][0]["facts"][0]["fact_id"]
    lines.insert(4, "A made-up claim says inflation hit 99.9%% last week [%s]." % first_id)   # must be dropped
    lines.append("That was the briefing.")
    script = out / "mock.txt"
    script.write_text("\n".join(lines), encoding="utf-8")
    r = LB.run_briefing(prof, out / "run", HERE, no_audio=True, mock_script=script)
    c = r["counters"]
    assert r["audit_passed"], r
    assert c["figures_verified"] == c["figures_checked"] > 0, c
    assert c["sentences_dropped"] >= 1, c
    assert "99.9" not in (out / "run" / "script.txt").read_text()
    page = (out / "run" / "sources.html").read_text()
    assert "http" in page and "Open source article" in page
    print("pipeline ok:", json.dumps(c))


if __name__ == "__main__":
    test_numbers()
    test_pipeline()
    print("ALL OK")
