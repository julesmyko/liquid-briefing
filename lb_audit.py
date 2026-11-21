"""The trust gate. Every spoken sentence must (1) cite known fact IDs, (2) only contain figures that are in those
facts, (3) not copy article wording. Sentences that fail are repaired by the LLM once, then DROPPED, never spoken."""
from __future__ import annotations
import re
from lb_numbers import check_spoken_numbers
from lb_stories import split_sentences

ID_RE = re.compile(r"\[(s\d{2}f\d{2})\]")
HEADER_RE = re.compile(r"^\s*(\*\*.+\*\*|#+\s.+)\s*$")
MAX_COPY_WORDS = 8


def normalize_ids(text):
    """Move IDs that follow the final punctuation back before it: 'Text. [s01f01]' -> 'Text [s01f01].'"""
    fn = lambda m: " " + "".join("[%s]" % i for i in ID_RE.findall(m.group(2))) + m.group(1) + " "
    text = re.sub(r"([.!?])\s*((?:\[s\d{2}f\d{2}\]\s*)+)", fn, text)
    return re.sub(r"[ \t]+", " ", text)


def parse_script(text):
    blocks = []
    for line in normalize_ids(text).splitlines():
        if not line.strip():
            continue
        if HEADER_RE.match(line):
            blocks.append({"kind": "header", "text": line.strip(), "sentences": []})
        else:
            blocks.append({"kind": "para", "text": line.strip(), "sentences": split_sentences(line)})
    return blocks


def _words(s):
    return re.findall(r"[a-zà-ÿ0-9]+", ID_RE.sub("", s).lower())


def longest_common_run(a, b):
    best, prev = 0, [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def audit_blocks(blocks, facts_by_id, lang):
    """Returns a list of sentence results in script order."""
    results = []
    flat = [(bi, si, s) for bi, b in enumerate(blocks) for si, s in enumerate(b["sentences"])]
    last_idx = len(flat) - 1
    for pos, (bi, si, s) in enumerate(flat):
        ids = ID_RE.findall(s)
        reasons = []
        nums_info = []
        structural = False
        if not ids:
            plain = not re.search(r"\d", s) and len(_words(s)) <= 14
            if plain and pos in (0, last_idx):
                structural = True            # disclosure line / short closing line
            else:
                reasons.append("missing_fact_id")
        else:
            unknown = [i for i in ids if i not in facts_by_id]
            if unknown:
                reasons.append("unknown_fact_id:" + ",".join(unknown))
            cited = [facts_by_id[i] for i in ids if i in facts_by_id]
            allowed = [n for f in cited for n in f["numbers"]]
            body = ID_RE.sub("", s)
            checked, unsupported, wordfigs = check_spoken_numbers(body, lang, allowed)
            nums_info = [{"raw": n["raw"], "matched": n["raw"] not in unsupported} for n in checked]
            if unsupported:
                reasons.append("unsupported_number:" + ", ".join(unsupported))
            if wordfigs:
                reasons.append("figure_written_as_words:" + ", ".join(wordfigs))
            sw = _words(body)
            for f in cited:
                if longest_common_run(sw, _words(f["sent"])) >= MAX_COPY_WORDS:
                    reasons.append("copies_article_wording")
                    break
        results.append({"block": bi, "index": si, "sentence": s, "fact_ids": ids, "structural": structural,
                        "numbers": nums_info, "reasons": reasons, "passed": not reasons})
    # header lines must not carry figures
    for bi, b in enumerate(blocks):
        if b["kind"] == "header" and re.search(r"\d", re.sub(r"^[\s*#]*\d+[.)]\s*", "", b["text"])):
            results.append({"block": bi, "index": -1, "sentence": b["text"], "fact_ids": [], "structural": False,
                            "numbers": [], "reasons": ["header_has_number"], "passed": False})
    return results


def rebuild(blocks, results):
    """Script text without failed sentences; headers with nothing left under them are removed."""
    bad = {(r["block"], r["index"]) for r in results if not r["passed"]}
    out, pending_header = [], None
    for bi, b in enumerate(blocks):
        if b["kind"] == "header":
            pending_header = None if (bi, -1) in bad else b["text"]
            if pending_header and (bi, -1) not in bad:
                pass
            continue_header = pending_header
            if continue_header:
                out.append(("H", continue_header))
            continue
        kept = [s for si, s in enumerate(b["sentences"]) if (bi, si) not in bad]
        if kept:
            out.append(("P", " ".join(kept)))
    lines, i = [], 0
    while i < len(out):
        kind, text = out[i]
        if kind == "H" and (i + 1 >= len(out) or out[i + 1][0] == "H"):
            i += 1
            continue
        lines.append(text)
        i += 1
    return "\n\n".join(lines)


def counters(results):
    claims = [r for r in results if not r["structural"] and r["index"] >= 0]
    nums = [n for r in claims for n in r["numbers"]]
    return {"claim_sentences": len(claims), "claims_passed": sum(r["passed"] for r in claims),
            "claims_failed": sum(not r["passed"] for r in claims),
            "figures_checked": len(nums), "figures_verified": sum(n["matched"] for n in nums)}
