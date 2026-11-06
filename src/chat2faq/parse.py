"""Parse WhatsApp chat exports (Android and iOS, 12- and 24-hour clocks).

A message can span several lines. Any line that doesn't start with a timestamp belongs to
the message above it. Lines without "Name: " after the timestamp are system notices
(encryption banner, "X added Y") and are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_ANDROID = re.compile(
    r"^(?P<d>\d{1,2}/\d{1,2}/\d{2,4}), (?P<t>\d{1,2}:\d{2})(?:[   ](?P<ap>[ap]\.?m\.?))?"
    r" - (?P<rest>.*)$",
    re.I,
)
_IOS = re.compile(
    r"^‎?\[(?P<d>\d{1,2}/\d{1,2}/\d{2,4}), (?P<t>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:[   ](?P<ap>[AP]M))?\] (?P<rest>.*)$",
    re.I,
)


@dataclass
class Message:
    source: str
    line: int
    at: datetime
    sender: str
    text: str


# What WhatsApp writes in place of content it didn't export. Not customer text.
PLACEHOLDERS = {
    "<media omitted>",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "gif omitted",
    "document omitted",
    "contact card omitted",
    "this message was deleted",
    "you deleted this message",
    "missed voice call",
    "missed video call",
    "null",
    "waiting for this message",
}
_EDITED = re.compile(r"\s*<This message was edited>$")


def is_placeholder(text: str) -> bool:
    return text.replace("\u200e", "").strip().lower() in PLACEHOLDERS


def date_order(text: str) -> str:
    """'dmy' or 'mdy' for one export. India writes day first, but a phone set to a US
    locale exports 12/25/26. Any first number above 12 settles it as dmy, any second
    number above 12 as mdy; with no evidence either way, day first."""
    firsts, seconds = set(), set()
    for raw in text.splitlines():
        m = _ANDROID.match(raw) or _IOS.match(raw)
        if m:
            a, b, _ = m.group("d").split("/")
            firsts.add(int(a))
            seconds.add(int(b))
    if any(x > 12 for x in firsts):
        return "dmy"
    if any(x > 12 for x in seconds):
        return "mdy"
    return "dmy"


def _when(d: str, t: str, ap: str | None, order: str = "dmy") -> datetime:
    a, b, year = (int(x) for x in d.split("/"))
    day, month = (a, b) if order == "dmy" else (b, a)
    if year < 100:
        year += 2000
    parts = [int(x) for x in t.split(":")]
    hour, minute = parts[0], parts[1]
    second = parts[2] if len(parts) > 2 else 0
    if ap:
        pm = ap.lower().startswith("p")
        hour = hour % 12 + (12 if pm else 0)
    return datetime(year, month, day, hour, minute, second)


def parse_text(text: str, source: str = "<text>", order: str = "auto") -> list[Message]:
    """Parse one export. `order` is 'dmy', 'mdy' or 'auto' (decide from the dates)."""
    if order == "auto":
        order = date_order(text)
    if order not in ("dmy", "mdy"):
        raise ValueError("date order must be dmy, mdy or auto")
    out: list[Message] = []
    skip_continuation = False
    for n, raw in enumerate(text.splitlines(), start=1):
        m = _ANDROID.match(raw) or _IOS.match(raw)
        if not m:
            if out and raw.strip() and not skip_continuation:
                out[-1].text += "\n" + raw
            continue
        sender, sep, body = m.group("rest").partition(": ")
        skip_continuation = not sep or is_placeholder(body)
        if skip_continuation:
            continue  # system notice, or media/deleted placeholder
        try:
            at = _when(m.group("d"), m.group("t"), m.group("ap"), order)
        except ValueError as e:
            raise ValueError(f"{source}:{n}: bad date {m.group('d')!r} ({e})") from e
        body = _EDITED.sub("", body)
        out.append(Message(source, n, at, sender.strip(), body))
    return out


def parse_path(path: Path, order: str = "auto") -> list[Message]:
    files = sorted(path.glob("*.txt")) if path.is_dir() else [path]
    msgs: list[Message] = []
    for f in files:
        msgs += parse_text(f.read_text(encoding="utf-8", errors="replace"), f.name, order)
    return msgs
