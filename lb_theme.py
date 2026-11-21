"""Visual theme shared by the listener site and the transcript pages (own identity, light editorial look)."""
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Instrument+Serif:ital@0;1'
         '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">')
LOGO = ('<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><rect x="3" y="11" width="3.4" height="8" rx="1.7" fill="#4a76e8"/>'
        '<rect x="9" y="6" width="3.4" height="18" rx="1.7" fill="#0f1530"/><rect x="15" y="9" width="3.4" height="12" rx="1.7" fill="#4a76e8"/>'
        '<rect x="21" y="4" width="3.4" height="22" rx="1.7" fill="#0f1530"/></svg>')
NAMES = {"fx_trader": "FX trader", "dutch_investor": "Dutch investor", "german_investor": "German investor",
         "general_news": "General news listener", "wildcard": "Wildcard listener"}


def pretty(name):
    return NAMES.get(name, str(name or "Listener").replace("_", " ").capitalize())


CSS = """
:root{--bg:#f8f9fc;--ink:#0f1530;--mut:#6b7794;--blue:#4a76e8;--line:#e3e8f2;--sans:"Manrope",-apple-system,"SF Pro Display","Segoe UI",system-ui,sans-serif;
--serif:"Instrument Serif","Iowan Old Style",Georgia,serif;--mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:400 17px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit}.wrap{max-width:1180px;margin:0 auto;padding:0 28px}
.nav{display:flex;align-items:center;gap:34px;height:84px}.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:21px;letter-spacing:-.02em;text-decoration:none}
.nav a.l{color:var(--mut);text-decoration:none;font-size:15.5px}.nav a.l:hover{color:var(--ink)}.sp{flex:1}
.btn{display:inline-flex;align-items:center;gap:10px;background:var(--ink);color:#fff;border:0;border-radius:12px;padding:15px 26px;font:600 16px var(--sans);text-decoration:none;cursor:pointer;box-shadow:0 8px 24px rgba(15,21,48,.16)}
.btn.s{padding:11px 20px;font-size:15px}.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line);box-shadow:none}
.pill{display:inline-flex;align-items:center;gap:9px;border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 16px;font:500 12px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:#43507a}
.pill i{width:7px;height:7px;border-radius:50%;background:#7aa2f7;display:inline-block}
.h1{font:800 clamp(40px,5.2vw,74px)/.98 var(--sans);letter-spacing:-.045em;margin:26px 0 0}.h1 em{display:block;font:italic 400 1.04em/1 var(--serif);color:var(--blue);letter-spacing:-.02em;margin:.05em 0}
.lead{color:var(--mut);font-size:20px;max-width:540px;margin:32px 0}.lead b{color:var(--ink);font-weight:600}.cta{display:flex;gap:14px;flex-wrap:wrap}
.heroGrid{display:grid;grid-template-columns:1.05fr 1fr;gap:44px;align-items:center;padding:34px 0 80px}
.flow{display:grid;grid-template-columns:140px minmax(240px,1fr) 150px;gap:46px;align-items:center}.col{display:flex;flex-direction:column;gap:14px}
.chip{position:relative;background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 14px;box-shadow:0 4px 18px rgba(15,21,48,.06);font-weight:600;font-size:14px;line-height:1.25}
.chip small,.mono{display:block;font:500 10.5px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:#8793b3;margin-top:3px}
.col.l .chip::after,.col.r .chip::before{content:"";position:absolute;top:50%;width:46px;border-top:2px dashed #b9c6ee}.col.l .chip::after{left:100%}.col.r .chip::before{right:100%}
.core{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px 20px;box-shadow:0 22px 54px rgba(15,21,48,.11)}
.core h4{font:700 19px/1.25 var(--sans);letter-spacing:-.02em;margin:10px 0 12px}.bars i{display:block;height:7px;border-radius:4px;background:#edf0f7;margin:7px 0}
.tag{display:inline-block;background:#e8efff;color:#2f56c4;border-radius:7px;padding:4px 10px;font:600 11px var(--mono);letter-spacing:.08em;text-transform:uppercase}
.sec{padding:76px 0;border-top:1px solid var(--line)}.t{font:800 clamp(30px,4vw,46px)/1.05 var(--sans);letter-spacing:-.035em;margin:16px 0 10px}.t em{font:italic 400 1.06em var(--serif);color:var(--blue);letter-spacing:-.01em}
.sub{color:var(--mut);max-width:640px;margin:0 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.grid.w{grid-template-columns:repeat(auto-fit,minmax(380px,1fr))}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 4px 18px rgba(15,21,48,.05)}.card h3{margin:8px 0 6px;font:700 20px/1.2 var(--sans);letter-spacing:-.02em}
.card p{margin:0 0 10px;color:var(--mut);font-size:15.5px}.card .no{font:500 12px var(--mono);color:var(--blue);letter-spacing:.1em}
.stat b{display:block;font:800 46px/1 var(--sans);letter-spacing:-.04em}.stat span{color:var(--mut);font-size:14px}
.dark{background:var(--ink);color:#fff;border-radius:20px;padding:30px}.dark p{color:#b8c2e0}.dark b{color:#fff}
audio{width:100%;margin:10px 0}textarea{width:100%;min-height:84px;font:inherit;padding:14px;border:1px solid #cdd6ea;border-radius:12px;background:#fff;resize:vertical}
.foot{padding:40px 0 60px;color:#8793b3;font-size:13.5px;border-top:1px solid var(--line)}
.badge{display:inline-block;background:#eef2ff;color:#3446b4;border-radius:999px;padding:2px 11px;font:600 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;margin-right:6px}
.summary{background:var(--ink);color:#fff;border-radius:16px;padding:18px 24px;display:flex;flex-wrap:wrap;gap:12px 34px;margin:16px 0}.summary b{display:block;font:800 28px var(--sans);letter-spacing:-.03em}
.summary span{font:500 10.5px var(--mono);opacity:.75;text-transform:uppercase;letter-spacing:.08em}
.note{background:#fff8e6;border:1px solid #f1d98a;border-radius:12px;padding:12px 16px;margin:14px 0;font-size:14.5px}
.sent{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin:10px 0;box-shadow:0 3px 14px rgba(15,21,48,.04)}
.said{font-size:17.5px;margin:0 0 8px}.said small{color:#8793b3;font-family:var(--mono)}
.n{display:inline-block;background:#e8f7ee;color:#087443;border-radius:7px;padding:2px 9px;margin:0 6px 6px 0;font:600 12.5px var(--mono)}.n.bad{background:#fde8e8;color:#b42318}
.src{border-top:1px solid #edf0f6;margin-top:8px;padding-top:9px;font-size:14.5px;color:#3b4b6b}.src q{display:block;color:var(--ink);margin:3px 0 4px}.src small{color:#8793b3;font-family:var(--mono);font-size:11.5px}
.src a{color:var(--blue);font-weight:600;text-decoration:none}h2.st{font:700 21px/1.25 var(--sans);letter-spacing:-.02em;margin:34px 0 6px}h2.st small{display:block;font:500 11px var(--mono);color:#8793b3;letter-spacing:.08em;text-transform:uppercase;margin-top:3px}
a.n,a.n:visited{text-decoration:none;color:#087443}a.n:hover{outline:2px solid #087443;outline-offset:1px}a.n.bad{color:#b42318}
.how{background:#fff;border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:12px;padding:14px 20px;margin:16px 0;font-size:15.5px}.how ol{margin:8px 0 0;padding-left:20px;color:#3b4b6b}.how li{margin:3px 0}
details.grp{margin:2px 0 10px;font-size:14.5px;color:#3b4b6b}details.grp summary{cursor:pointer;color:var(--blue);font-weight:600}details.grp ul{margin:8px 0 0;padding-left:18px}details.grp li{margin:5px 0}details.grp a{color:var(--ink);text-decoration:none;border-bottom:1px solid #c9d4f2}
.verify{display:flex;gap:14px;flex-wrap:wrap;margin:6px 0 0}.verify span{font:500 12px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:#43507a}
.sel{-webkit-appearance:none;appearance:none;height:52px;padding:0 46px 0 20px;border:1px solid var(--line);border-radius:12px;color:var(--ink);font:600 15.5px var(--sans);cursor:pointer;
background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='9' viewBox='0 0 14 9' fill='none'%3E%3Cpath d='M1.5 1.75 7 7.25l5.5-5.5' stroke='%234a76e8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 20px center;
box-shadow:0 4px 18px rgba(15,21,48,.06);transition:border-color .15s,box-shadow .15s}.sel:hover{border-color:#b9c6ee}.sel:focus{outline:none;border-color:var(--blue);box-shadow:0 0 0 3px rgba(74,118,232,.18)}
@media(max-width:940px){.heroGrid{grid-template-columns:1fr}.nav a.l{display:none}.flow{grid-template-columns:1fr}.col.l,.col.r{flex-direction:row;flex-wrap:wrap}.col .chip::after,.col .chip::before{display:none}}
"""
