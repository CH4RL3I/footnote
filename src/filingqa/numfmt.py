"""Number handling: how a raw XBRL value looks inside a filing, and how to read one in an answer.

XBRL stores 391035000000. The filing prints "$ 391,035" under a "(In millions)" caption, and
MD&A prose says "$391.0 billion". The gold-chunk matcher has to bridge all of these.
"""

from __future__ import annotations

import re

UNITS = {
    "trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
    "tn": 1e12, "bn": 1e9, "b": 1e9, "m": 1e6, "mm": 1e6, "k": 1e3,
}  # fmt: skip

# optional sign/paren/$ , digits with thousands separators, optional decimals, optional unit word
_NUMBER = re.compile(
    r"(?P<neg>[-−(])?\s*\$?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<unit>trillion|billion|million|thousand|tn|bn|mm|b|m|k)\b)?",
    re.I,
)


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def extract_numbers(text: str) -> list[float]:
    """Every dollar-like quantity in an answer, as candidate values in dollars.

    "$391,035 million" -> 391035000000. A number with no unit word is ambiguous: filings print
    statements in millions, so it yields both the raw figure and figure x 1e6. Bare integers
    that look like years are ignored.
    """
    out: list[float] = []
    for m in _NUMBER.finditer(text):
        num = _to_float(m["num"])
        unit = (m["unit"] or "").lower()
        sign = -1.0 if m["neg"] and m["neg"] != "(" else 1.0
        if unit:
            out.append(sign * num * UNITS[unit])
        else:
            if "," not in m["num"] and "." not in m["num"] and 1900 <= num <= 2100:
                continue
            out.extend([sign * num * 1e6, sign * num])
    return out


def numeric_match(text: str, value: float, tol: float = 0.005) -> bool:
    """True if any number in text equals value within relative tolerance (default 0.5%)."""
    target = abs(value)
    return any(abs(abs(c) - target) <= tol * target for c in extract_numbers(text))


def filing_forms(value: float) -> list[str]:
    """Strings under which |value| (USD) may appear in a filing, most specific first."""
    v = abs(value)
    forms: list[str] = []
    for scale in (1e6, 1e3):  # statement tables in millions, or in thousands
        scaled = v / scale
        if scaled == round(scaled):
            forms.append(f"{scaled:,.0f}")
    if v >= 1e9:  # MD&A prose: "$391.0 billion", "$391 billion"
        b = v / 1e9
        forms += [f"{b:,.1f} billion", f"{b:,.2f} billion", f"{b:,.0f} billion"]
    forms = list(dict.fromkeys(forms))
    # Bare table figures need 4+ digits to be distinctive; "391.0 billion" carries its own unit.
    return [f for f in forms if " " in f or len(re.sub(r"\D", "", f)) >= 4]


def _pattern(form: str) -> re.Pattern:
    # Not glued to other digits/separators: "391,035" must not match inside "1,391,035".
    return re.compile(r"(?<![\d,.])" + re.escape(form) + r"(?!\d|,\d|\.\d)")


def contains_value(text: str, value: float) -> bool:
    return any(_pattern(f).search(text) for f in filing_forms(value))
