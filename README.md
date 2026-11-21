# Liquid Briefing: personal audio news briefings you can check

MAIN AI Hackathon 2026, Sourcera track "The Liquid Briefing".
A week of Newstex business news becomes a personal audio briefing per listener. Every spoken sentence is linked to its source
article, every figure is checked before it is voiced, and when sources disagree the briefing says so.

## What is in the box
- **Briefings for different listeners** (`out_fx`, `out_dutch`, `out_german`, plus four live "wildcard" examples in `runs/`, including a Dutch and a German one):
  trader in English, investor in Dutch, investor in German. Different stories, order, depth, length and language.
- **Listener site** (`python3 server.py`, then http://localhost:8787): play each briefing, open its transcript, and create a new
  listener live from a free-text description (language menu: English, Nederlands, Deutsch).
- **Transcript pages**: sentence by sentence, with the figure chips (click one to land on the original article), a short excerpt,
  a link to the source article, and for each story the list of every article grouped into it.
- **"Sources differ" flags**: when two articles quote the same headline figure but a different benchmark, they are flagged in the
  transcript and the briefing says it out loud (example in the Dutch and German briefings: Nvidia's revenue forecast against
  analyst expectations of 125.3, 125.1 and 124.89 billion dollars).

## Listen without any API key
The sample outputs are included. Run `python3 server.py` and open http://localhost:8787. Only creating a new briefing needs keys.

## Setup to generate new briefings
1. Python 3.9+ and `pip install -r requirements.txt` (only numpy).
2. Put the provided Newstex files (`actionforex.jsonl`, `ibtimes_uk.jsonl`, `invezz_en.jsonl`, `invezz_nl.jsonl`, `invezz_de.jsonl`,
   `zacks.jsonl`) in this folder. They are not included (licence).
3. `cp .env.example .env` and fill `OPENAI_API_KEY` and `ELEVENLABS_API_KEY`.
4. `python3 tests_offline.py` must print ALL OK (no API needed).

```
python3 liquid_briefing.py --profile profile_fx.json     --out-dir out_fx
python3 liquid_briefing.py --profile profile_dutch.json  --out-dir out_dutch
python3 liquid_briefing.py --profile profile_german.json --out-dir out_german
python3 liquid_briefing.py --describe "retired teacher in Utrecht, worried about her pension, 4 minutes" --out-dir out_wild
python3 server.py
```
Flags: `--facts-only` (free), `--no-audio` (script and audit only), `--no-cache`. A listener profile is a small JSON file
(language, topics, preferred outlets, length, style, voice).

## How it works
| Step | Where | Cost |
|---|---|---|
| Load week, align Invezz EN/NL/DE twins (author + 15 min), group articles into stories (TF-IDF with rare-entity and time rules), extract facts and figures, rank per listener | local Python | no API cost |
| "Sources differ" detector: same headline figure, different benchmark, across the whole week | local Python | no API cost |
| Write the script: one OpenAI call per briefing (one repair call only if the audit finds a problem) | OpenAI Responses API | about 3k to 10k tokens per briefing |
| Trust audit: every sentence cites fact IDs, every spoken figure must be in a cited fact (en/nl/de number formats), no figure spelled as words, no copied wording; failing sentences are repaired once, then dropped | local | no API cost |
| Voice | ElevenLabs API (`eleven_multilingual_v2`) | characters |

Native-language rule: when the listener's language has a twin article (Invezz NL/DE), facts come from it; otherwise from the English article
and the script is written in the listener's language.
Cost numbers: `python3 cost_report.py out_fx out_dutch out_german` (writes `cost_report.md`; fill `pricing.json` for dollars).

## Checks to try (Trust)
Open a transcript, click a green figure: you land on the article it came from. Open "Check the grouping" under a story: every merged article is listed,
with those cited in the briefing marked. Counters at the top show sentences and figures verified and how many wrong figures were caught before speech.

## Honest limits
- Story grouping is rule based and can split one saga over several stories (for example Nvidia news is spread over several groups).
- The "sources differ" detector covers money figures with a stated benchmark (consensus, estimate, expectation); other kinds of disagreement are not detected.
- Scaling to 10x the articles is estimated, not measured. Similarity is O(n^2); beyond a few thousand articles use an embedding index.
- Nothing is checked against external sources: only the provided dataset is used.
- The briefing informs, it gives no investment advice. Voice is synthetic and disclosed at the start of each briefing.

## Optional: n8n
`python3 server.py`, then import `n8n_workflow.json` (Webhook, HTTP Request to localhost:8787/briefing, Respond).
POST body: `{"description": "...", "language": "en|nl|de"}` or `{"profile": {...}}`. Untested in this submission.

## Licence
Article files and all text derived from them (`cache/`, `facts.json`) stay local and are not included. Sample outputs contain only
paraphrased facts, short excerpts (14 words at most) and links. Delete all data after the event.
