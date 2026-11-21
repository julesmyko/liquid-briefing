# Demo script (about 3 minutes) — Trust & accuracy first (25 points)

Before going on stage: `python3 server.py`, open http://localhost:8787, hit play once on each briefing so audio is warm. Keep a cached wildcard ready.

| Time | Do | Say |
|---|---|---|
| 0:00 | Home page, hero. | "One week of news, one briefing per listener. Every sentence is traceable." |
| 0:15 | Play the **FX trader** briefing for ~20 seconds. | (let it speak: outlet named, figures in digits, short sentences) |
| 0:35 | Click **Transcript and sources**. | "Same words you just heard, sentence by sentence. Read the blue box: three clicks to verify." |
| 0:50 | Click a green **figure chip** (e.g. 98%). | "This 98% was checked against the cited fact before it was spoken. One click and we are on the original article." |
| 1:10 | Back, open **Check the grouping** under a story. | "The jury cannot see an answer key, so we show our grouping: every article merged into this story, and which ones the briefing cites." |
| 1:30 | Show the counters banner. | "263/263 sentences verified, 343/343 figures across the seven briefings. Sentences that failed were repaired once, then dropped, never spoken." |
| 1:45 | Home → **Dutch investor** or **German investor**, play 10 s. | "Same week, different listener, different language, native-language source when it exists." |
| 2:05 | **Wildcard**: type the live listener description, Generate. | "New listener on the fly. One model call, then ElevenLabs." (while it runs, show the cost section: ~10k tokens per briefing vs ~940k naive) |
| 2:45 | Play the wildcard result, open its transcript. | "Same trust layer, same links." |

If the network fails: play the cached briefings and open their transcripts; the trust story is identical.
