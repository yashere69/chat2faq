from datetime import datetime

import pytest

import chat2faq.redact as redact_mod
from chat2faq.parse import parse_text

ANDROID = (
    "07/01/26, 10:00 am - Messages and calls are end-to-end encrypted.\n"
    "07/01/26, 10:01 am - Asha Sharma: hi\n"
    "07/01/26, 10:02 pm - Asha Sharma: first line\n"
    "second line\n"
    "07/01/26, 22:15 - Indigo Loom: 24-hour clock reply\n"
)
IOS = "[17/01/26, 12:05:09 PM] Kavya Reddy: XL ka bust kitna hai?\n"


def test_android_formats_multiline_and_system_lines():
    msgs = parse_text(ANDROID)
    assert [m.sender for m in msgs] == ["Asha Sharma", "Asha Sharma", "Indigo Loom"]
    assert msgs[1].text == "first line\nsecond line"
    assert msgs[1].at == datetime(2026, 1, 7, 22, 2)
    assert msgs[2].at == datetime(2026, 1, 7, 22, 15)
    assert msgs[0].line == 2


def test_ios_format():
    (m,) = parse_text(IOS)
    assert m.sender == "Kavya Reddy" and m.at == datetime(2026, 1, 17, 12, 5, 9)


def test_twelve_am_is_midnight():
    (m,) = parse_text("01/02/26, 12:30 am - A: x\n")
    assert m.at.hour == 0


@pytest.mark.parametrize("use_parda", [True, False])
def test_redaction_backends(monkeypatch, use_parda):
    if not use_parda:
        monkeypatch.setattr(redact_mod, "_parda", lambda: None)
    elif redact_mod._parda() is None:
        pytest.skip("parda not installed")
    out = redact_mod.redact("call 9876501931 or mail asha@example.com, refund asha12@okicici")
    assert "9876501931" not in out and "asha@example.com" not in out
    assert "asha12@okicici" not in out
