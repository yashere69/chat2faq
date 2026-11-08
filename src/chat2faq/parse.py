"""Parse WhatsApp chat exports (Android and iOS, 12- and 24-hour clocks, day-first,
month-first or year-first dates with /, . or - between the parts).

A message can span several lines. Any line that doesn't start with a timestamp belongs to
the message above it. Lines without "Name: " after the timestamp are system notices
(encryption banner, "X added Y") and are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Exports carry invisible direction marks (around phone numbers, before attachments) and
# sometimes a byte-order mark. They are never content, so they are removed before matching.
_MARKS = dict.fromkeys(
    map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff"),
    None,
)
_DATE = r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}"
# am/pm as Android and iOS write it in English locales, and in Hindi
_AMPM = r"(?:[ap]\.?\s?m\.?|पूर्वाह्न|अपराह्न)"
_GAP = "[ \u00a0\u202f]?"  # newer exports put a narrow no-break space before am/pm
_ANDROID = re.compile(
    rf"^(?P<d>{_DATE}),? (?P<t>\d{{1,2}}[:.]\d{{2}}){_GAP}(?P<ap>{_AMPM})?\s[-–] (?P<rest>.*)$",
    re.I,
)
_IOS = re.compile(
    rf"^\[(?P<d>{_DATE}),? (?P<t>\d{{1,2}}[:.]\d{{2}}(?:[:.]\d{{2}})?){_GAP}(?P<ap>{_AMPM})?\]"
    r" (?P<rest>.*)$",
    re.I,
)


@dataclass
class Message:
    source: str
    line: int
    at: datetime
    sender: str
    text: str


# What WhatsApp writes in place of content it didn't export, and notices it writes with a
# sender in front (iOS puts the contact's name on the encryption banner). Not customer text.
_PLACEHOLDER = re.compile(
    r"^(?:<media omitted>|(?:image|video|audio|sticker|gif|document|contact card) omitted"
    r"|this message was deleted\.?|you deleted this message\.?|missed (?:voice|video) call"
    r"|null|waiting for this message.*|<attached: [^>]+>|.+ \(file attached\)"
    r"|location: https?://\S+|live location shared"
    r"|messages and calls are end-to-end encrypted.*|your security code with .*"
    r"|this business (?:uses|is working with) .*|disappearing messages .*"
    r"|.+ changed (?:their|the) phone number.*)$",
    re.I,
)
_EDITED = re.compile(r"\s*<This message was edited>$")


def is_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER.match(text.translate(_MARKS).strip()))


def _clean_sender(name: str) -> str:
    """iOS marks non-contacts with a tilde ("~ Ravi"); phone numbers come wrapped in
    direction marks. Both would make one person look like two."""
    return " ".join(name.translate(_MARKS).replace("\u00a0", " ").lstrip("~").split())


def _parts(d: str) -> tuple[int, int, int]:
    a, b, c = (int(x) for x in re.split(r"[/.\-]", d))
    return a, b, c


def date_order(text: str) -> str:
    """'dmy' or 'mdy' for one export. India writes day first, but a phone set to a US
    locale exports 12/25/26. Any first number above 12 settles it as dmy, any second
    number above 12 as mdy; with no evidence either way, day first."""
    firsts, seconds = set(), set()
    for raw in text.splitlines():
        m = _ANDROID.match(raw.translate(_MARKS)) or _IOS.match(raw.translate(_MARKS))
        if m:
            a, b, _ = _parts(m.group("d"))
            if a > 31:  # year first: no ambiguity to settle
                continue
            firsts.add(a)
            seconds.add(b)
    if any(x > 12 for x in firsts):
        return "dmy"
    if any(x > 12 for x in seconds):
        return "mdy"
    return "dmy"


def _when(d: str, t: str, ap: str | None, order: str = "dmy") -> datetime:
    a, b, c = _parts(d)
    if a > 31:  # 2026-01-11
        year, month, day = a, b, c
    else:
        year = c
        day, month = (a, b) if order == "dmy" else (b, a)
    if year < 100:
        year += 2000
    parts = [int(x) for x in re.split(r"[:.]", t)]
    hour, minute = parts[0], parts[1]
    second = parts[2] if len(parts) > 2 else 0
    if ap:
        pm = ap.lower().startswith("p") or ap == "अपराह्न"
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
        raw = raw.translate(_MARKS)
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
        out.append(Message(source, n, at, _clean_sender(sender), body))
    for msg in out:  # the edit marker ends the message, which may be several lines long
        msg.text = _EDITED.sub("", msg.text)
    return out


def read_export(path: Path) -> str:
    """Exports are UTF-8, but one re-saved by Notepad or Excel may be UTF-16 or carry a
    BOM. Undecodable bytes become U+FFFD rather than stopping the run."""
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def parse_path(path: Path, order: str = "auto") -> list[Message]:
    files = sorted(path.glob("*.txt")) if path.is_dir() else [path]
    msgs: list[Message] = []
    for f in files:
        msgs += parse_text(read_export(f), f.name, order)
    return msgs
