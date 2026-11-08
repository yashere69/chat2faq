"""Export variants: each fixture in tests/fixtures is written to a format WhatsApp
produces on some phone, OS version or locale. None of it is real customer data."""

from datetime import datetime
from pathlib import Path

import pytest

from chat2faq.parse import parse_path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize(
    "name, expected",
    [
        (
            "android-in.txt",
            [
                ("+91 98765 43210", "COD hai?", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "Haan, ₹5,000 tak COD hai.", datetime(2026, 1, 11, 14, 50)),
                ("+91 98765 43210", "aur size chart?\nM ya L?", datetime(2026, 1, 11, 14, 52)),
            ],
        ),
        (
            "android-dots-24h.txt",
            [
                ("Asha", "shipping kitna hai?", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "₹79, ₹1,499 se upar free.", datetime(2026, 1, 11, 14, 49)),
            ],
        ),
        (
            "ios.txt",
            [
                ("Asha", "return kaise karu?", datetime(2026, 1, 11, 14, 47, 5)),
                ("Indigo Loom", "7 din mein, app se.", datetime(2026, 1, 11, 14, 55)),
            ],
        ),
        (
            "us-mdy.txt",
            [
                ("Ravi", "is COD available?", datetime(2026, 12, 25, 9, 5)),
                ("Indigo Loom", "Yes, up to ₹5,000.", datetime(2026, 12, 25, 9, 7)),
            ],
        ),
        (
            "ymd.txt",
            [
                ("Neha", "refund kab tak?", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "5-7 working days.", datetime(2026, 1, 11, 15, 2)),
            ],
        ),
        (
            "hindi-day-period.txt",
            [
                ("Kabir", "colour bleed hoga kya?", datetime(2026, 1, 11, 14, 47)),
                (
                    "Indigo Loom",
                    "Pehli wash thande paani mein karein.",
                    datetime(2026, 1, 11, 14, 50),
                ),
            ],
        ),
        (
            "bom-crlf.txt",
            [
                ("Om", "delivery kab hogi?", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "3-5 din.", datetime(2026, 1, 11, 14, 49)),
            ],
        ),
        (
            "utf16.txt",
            [
                ("Om", "delivery kab hogi?", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "3-5 din.", datetime(2026, 1, 11, 14, 49)),
            ],
        ),
        (
            "truncated.txt",
            [
                ("Om", "size chart bhej", datetime(2026, 1, 11, 14, 47)),
                ("Indigo Loom", "S 36, M 3", datetime(2026, 1, 11, 14, 49)),
            ],
        ),
    ],
)
def test_export_variant(name, expected):
    got = [(m.sender, m.text, m.at) for m in parse_path(FIXTURES / name)]
    assert got == expected
