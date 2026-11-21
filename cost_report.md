# Cost report

## Local preprocessing (grouping, facts, ranking, audit): $0 API cost
- Window: 811 articles, 3.8M characters (~0.94M tokens). Measured local time: 1.1 s on this machine.
- Story grouping uses TF-IDF + rules, no embeddings API (optional `--embed openai`).

## Per briefing (paid steps only)

| Listener | LLM in (tokens) | LLM out (tokens) | TTS chars | source | $ |
|---|---|---|---|---|---|
| fx_trader | 10576 | 3541 | 5828 | measured | set pricing.json |
| dutch_investor | 3119 | 1563 | 4927 | measured | set pricing.json |
| german_investor | 8371 | 3430 | 5151 | measured | set pricing.json |

## Scaling

- **Naive baseline** (every article through a large model for every listener): 0.94M input tokens per listener per run.
- **This design**: 7.4k input tokens per listener (only the selected, verified facts reach the model), i.e. 128x fewer.
- **Full dataset (1740 articles)**: grouping and fact extraction cost nothing in API terms; cost = listeners x one briefing.
- **10x volume**: preprocessing time grows with articles (the pairwise similarity step is O(n^2); NOT measured at 10x here, so expect minutes rather than seconds, and use an embedding + nearest-neighbour index beyond that). **LLM and TTS cost scale with the number of listeners, not articles.**
- Daily newsroom run, L listeners: ~7355 tokens in, ~2844 tokens out, ~5302 TTS chars per listener x L.
