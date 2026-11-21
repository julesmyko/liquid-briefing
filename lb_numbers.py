"""Locale-aware number extraction and matching (en / nl / de).

Used twice:
  1. on article sentences, to know which figures a fact really contains;
  2. on the spoken script, to prove every figure the listener hears is in a fact.
"""
from __future__ import annotations
import re

PCT_WORDS = {"percentage points", "percentage point", "procentpunten", "procentpunt",
             "prozentpunkte", "prozentpunkt", "percent", "per cent", "procent", "prozent", "pct"}
BP_WORDS = {"basis points", "basis point", "basispunten", "basispunt", "basispunkte",
            "basispunkt", "bps", "bp"}
SCALE = {"thousand": 1e3, "duizend": 1e3, "tausend": 1e3,
         "million": 1e6, "miljoen": 1e6, "millionen": 1e6, "mln": 1e6, "mn": 1e6, "mio": 1e6,
         "billion": 1e9, "bn": 1e9, "miljard": 1e9, "mrd": 1e9, "milliarden": 1e9, "milliarde": 1e9,
         "trillion": 1e12, "biljoen": 1e12, "billionen": 1e12}
SCALE_ATT = {"bn": 1e9, "m": 1e6, "k": 1e3, "b": 1e9}   # only valid right after a currency symbol or code: $40m, USD 40B
MONTHS = set("""january february march april may june july august september october november december
januari februari maart mei juni juli augustus oktober
januar februar märz juli dezember""".split())

_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_WORDS = "|".join(re.escape(w) for w in sorted(PCT_WORDS | BP_WORDS | set(SCALE), key=len, reverse=True))
TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?P<cur>USD|EUR|GBP|[$€£])?\s?(?P<num>" + _NUM + r")"
    r"(?:\s?(?P<pct>%)|\s?(?P<word>" + _WORDS + r")\b|(?P<att>bn|m|k|b)\b)?", re.I)

# Figures spelled out as words ("drie procent") cannot be audited, so they are refused.
_NUMBER_WORDS = ("een|twee|drie|vier|vijf|zes|zeven|acht|negen|tien|elf|twaalf|dertien|veertien|vijftien|twintig|"
                 "dertig|veertig|vijftig|zestig|zeventig|tachtig|negentig|honderd|duizend|"
                 "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
                 "sixty|seventy|eighty|ninety|hundred|"
                 "ein|eine|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|zwanzig|dreißig|hundert|tausend")
_FIG_UNITS = ("procent|percent|per cent|prozent|miljoen|miljard|million|billion|millionen|milliarden|"
              "basispunten|basis points|basispunkte|procentpunten|percentage points")
NUMBER_WORD_FIGURE = re.compile(r"\b(?:" + _NUMBER_WORDS + r")(?:\s+komma\s+\w+)?\s+(?:" + _FIG_UNITS + r")\b", re.I)


def parse_value(s: str, lang: str) -> float:
    """'1.234,5' (nl/de) and '1,234.5' (en) -> 1234.5; ambiguous 'x,ddd' follows the language."""
    s = s.strip()
    dec_comma = lang in ("nl", "de")
    if "." in s and "," in s:
        last = max(s.rfind("."), s.rfind(","))
        dec = s[last]
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2:
            s = "".join(parts)
        else:
            a, b = parts
            thousands = len(b) == 3 and a != "0" and len(a) <= 3 and ((sep == "," and not dec_comma) or (sep == "." and dec_comma))
            s = a + b if thousands else a + "." + b
    return float(s)


def extract_numbers(text: str, lang: str = "en"):
    """Every figure in `text` as {raw, value, kind(pct|bp|num), exempt}. 'exempt' = year or date day."""
    out = []
    for m in TOKEN.finditer(text):
        try:
            v = parse_value(m.group("num"), lang)
        except ValueError:
            continue
        cur = m.group("cur")
        word = (m.group("word") or "").lower()
        att = (m.group("att") or "").lower() if cur else ""
        kind = "num"
        if m.group("pct") or word in PCT_WORDS:
            kind = "pct"
        elif word in BP_WORDS:
            kind = "bp"
        mult = SCALE.get(word, 1.0)
        if att:
            mult = SCALE_ATT[att]
        value = v * mult
        nxt = re.findall(r"[A-Za-zÀ-ÿ]+", text[m.end():m.end() + 16])
        exempt = False
        if kind == "num" and not cur and not word and not att:
            if float(value).is_integer() and 1900 <= value <= 2100:
                exempt = True
            if nxt and nxt[0].lower() in MONTHS:
                exempt = True
        out.append({"raw": m.group(0).strip(), "value": value, "kind": kind, "exempt": exempt})
    return out


def dedupe_numbers(nums):
    seen, out = set(), []
    for n in nums:
        key = (n["kind"], round(n["value"], 9))
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def same_number(a, b) -> bool:
    return a["kind"] == b["kind"] and abs(a["value"] - b["value"]) <= 1e-9 * max(1.0, abs(a["value"]))


def check_spoken_numbers(sentence: str, lang: str, allowed):
    """-> (checked, unsupported_raw, number_word_figures). `allowed` = number dicts of the cited facts."""
    checked = [n for n in extract_numbers(sentence, lang) if not n["exempt"]]
    unsupported = [n["raw"] for n in checked if not any(same_number(n, a) for a in allowed)]
    words = [m.group(0) for m in NUMBER_WORD_FIGURE.finditer(sentence)]
    return checked, unsupported, words
