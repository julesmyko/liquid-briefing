#!/usr/bin/env python3
"""Listener page: audio player + the briefing sentence by sentence, each linked to its source article.
Only short snippets (<= 14 words) of sources are shown, never article text."""
from __future__ import annotations
import argparse, html, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lb_theme import CSS, FONTS, LOGO, pretty


def esc(x):
    return html.escape(str(x or ""), quote=True)


def group_html(group):
    if not group:
        return ""
    cited = sum(1 for g in group if g.get("cited"))
    rows = "".join("<li><span class='mono' style='display:inline'>%s · %s</span> <a href='%s' target='_blank' rel='noopener'>%s ↗</a>%s</li>" % (
        esc(g.get("outlet")), esc(g.get("date")), esc(g.get("permalink") or "#"), esc(g.get("headline")),
        " <span class='badge'>cited</span>" if g.get("cited") else "") for g in group)
    return ("<details class='grp'><summary>Grouped from %d article%s (%d cited in this briefing). Check the grouping</summary><ul>%s</ul></details>"
            % (len(group), "" if len(group) == 1 else "s", cited, rows))


def chip(x, fact_ids, claims):
    mark = "✓" if x["matched"] else "✗"
    cls = "n" + ("" if x["matched"] else " bad")
    target = None
    for i in fact_ids:
        k = claims.get(i)
        if k and x["raw"] in (k.get("numbers") or []):
            target = k
            break
    if target is None:
        target = next((claims[i] for i in fact_ids if i in claims), None)
    if target and target.get("permalink"):
        return "<a class='%s' href='%s' target='_blank' rel='noopener' title='Open the article this figure comes from'>%s %s ↗</a>" % (cls, esc(target["permalink"]), mark, esc(x["raw"]))
    return "<span class='%s'>%s %s</span>" % (cls, mark, esc(x["raw"]))


HOWTO = ("<div class='how'><b>Verify any sentence in 3 clicks</b><ol><li><b>Read</b> the sentence you just heard.</li>"
         "<li><b>Check</b> the green figure chips and the short excerpt under it.</li>"
         "<li><b>Click</b> a figure or <i>Open source article</i> to land on the original article. "
         "Open <i>Check the grouping</i> under a story heading to see every article we merged into it.</li></ol></div>")


def render_page(sources, audit, title="Liquid Briefing", audio="briefing.mp3"):
    c = sources.get("counters", {})
    prof = sources.get("profile") or {}
    claims = {x["fact_id"]: x for x in sources.get("claims", [])}
    stories = {s["story_id"]: s for s in sources.get("stories", [])}
    stats = [("Stories", c.get("stories")), ("Sentences verified", "%s / %s" % (c.get("claims_passed"), c.get("claim_sentences"))),
             ("Figures verified", "%s / %s" % (c.get("figures_verified"), c.get("figures_checked"))),
             ("Wrong figures caught before speech", c.get("figures_caught_before_speech")),
             ("'Sources differ' flags", c.get("sources_differ_flags"))]
    parts = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             "<title>%s</title>%s<style>%s</style></head><body><div class='wrap'><div class='nav'><a class='logo' href='/'>%s Liquid Briefing</a><span class='sp'></span><a class='btn s ghost' href='/'>All briefings</a></div>"
             "<span class='pill'><i></i>Transcript and sources</span><h1 class='t' style='font-size:clamp(34px,5vw,56px);margin-top:18px'>%s</h1>" % (esc(title), FONTS, CSS, LOGO, esc(title)),
             "<p class='sub' style='margin-bottom:6px'><span class='badge'>AI-generated</span><span class='badge'>synthetic voice</span>"
             "<span class='badge'>language: %s</span> %s</p>" % (esc(prof.get("language")), esc(prof.get("description"))),
             "<audio controls preload='metadata' src='%s'></audio>" % esc(audio),
             HOWTO,
             "<div class='summary'>%s</div>" % "".join("<div><b>%s</b><span>%s</span></div>" % (esc(v), esc(k)) for k, v in stats),
             "<p class='sub' style='margin:14px 0 0'>Below: what you hear, sentence by sentence. Each sentence links to the article it comes from; "
             "every figure was checked against that article before it was voiced.</p>"]
    if sources.get("conflicts"):
        parts.append("<div class='note'><b>Sources differ:</b> %d possible disagreement(s) between outlets were flagged: %s</div>"
                     % (len(sources["conflicts"]), esc("; ".join(x.get("note") or "%s vs %s" % (x["a"], x["b"]) for x in sources["conflicts"]))))
    n, last = 0, None
    for r in audit.get("sentences", []):
        if r.get("structural") or r.get("index", 0) < 0:
            continue
        m = re.match(r"s\d{2}", r["fact_ids"][0]) if r.get("fact_ids") else None
        sid = m.group(0) if m else None
        if sid and sid != last:
            st = stories.get(sid, {})
            parts.append("<h2 class='st'>%s <small>%s</small></h2>" % (esc(st.get("headline", sid)), esc(", ".join(st.get("outlets", [])))))
            parts.append(group_html(st.get("group") or []))
            last = sid
        n += 1
        said = re.sub(r"\s*\[s\d{2}f\d{2}\]", "", r["sentence"])
        chips = "".join(chip(x, r.get("fact_ids", []), claims) for x in r.get("numbers", []))
        srcs = ""
        for i in r.get("fact_ids", []):
            k = claims.get(i)
            if k:
                srcs += ("<div class='src'><small>%s · %s · %s</small><q>%s</q><a href='%s' target='_blank' rel='noopener'>Open source article ↗</a> <small>%s</small></div>"
                         % (esc(i), esc(k["outlet"]), esc(k["date"][:10]), esc(k["snippet"]), esc(k["permalink"] or "#"), esc(k["headline"])))
        parts.append("<div class='sent'><p class='said'><small>%d.</small> %s</p>%s%s</div>" % (n, esc(said), chips, srcs))
    parts.append("<p class='foot'>AI-generated briefing, read by a synthetic voice. Source data: Newstex (licensed for the MAIN AI Hackathon 2026). Short snippets and links only.</p></div></body></html>")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path, help="folder with sources.json and script_audit.json")
    ap.add_argument("--title")
    a = ap.parse_args()
    s = json.loads((a.run_dir / "sources.json").read_text(encoding="utf-8"))
    au = json.loads((a.run_dir / "script_audit.json").read_text(encoding="utf-8"))
    title = a.title or pretty((s.get("profile") or {}).get("name") or a.run_dir.name)
    (a.run_dir / "sources.html").write_text(render_page(s, au, title), encoding="utf-8")
    print(a.run_dir / "sources.html")


if __name__ == "__main__":
    main()
