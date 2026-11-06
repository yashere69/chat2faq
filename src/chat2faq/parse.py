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


def _when(d: str, t: str, ap: str | None) -> datetime:
    day, month, year = (int(x) for x in d.split("/"))
    if year < 100:
        year += 2000
    parts = [int(x) for x in t.split(":")]
    hour, minute = parts[0], parts[1]
    second = parts[2] if len(parts) > 2 else 0
    if ap:
        pm = ap.lower().startswith("p")
        hour = hour % 12 + (12 if pm else 0)
    return datetime(year, month, day, hour, minute, second)


def parse_text(text: str, source: str = "<text>") -> list[Message]:
    out: list[Message] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        m = _ANDROID.match(raw) or _IOS.match(raw)
        if not m:
            if out and raw.strip():
                out[-1].text += "\n" + raw
            continue
        sender, sep, body = m.group("rest").partition(": ")
        if not sep:
            continue  # system notice
        out.append(
            Message(
                source, n, _when(m.group("d"), m.group("t"), m.group("ap")), sender.strip(), body
            )
        )
    return out


def parse_path(path: Path) -> list[Message]:
    files = sorted(path.glob("*.txt")) if path.is_dir() else [path]
    msgs: list[Message] = []
    for f in files:
        msgs += parse_text(f.read_text(encoding="utf-8"), f.name)
    return msgs
