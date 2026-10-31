"""Canonical chunk citation syntax shared by answer parsing and numeric preprocessing.

Chunk numbers are formatted with :04d, a minimum width, not a four-digit truncation.
Boundaries prevent an allowed ID from being credited inside another/malformed identifier.
"""

import re

ID_BODY = r"[A-Z][A-Z.]{0,5}-FY[0-9]{4}#[0-9]{4,}"
CITATION_ID = re.compile(r"(?<![\w.#-])" + ID_BODY + r"(?![\w.#-])")
CITATION_GROUP = re.compile(
    r"\[\s*" + ID_BODY + r"(?:\s*[,;]\s*" + ID_BODY + r")*\s*\]"
)
