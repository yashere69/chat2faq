"""Remove personal details before anything is clustered or written out.

If `parda` is installed, its detectors are used: check-digit validation, Devanagari digits,
spoken numbers. Otherwise a small built-in set of patterns covers the common cases. Either
way the FAQ never contains a customer's phone number, email, UPI id or PAN.
"""

from __future__ import annotations

import re

_BUILTIN = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("UPI", re.compile(r"[\w.-]{2,}@[a-zA-Z][a-zA-Z0-9]+\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.I)),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
]


def _parda():
    try:
        from parda.detect import detect
    except ImportError:
        return None
    return detect


def redact(text: str) -> str:
    detect = _parda()
    if detect is not None:
        out, last = [], 0
        for s in detect(text):
            out += [text[last : s.start], f"[{s.kind}]"]
            last = s.end
        return "".join(out) + text[last:]
    for kind, rx in _BUILTIN:
        text = rx.sub(f"[{kind}]", text)
    return text


def backend() -> str:
    return "parda" if _parda() is not None else "built-in patterns"
