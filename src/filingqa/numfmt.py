"""Number handling: how a raw XBRL value looks inside a filing, and how to read one in an answer.

XBRL stores 391035000000. The filing prints "$ 391,035" under a "(In millions)" caption, and
MD&A prose says "$391.0 billion". The gold-chunk matcher has to bridge all of these.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from .citations import CITATION_GROUP, CITATION_ID

UNITS = {
    "trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
    "tn": 1e12, "bn": 1e9, "b": 1e9, "m": 1e6, "mm": 1e6, "k": 1e3,
}  # fmt: skip

# Tokenize before validating amounts. A malformed/foreign prefix cannot make a regex
# retry at its inner digits: each complete numeric lexeme is considered exactly once.
_LEXEME = re.compile(
    r"(?P<space>\s+)|"
    r"(?P<number>(?:\d[\d.,]*|\.\d[\d.,]*)(?:[eE][+\-−]?\d+)?)|"
    r"(?P<word>[^\W\d]\w*)|(?P<symbol>.)", re.S,
)
_RAW_NUMBER = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_FOREIGN_WORDS = frozenset("eur gbp jpy cny chf cad aud rmb euro euros pound pounds yen".split())
_USD_WORDS = frozenset({"usd", "us", "dollar", "dollars"})
_CURRENCY_WORDS = _FOREIGN_WORDS | _USD_WORDS
_PREFIXES = {"", "$", "+", "-", "−", "+$", "-$", "−$", "$+", "$-", "$−", "(", "$(", "($"}
_NOT_AMOUNT_WORDS = frozenset({"percent", "percentage", "bps", "quadrillion", "hundred"})
_FORMATTING = frozenset("*_`~\\")
_HTML_LIKE = re.compile(
    r"<\s*(?:/?[A-Za-z]|!|\?)|&#(?:[xX][0-9A-Fa-f]+|[0-9]+);?|&[A-Za-z][A-Za-z0-9]*;"
)


@lru_cache(maxsize=512)
def _character_info(char: str) -> tuple[str, str, str]:
    return unicodedata.category(char), unicodedata.name(char, ""), unicodedata.normalize("NFKC", char)


def _sign_like(text: str) -> bool:
    if len(text) != 1:
        return False
    category, name, _ = _character_info(text)
    return category == "Pd" or any(part in name for part in ("MINUS", "HYPHEN", "PLUS", "DASH"))


def _foreign_symbol(text: str) -> bool:
    return len(text) == 1 and text != "$" and _character_info(text)[0] == "Sc"


def _control_or_mark(text: str) -> bool:
    return (len(text) == 1 and not text.isspace()
            and _character_info(text)[0][0] in {"C", "M"})


def _noncanonical_parenthesis(text: str) -> bool:
    if len(text) != 1 or text in {"(", ")"}:
        return False
    _, name, normalized = _character_info(text)
    return normalized in {"(", ")"} or "PARENTHESIS" in name


def _noncanonical_separator(text: str) -> bool:
    if len(text) != 1 or text in {".", ","}:
        return False
    _, name, normalized = _character_info(text)
    return (normalized in {".", ","} or "DECIMAL SEPARATOR" in name
            or "THOUSANDS SEPARATOR" in name)


def _unsupported_marker(text: str) -> bool:
    return (_foreign_symbol(text) or _control_or_mark(text) or _noncanonical_parenthesis(text)
            or _noncanonical_separator(text) or (_sign_like(text) and text not in {"+", "-", "−"}))


def _prefix_mark(text: str) -> bool:
    return text in {"$", "(", ")", "+"} or _sign_like(text) or _unsupported_marker(text)


def _currency_name(text: str) -> str:
    # Classification only, never acceptance/normalization: a decorated known code is
    # consumed with its prefix and then rejected by the exact supported grammar.
    plain = "".join(char for char in text if not _control_or_mark(char))
    return unicodedata.normalize("NFKC", plain).lower().strip("_")


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    start: int
    end: int


@dataclass
class _Amount:
    number: _Token
    end: int
    value: float | None
    accounting_start: int | None = None
    marked: bool = False
    non_monetary: bool = False


def _tokens(text: str) -> list[_Token]:
    out: list[_Token] = []
    for match in _LEXEME.finditer(text):
        token = _Token(match.lastgroup, match.group(), match.start(), match.end())
        if out and out[-1].end == token.start:
            previous = out[-1]
            decorated_word = previous.kind == "word" and (
                _control_or_mark(token.text)
                or (token.kind == "word" and _control_or_mark(previous.text[-1]))
            )
            malformed_number = previous.kind == "number" and (
                _noncanonical_separator(token.text)
                or (token.kind == "number" and _noncanonical_separator(previous.text[-1]))
            )
            if decorated_word or malformed_number:
                out[-1] = _Token(previous.kind, previous.text + token.text, previous.start, token.end)
                continue
        out.append(token)
    return out


def _previous(tokens: list[_Token], index: int) -> int:
    index -= 1
    while index >= 0 and tokens[index].kind == "space":
        index -= 1
    return index


def _next(tokens: list[_Token], index: int) -> int:
    while index < len(tokens) and tokens[index].kind == "space":
        index += 1
    return index


def _unit(token: _Token) -> str:
    name = token.text.lower().removesuffix("s")
    return name if token.kind == "word" and name in UNITS else ""


def _regional_us(tokens: list[_Token], index: int) -> bool:
    # non-US/ex-US are ordinary adjectives, not a unary sign before a currency code.
    return (
        tokens[index].text.lower() == "us" and index >= 2
        and tokens[index - 1].text == "-" and tokens[index - 2].kind == "word"
        and tokens[index - 2].end == tokens[index - 1].start
        and tokens[index - 1].end == tokens[index].start
    )


def _formatting_token(token: _Token) -> bool:
    return bool(token.text) and all(char in _FORMATTING for char in token.text)


def _skip_formatting(tokens: list[_Token], start: int) -> int:
    while start < len(tokens) and (tokens[start].kind == "space" or _formatting_token(tokens[start])):
        start += 1
    return start


def _scale_like_label(token: _Token) -> bool:
    if token.kind != "word":
        return False
    label = _currency_name(token.text)
    return label.removesuffix("s") in UNITS or any(
        label.startswith(scale) for scale in ("million", "billion", "trillion", "thousand")
    )


def _adjacency_gap(text: str) -> str:
    # Formatting is transparent only for conservative adjacency checks, not for parsing
    # an amount or assigning its sign/unit.
    return "".join(char for char in text if char not in _FORMATTING)


def _attached_before_formatting(tokens: list[_Token], start: int) -> bool:
    """Apply the existing attached-word/ID rule across touching formatting only."""
    cursor = start
    while (cursor > 0 and tokens[cursor - 1].end == tokens[cursor].start
           and _formatting_token(tokens[cursor - 1])):
        cursor -= 1
    if cursor == 0 or tokens[cursor - 1].end != tokens[cursor].start:
        return False
    before = tokens[cursor - 1]
    return before.kind == "word" or before.text in {"#", ".", ","}


def _composite_dollar(tokens: list[_Token], start: int) -> bool:
    """A word touching formatting then $ is still an unsupported composite code."""
    if tokens[start].kind != "word":
        return False
    cursor = start + 1
    while (cursor < len(tokens) and tokens[cursor - 1].end == tokens[cursor].start
           and _formatting_token(tokens[cursor])):
        cursor += 1
    return (cursor < len(tokens) and tokens[cursor].text == "$"
            and tokens[cursor - 1].end == tokens[cursor].start)


def _hidden_prefix_marker(tokens: list[_Token], start: int) -> bool:
    """Reject punctuation wrappers hiding a prior monetary marker, without decoding them.

    The canonical prefix has already been consumed. Scan the preceding punctuation/space
    run only; an ordinary word/number is a hard boundary. Thus **-$45 and :$45 remain
    valid, but -**$45 and -\\$45 cannot lose their leading minus.
    """
    position = start - 1
    while position >= 0:
        token = tokens[position]
        if _formatting_token(token):
            position -= 1
            continue
        if token.kind == "word":
            name = _currency_name(token.text)
            if name in _CURRENCY_WORDS and not _regional_us(tokens, position):
                if name in _USD_WORDS and token.text.lower() == name:
                    position -= 1  # plain US prose/currency word, still check earlier markers
                    continue
                return True
            break
        if token.kind == "number":
            break
        if (token.text in {"(", "$"} or _sign_like(token.text)
                or _unsupported_marker(token.text)):
            return True
        position -= 1
    return False


def _amount(tokens: list[_Token], index: int) -> _Amount:
    number = tokens[index]
    start, previous = index, _previous(tokens, index)
    while previous >= 0:
        token = tokens[previous]
        marked = token.kind == "symbol" and _prefix_mark(token.text)
        currency = token.kind == "word" and _currency_name(token.text) in _CURRENCY_WORDS
        if not (marked or currency) or (currency and _regional_us(tokens, previous)):
            break
        start, previous = previous, _previous(tokens, previous)
    prefix = [t for t in tokens[start:index] if t.kind != "space"]
    valid = not _hidden_prefix_marker(tokens, start)
    # A sign followed by whitespace can be a bullet or label separator. Reject the
    # complete amount, including at line start; never normalize it into either sign.
    for position, token in enumerate(prefix):
        following = prefix[position + 1] if position + 1 < len(prefix) else number
        if token.text in {"+", "-", "−"} and token.end < following.start:
            valid = False
    # An attached ordinary word makes forms such as C$ / HK$ / loss-$ unsupported.
    # We still consume this number once; there is no fallback parsing of its interior.
    if _attached_before_formatting(tokens, start):
        valid = False
    usd_code = False
    if prefix and prefix[0].kind == "word" and prefix[0].text.lower() in _USD_WORDS:
        usd_code = True
        first = prefix.pop(0)
        # Codes need whitespace before the remaining sign/$/number. Contiguous USD-45,
        # US$45, and signs before the code deliberately fail closed.
        following = prefix[0] if prefix else number
        if first.end == following.start:
            valid = False
    compact = "".join(t.text for t in prefix)
    if compact not in _PREFIXES:
        valid = False

    # Consume closing/scale/currency suffix tokens before deciding validity.
    cursor, end, closed = _next(tokens, index + 1), number.end, 0
    if cursor < len(tokens) and tokens[cursor].text == ")":
        closed += 1
        end, cursor = tokens[cursor].end, _next(tokens, cursor + 1)
    unit = _unit(tokens[cursor]) if cursor < len(tokens) else ""
    if unit:
        end, cursor = tokens[cursor].end, _next(tokens, cursor + 1)
    if cursor < len(tokens) and tokens[cursor].text == ")":
        closed += 1
        end, cursor = tokens[cursor].end, _next(tokens, cursor + 1)
    suffix_usd, non_monetary = False, False
    compound = _skip_formatting(tokens, cursor)
    if compound < len(tokens) and _sign_like(tokens[compound].text):
        following = _skip_formatting(tokens, compound + 1)
        if following < len(tokens) and _scale_like_label(tokens[following]):
            valid = False  # obscured sign-scale compounds must not become raw $45
            end = max(end, tokens[following].end)
    if cursor < len(tokens):
        suffix = tokens[cursor]
        name = suffix.text.lower()
        if _currency_name(suffix.text) in _CURRENCY_WORDS or _foreign_symbol(suffix.text) or suffix.text == "$":
            suffix_usd = name in {"usd", "dollar", "dollars"} and suffix.start > end
            if not suffix_usd:
                valid = False
            end, cursor = suffix.end, _next(tokens, cursor + 1)
            if cursor < len(tokens) and _prefix_mark(tokens[cursor].text):
                valid = False
        elif _unsupported_marker(suffix.text):
            valid = False
        elif _composite_dollar(tokens, cursor):
            valid = False  # unsupported code-prefixed dollar suffix, e.g. 45 million C$
        elif (suffix.kind == "word" and any(_currency_name(suffix.text).startswith(scale) for scale in
                ("million", "billion", "trillion", "thousand"))):
            valid = False  # malformed scale token must not fall back to raw magnitude
            end = suffix.end
        elif suffix.text == "%" or name in _NOT_AMOUNT_WORDS or name == "basis":
            valid = False
            non_monetary = suffix.text == "%" or name in {"percent", "percentage", "bps", "basis"}
        elif suffix.kind == "word" and suffix.start == end:
            valid = False  # 45xyz / malformed attached scale, not a smaller bare amount

    # Look across closing wrappers only to reject hidden currency/scale context. Do not
    # turn wrappers into syntax support, and do not cross independent-amount boundaries.
    look = _skip_formatting(tokens, cursor)
    if look < len(tokens):
        token = tokens[look]
        label = _currency_name(token.text)
        stopped = token.text in {";", ",", "(", ")"} or _sign_like(token.text)
        composite_dollar = _composite_dollar(tokens, look)
        if not stopped and (label in _CURRENCY_WORDS or _foreign_symbol(token.text)
                            or _unsupported_marker(token.text) or composite_dollar):
            valid = False
        if not stopped and _scale_like_label(token):
            valid = False
            end = max(end, token.end)
        if not stopped and (token.text == "%" or label in _NOT_AMOUNT_WORDS or label == "basis"):
            valid = False
            non_monetary = non_monetary or token.text == "%" or label in {
                "percent", "percentage", "bps", "basis"
            }
            end = max(end, token.end)

    # Inspect a complete trailing chain of currency/sign tokens, too. A foreign marker
    # after a separating sign (45 million - EUR) is still not a USD amount. Stop at
    # ordinary prose, punctuation or another number; range handling below owns the latter.
    tail = cursor
    while tail < len(tokens):
        token = tokens[tail]
        name = token.text.lower()
        if token.kind == "space" or _formatting_token(token):
            tail += 1
            continue
        if _unsupported_marker(token.text) or _currency_name(token.text) in _FOREIGN_WORDS:
            valid = False
        elif _composite_dollar(tokens, tail):
            valid = False  # C$/HK$/US$ suffix layouts are unsupported
        elif not ((token.kind == "symbol" and _prefix_mark(token.text))
                  or (token.kind == "word" and _currency_name(token.text) in _USD_WORDS)):
            break
        tail += 1

    parenthesized = "(" in compact
    if closed != int(parenthesized):
        valid = False
    raw = number.text
    # A single final comma/period may be sentence punctuation. Keep it outside the
    # amount's span for the range check; malformed inner grouping still fails fullmatch.
    trailing = raw[-1:] in {".", ","}
    if trailing:
        raw = raw[:-1]
        if end == number.end:
            end -= 1
        if unit:
            valid = False
    if not _RAW_NUMBER.fullmatch(raw):
        valid = False
    currency = "$" in compact or usd_code or suffix_usd
    if parenthesized and not (currency or unit or "," in raw):
        valid = False  # a bare (5) may be a note/reference
    value = None
    if valid:
        num = float(raw.replace(",", ""))
        if not unit and not compact and not currency and "," not in raw and "." not in raw and 1900 <= num <= 2100:
            return _Amount(number, end, None)
        sign = -1.0 if parenthesized or "-" in compact or "−" in compact else 1.0
        result = sign * num * UNITS.get(unit, 1.0)
        value = result if math.isfinite(result) else None
    opening = next((t.start for t in prefix if t.text == "("), None)
    return _Amount(number, end, value, opening, currency or bool(unit), non_monetary)


def _range_connector(text: str) -> bool:
    parts = [t for t in _tokens(text) if t.kind != "space"]
    return (
        any(_sign_like(t.text) for t in parts)
        and all((t.kind == "symbol" and _prefix_mark(t.text))
                or (t.kind == "word" and _currency_name(t.text) in _CURRENCY_WORDS) for t in parts)
    )


def extract_numbers(text: str) -> list[float]:
    """Read amounts with a finite USD grammar, never retrying inside rejected tokens.

    Supported: raw magnitudes; explicit scale words; $ and spaced USD/dollar markers;
    ASCII +/- or Unicode minus attached to $ or digits; marked accounting parentheses. Bare years, citation IDs,
    percentages, listed foreign markers and unsupported code/sign layouts are excluded.
    Spaced signs (including Markdown bullets/label separators), noncanonical Unicode
    sign/dash characters, currency symbols other than ASCII $, attached control/combining
    markers, noncanonical parentheses/grouping and hyphenated scale compounds are rejected.
    Character classes are checked on encountered characters, without an import-time scan. Both endpoints of adjacent amounts joined
    only by a dash/currency connector are excluded as ambiguous ranges/arithmetic; use
    semicolons or words such as 'and' to separate independent amounts. Contradictory or
    unsupported currency labels such as 'non-USD $45 million' are conservatively excluded.
    An immediately following parenthesized restatement is excluded rather than assigned
    a negative sign; semicolon/and-separated accounting amounts remain supported.
    Numbered lists, prose parentheses, 'US dollars' suffixes and parenthesized-citation
    layouts are unsupported. Prefer one plain signed numeric amount plus a citation.

    Canonical bracketed citation groups are removed before adjacent-restatement checks;
    ordinary bracket/prose content is not normalized. Punctuation wrappers that hide
    earlier sign/currency/accounting markers are rejected, without decoding formatting.
    Benign wrappers before an intact canonical prefix remain supported. Only the formatting
    characters *_`~ and backslash are ignored in adjacency checks; hidden suffix scales or
    currency markers fail closed. HTML-like tags/entities reject the whole input without
    decoding (numeric entity references need no semicolon; named ones do). Touching
    formatting does not break attached word/code boundaries. Bare AT&T prose remains
    valid. Numeric grammar is ASCII.

    Numeric agreement is not verification of metric, period, unit context or entailment.
    """
    if _HTML_LIKE.search(text):
        return []  # reject whole HTML-like messages; never decode tags/entities into signs
    text = CITATION_GROUP.sub(" ", text)
    text = _ISO_DATE.sub(" ", CITATION_ID.sub(" ", text))
    tokens = _tokens(text)
    amounts = [_amount(tokens, i) for i, t in enumerate(tokens) if t.kind == "number"]
    ambiguous: set[int] = set()
    for i, (left, right) in enumerate(zip(amounts, amounts[1:], strict=False)):
        if not right.non_monetary and _range_connector(_adjacency_gap(text[left.end:right.number.start])):
            ambiguous.update((i, i + 1))
        if (right.accounting_start is not None and not left.non_monetary
                and (left.value is not None or left.marked)
                and not _adjacency_gap(text[left.end:right.accounting_start]).strip()):
            ambiguous.add(i + 1)
    return [a.value for i, a in enumerate(amounts) if a.value is not None and i not in ambiguous]


def numeric_match(text: str, value: float, tol: float = 0.001) -> bool:
    """Match a signed numeric answer within relative tolerance (default 0.1%).

    Numeric agreement does not mean the answer is supported by its citation. A loss must
    carry an explicit minus/accounting sign; words such as "loss" alone are not interpreted.
    """
    if not math.isfinite(value) or not math.isfinite(tol) or tol < 0:
        raise ValueError("value and tolerance must be finite, with tolerance >= 0")
    return any(
        (c > 0) == (value > 0) and (c < 0) == (value < 0)
        and abs(c - value) <= tol * abs(value)
        for c in extract_numbers(text)
    )


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
