#!/usr/bin/env python3
"""Free, offline: add the grouped articles of each story to existing runs' sources.json (no LLM, no TTS), then rebuild the pages."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import liquid_briefing as LB
from generate_source_page import render_page
from lb_theme import pretty
import server


def main():
    since = datetime.fromisoformat("2026-11-13").replace(tzinfo=timezone.utc)
    for d in server.run_dirs():
        f = d / "facts.json"
        if not f.exists():
            print("skip (no facts.json):", d.name); continue
        prof = json.loads(f.read_text(encoding="utf-8"))["profile"]
        sel, _ = LB.build_selection(prof, HERE, since)
        s = json.loads((d / "sources.json").read_text(encoding="utf-8"))
        by_head = {x["headline"]: x for x in sel}
        n = 0
        for st in s["stories"]:
            m = by_head.get(st["headline"])
            if m:
                st["group"] = m["group"]; n += 1
        (d / "sources.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        a = json.loads((d / "script_audit.json").read_text(encoding="utf-8"))
        (d / "sources.html").write_text(render_page(s, a, pretty((s.get("profile") or {}).get("name") or d.name)), encoding="utf-8")
        print(d.name, "stories with group: %d/%d" % (n, len(s["stories"])), "sizes:", [len(x.get("group", [])) for x in s["stories"]])


if __name__ == "__main__":
    main()
