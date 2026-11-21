#!/usr/bin/env python3
"""Listener space + API.   python3 server.py   ->  http://localhost:8787
  GET  /                      all briefings (audio player + transcript linked to sources) and a live "describe a listener" box
  POST /briefing              {"profile": {...}} or {"description": "..."} (+ "no_audio": true)  -> used by the page and by n8n
Only briefing.mp3 / sources.html / sources.json / script.txt / script_readable.txt are served (never facts.json: it holds article text).
Keep it on your own network: the data licence forbids sharing outside the team."""
import html, json, os, re, socket, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lb_llm
import liquid_briefing as LB
from generate_source_page import render_page
from lb_theme import CSS, FONTS, LOGO, pretty

RUNS = HERE / "runs"
PUBLIC = {"briefing.mp3": "audio/mpeg", "sources.html": "text/html; charset=utf-8", "sources.json": "application/json",
          "script.txt": "text/plain; charset=utf-8", "script_readable.txt": "text/plain; charset=utf-8"}
FLAGS = {"en": "EN", "nl": "NL", "de": "DE"}


def run_dirs():
    ds = [d for d in sorted(HERE.glob("out_*")) if (d / "sources.json").exists()]
    ds += sorted([d for d in RUNS.glob("*") if (d / "sources.json").exists()], reverse=True) if RUNS.exists() else []
    return ds


def refresh_pages():
    for d in run_dirs():
        try:
            s = json.loads((d / "sources.json").read_text(encoding="utf-8"))
            a = json.loads((d / "script_audit.json").read_text(encoding="utf-8"))
            (d / "sources.html").write_text(render_page(s, a, pretty((s.get("profile") or {}).get("name") or d.name)), encoding="utf-8")
        except Exception as e:
            print("skip", d.name, e)


def _tok(d):
    try:
        c = json.loads((d / "cost.json").read_text(encoding="utf-8"))
        return sum((x.get("input_tokens") or 0) + (x.get("output_tokens") or 0) for x in c.get("calls", []) if x.get("provider") == "openai"), c.get("meta", {})
    except Exception:
        return 0, {}


def index_html():
    cards, tot = [], dict(stories=0, cs=0, cp=0, fc=0, fv=0, tokens=0)
    meta = {}
    for d in run_dirs():
        s = json.loads((d / "sources.json").read_text(encoding="utf-8"))
        p, c = s.get("profile") or {}, s.get("counters", {})
        tk, m = _tok(d)
        meta = meta or m
        tot["stories"] += c.get("stories") or 0; tot["cs"] += c.get("claim_sentences") or 0; tot["cp"] += c.get("claims_passed") or 0
        tot["fc"] += c.get("figures_checked") or 0; tot["fv"] += c.get("figures_verified") or 0; tot["tokens"] += tk
        rel = d.relative_to(HERE).as_posix()
        audio = "<audio controls preload='none' src='/%s/briefing.mp3'></audio>" % rel if (d / "briefing.mp3").exists() else "<p class='mono'>no audio</p>"
        cards.append("<div class='card'><span class='tag'>%s</span><h3>%s</h3><p>%s</p>%s<p class='mono'>%s stories · %s/%s sentences verified · %s/%s figures verified</p>"
                     "<a class='btn s ghost' href='/%s/sources.html'>Transcript and sources</a></div>" % (
                         FLAGS.get(p.get("language"), ""), html.escape(pretty(p.get("name") or d.name)), html.escape(str(p.get("description") or "")),
                         audio, c.get("stories"), c.get("claims_passed"), c.get("claim_sentences"), c.get("figures_verified"), c.get("figures_checked"), rel))
    n = max(len(cards), 1)
    art, st, tw = meta.get("articles_in_window", 1740), meta.get("stories_total", "-"), meta.get("twins_aligned", "-")
    steps = [("01", "Read the week", "%s articles in the window, parsed locally for free." % art),
             ("02", "Group into stories", "%s stories: the same event from several outlets is merged, translations aligned (%s twins)." % (st, tw)),
             ("03", "Pick for the listener", "Ranking by importance and by the listener's topics, language and time budget."),
             ("04", "Write, verify, speak", "One model call per briefing. Every sentence cites a fact; every figure is checked. Then ElevenLabs reads it.")]
    stepc = "".join("<div class='card'><span class='no'>%s</span><h3>%s</h3><p>%s</p></div>" % x for x in steps)
    naive = 940000
    avg = tot["tokens"] // n if tot["tokens"] else 0
    return ("""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Liquid Briefing</title>"""
    + FONTS + "<style>" + CSS + "</style></head><body><div class='wrap'>"
    "<div class='nav'><a class='logo' href='/'>" + LOGO + " Liquid Briefing</a><a class='l' href='#how'>How it works</a><a class='l' href='#listen'>Listen</a><a class='l' href='#trust'>Trust</a><a class='l' href='#cost'>Cost</a><span class='sp'></span><a class='btn s' href='#wild'>Try a wildcard</a></div>"
    "<div class='heroGrid'><div><span class='pill'><i></i>Personal audio news briefing</span>"
    "<h1 class='h1'>One week of news.<em>Every listener.</em>Five minutes.</h1>"
    "<p class='lead'>A week of business news becomes a briefing <b>made for you</b>: your topics, your language, your time. Every sentence links back to its source article.</p>"
    "<div class='cta'><a class='btn' href='#listen'>Listen now &#8594;</a><a class='btn ghost' href='#wild'>Create your own</a></div></div>"
    "<div class='flow'><div class='col l'><div class='chip'>Invezz<small>EN · NL · DE</small></div><div class='chip'>ActionForex<small>FX</small></div><div class='chip'>IBTimes UK<small>Markets</small></div><div class='chip'>Zacks<small>Equities</small></div></div>"
    "<div class='core'><span class='tag'>Briefing</span><h4>Your week, verified</h4><div class='bars'><i style='width:92%'></i><i style='width:74%'></i><i style='width:85%'></i></div><span class='mono'>Every claim cited</span></div>"
    "<div class='col r'><div class='chip'>FX trader<small>EN</small></div><div class='chip'>Dutch investor<small>NL</small></div><div class='chip'>German investor<small>DE</small></div></div></div></div>"
    "<section class='sec' id='how'><span class='pill'><i></i>How it works</span><h2 class='t'>From noise to <em>one voice</em></h2><p class='sub'>Free local steps do the heavy lifting; the paid model only writes the final script.</p><div class='grid'>" + stepc + "</div></section>"
    "<section class='sec' id='listen'><span class='pill'><i></i>Listeners</span><h2 class='t'>Same news, <em>different briefings</em></h2><p class='sub'>AI-generated text, read by a synthetic voice. Open the transcript to see the source behind each sentence.</p><div class='grid w'>" + "".join(cards) + "</div></section>"
    "<section class='sec' id='wild'><span class='pill'><i></i>Wildcard</span><h2 class='t'>Describe a listener, <em>get a briefing</em></h2><p class='sub'>Free text is enough: who they are, what they care about, how long they have.</p>"
    "<textarea id='d' placeholder='e.g. Retired teacher in Utrecht, worried about her pension, wants 4 minutes, no jargon'></textarea><p style='display:flex;gap:12px;align-items:center;flex-wrap:wrap'><select id='lang' class='sel'><option value='en'>English</option><option value='nl'>Nederlands</option><option value='de'>Deutsch</option></select><button class='btn' onclick='go()'>Generate briefing</button> <span id='st' class='mono'></span></p><div id='out'></div></section>"
    "<section class='sec' id='trust'><span class='pill'><i></i>Trust</span><h2 class='t'>Nothing is said <em>without a source</em></h2><p class='sub'>Each sentence must cite fact IDs, spoken figures are matched to those facts, and copied wording is rejected. Failing sentences are repaired once, then dropped.</p>"
    "<div class='how' style='max-width:760px;margin:0 0 22px'><b>Check it yourself in 3 clicks:</b> listen, open <i>Transcript and sources</i>, click a green figure. You land on the original article, and each story lists every article we grouped into it.</div><div class='grid'>"
    "<div class='card stat'><b>%s/%s</b><span>sentences verified</span></div><div class='card stat'><b>%s/%s</b><span>figures verified</span></div><div class='card stat'><b>%s</b><span>stories covered</span></div></div></section>" % (tot["cp"], tot["cs"], tot["fv"], tot["fc"], tot["stories"])
    + "<section class='sec' id='cost'><span class='pill'><i></i>Cost</span><h2 class='t'>Cheap by <em>design</em></h2><p class='sub'>Sending every article to the model for every listener would cost about %s tokens per listener. We send about %s.</p><div class='grid'>"
    "<div class='card stat'><b>~%sk</b><span>tokens per briefing (measured)</span></div><div class='card stat'><b>~%sk</b><span>naive baseline per listener</span></div><div class='card stat'><b>1</b><span>model call per briefing, cached</span></div></div></section>" % ("{:,}".format(naive), "{:,}".format(avg), avg // 1000, naive // 1000)
    + "<div class='foot'>Built at MAIN AI Hackathon 2026 for the Sourcera challenge track · News data: Newstex (licensed for the event, not redistributed) · AI-generated voice</div></div>"
    """<script>async function go(){const d=document.getElementById('d').value.trim();if(!d)return;const st=document.getElementById('st');st.textContent='Working... (1-2 minutes)';
try{const r=await fetch('/briefing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:d,language:document.getElementById('lang').value})});const j=await r.json();
if(j.error){st.textContent='Error: '+j.error;return}st.textContent='Done.';
document.getElementById('out').innerHTML="<div class='card'><audio controls src='"+j.urls['briefing.mp3']+"'></audio><p><a href='"+j.urls['sources.html']+"'>Transcript and sources</a> · language: "+j.profile_used.language+", "+j.spoken_words+" words</p></div>"}
catch(e){st.textContent='Error: '+e}}</script></body></html>""")


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/briefing":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            lb_llm.load_env()
            if req.get("description"):
                profile = lb_llm.profile_from_description(req["description"], lb_llm.CostLog(), language=req.get("language", "auto"))
            else:
                profile = req["profile"]
            rid = time.strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"\W+", "", str(profile.get("name") or "briefing"))
            res = LB.run_briefing(profile, RUNS / rid, HERE, no_audio=bool(req.get("no_audio")))
            res["urls"] = {k: "/runs/%s/%s" % (rid, k) for k in PUBLIC}
            res["profile_used"] = profile
            self._send(200, res)
        except Exception as e:
            self._send(500, {"error": str(e)[:600]})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, index_html().encode("utf-8"), "text/html; charset=utf-8")
        parts = [x for x in path.split("/") if x]
        top_ok = parts and (parts[0].startswith("out_") or parts[0] == "runs")
        f = (HERE.joinpath(*parts)).resolve() if parts else None
        if not (top_ok and f and f.is_file() and f.name in PUBLIC and HERE in f.parents):
            return self._send(404, {"error": "not found"})
        data = f.read_bytes()
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and f.suffix == ".mp3":
            start = int(rng.group(1)) if rng.group(1) else 0
            end = int(rng.group(2)) if rng.group(2) else len(data) - 1
            end = min(end, len(data) - 1)
            return self._send(206, data[start:end + 1], PUBLIC[f.name], {"Content-Range": "bytes %d-%d/%d" % (start, end, len(data))})
        self._send(200, data, PUBLIC[f.name])

    def log_message(self, *a):
        pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return None


if __name__ == "__main__":
    RUNS.mkdir(exist_ok=True)
    refresh_pages()
    ip = lan_ip()
    print("Liquid Briefing listener space:\n  on this computer: http://localhost:8787" + ("\n  same Wi-Fi (phone): http://%s:8787" % ip if ip else ""))
    ThreadingHTTPServer(("0.0.0.0", 8787), H).serve_forever()
