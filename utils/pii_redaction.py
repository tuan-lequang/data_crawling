"""Best-effort redaction of common contact details in free-text reviews.

This is a privacy safeguard, not a guarantee that all personal information is found.
"""
from __future__ import annotations

import re
import unicodedata

# Vietnamese mobile/landline-style numbers and international numbers beginning with +.
_PHONE_PATTERNS = (
    re.compile(r"(?<!\w)(?:\+?84|0)(?:[ .()\-]*\d){8,10}(?!\w)"),
    re.compile(r"(?<!\w)\+\d{1,3}(?:[ .()\-]*\d){7,14}(?!\w)"),
)
_EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.[A-Z]{2,}(?![\w-])")
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_CONTACT_RE = re.compile(
    r"(?i)\b(zalo|facebook|fb|telegram|whatsapp|sđt|sdt|phone)\s*[:：]\s*@?[\w.+-]{3,}"
)


def redact_pii_text(value: object) -> tuple[str | None, int]:
    """Normalize and redact common PII patterns; return (safe_text, replacement_count)."""
    if value is None:
        return None, 0
    try:
        if value != value:  # NaN
            return None, 0
    except Exception:
        pass
    text = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    count = 0

    def replace(pattern: re.Pattern, token: str, content: str) -> str:
        nonlocal count
        content, n = pattern.subn(token, content)
        count += n
        return content

    # Apply specific formats before the long-digit fallback.
    for pattern in _PHONE_PATTERNS:
        text = replace(pattern, "[phone]", text)
    text = replace(_EMAIL_RE, "[email]", text)
    text = replace(_URL_RE, "[url]", text)
    text = replace(_CONTACT_RE, "[contact]", text)
    text = replace(_LONG_DIGITS_RE, "[number]", text)
    # Preserve paragraph structure but trim excessive blank lines and edge whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return (text if text else None), count
