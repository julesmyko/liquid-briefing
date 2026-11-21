"""Generate the pitch-video narration, one MP3 per scene, with the project's own ElevenLabs helper.
Run from the project folder:  python3 make_voice.py
Output: video/narr_1.mp3 ... video/narr_5.mp3"""
from pathlib import Path
import lb_llm

lb_llm.load_env()
OUT = Path("video"); OUT.mkdir(exist_ok=True)
VOICE = "I7qs7sGMuqqIuJ1AE3eT"   # same English voice as the briefings

SCENES = [
    "Meet Liquid Briefing. One week of business news, turned into a personal audio briefing for every listener.",
    "Same news, different listeners. A forex trader in English, a Dutch investor in Dutch, and a German reader in German, each with their own topics and length.",
    "And you never have to trust the voice. Every sentence links to the article it came from. Click a figure, and you land on the original source. Stories merged from several articles show exactly which ones.",
    "When outlets disagree, we say so. Here, Invezz and ActionForex quote different analyst expectations for Nvidia, and the briefing reports both instead of picking one.",
    "Anyone can describe themselves in plain words, here a small business owner in Amsterdam, and get a new briefing in about a minute. In total, two hundred sixty three of two hundred sixty three sentences verified, and every figure matched, for cents per briefing.",
]

cost = lb_llm.CostLog()
for i, text in enumerate(SCENES, 1):
    out = OUT / ("narr_%d.mp3" % i)
    lb_llm.elevenlabs_tts(text, VOICE, out, cost, True)
    print("ok", out, len(text), "chars")
print("done")
