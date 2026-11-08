"""--probe: asking the mined FAQ questions it was not built from."""

from pathlib import Path

import pytest


def test_probe_questions_against_the_faq(tmp_path, capsys):
    from chat2faq.cli import main
    from chat2faq.evaluate import load_probe

    probe = tmp_path / "probe.txt"
    probe.write_text("COD milta hai?\nसाइज़ चार्ट भेज दो\n", encoding="utf-8")
    examples = Path(__file__).resolve().parent.parent / "examples"
    assert (
        main([str(examples / "exports"), "--business", "Indigo Loom", "--probe", str(probe)]) == 0
    )
    out = capsys.readouterr().out
    assert "probe: 2 questions" in out and "size chart" in out
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"text": "ok"}\n{"txt": "no"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        load_probe(bad)
