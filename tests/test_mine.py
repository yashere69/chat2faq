from pathlib import Path

from chat2faq.cli import guess_business, main
from chat2faq.evaluate import load_labels, score
from chat2faq.mine import Vectorizer, cosine, group, is_question, merge_by_answer, pair, templatize
from chat2faq.parse import parse_path, parse_text

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_question_detection():
    assert is_question("COD available hai?")
    assert is_question("size chart bhej do please")
    assert is_question("kab tak aayega")
    assert not is_question("Namaste")
    assert not is_question("ok")


def test_templatize_removes_per_order_details():
    assert templatize("Order #1042 shipped: https://track.example.com/1042") == (
        "Order #[ORDER] shipped: [LINK]"
    )


def test_pairing_respects_thread_and_window():
    msgs = parse_text(
        "01/02/26, 10:00 am - Asha: COD hai?\n"
        "01/02/26, 10:01 am - Ravi: shipping free hai?\n"
        "01/02/26, 10:05 am - Store: Hi Ravi, ₹1,499 se upar free.\n"
        "01/02/26, 10:06 am - Store: Hi Asha, COD ₹5,000 tak hai.\n"
        "02/02/26, 10:00 am - Ravi: size chart?\n"
    )
    qas = {q.question.sender + ":" + q.asked: q.answered for q in pair(msgs, "Store")}
    assert qas["Asha:COD hai?"] == "Hi Asha, COD ₹5,000 tak hai."
    assert qas["Ravi:shipping free hai?"] == "Hi Ravi, ₹1,499 se upar free."
    assert qas["Ravi:size chart?"] is None  # nothing within six hours


def test_char_ngrams_tolerate_hinglish_spelling():
    v = Vectorizer(["kab aayega", "kab ayega", "refund kab"])
    assert cosine(v.vec("kab aayega"), v.vec("kab ayega")) > 0.5


def test_answer_merge_joins_differently_worded_questions():
    msgs = parse_text(
        "01/02/26, 10:00 am - A: shipping charges?\n"
        "01/02/26, 10:01 am - Store: ₹79 below ₹1,499.\n"
        "01/02/26, 11:00 am - B: delivery ka kitna lagega\n"
        "01/02/26, 11:01 am - Store: ₹79 below ₹1,499.\n"
    )
    qas = pair(msgs, "Store")
    v = Vectorizer([q.asked for q in qas] + [q.answered or "" for q in qas])
    assert len(group(qas, v, 0.3)) == 2
    assert len(merge_by_answer(group(qas, v, 0.3), v)) == 1


def test_sample_evaluation():
    msgs = parse_path(EXAMPLES / "exports")
    assert guess_business(msgs) == "Indigo Loom"
    r = score(pair(msgs, "Indigo Loom"), load_labels(EXAMPLES / "labels.jsonl"))
    assert r["intents_with_entry"] == r["intents"]
    assert r["purity"] > 90
    assert r["heldout_covered"] >= 0.8 * r["heldout"]


def test_cli_writes_outputs(tmp_path, capsys):
    out, jl = tmp_path / "faq.md", tmp_path / "faq.jsonl"
    assert (
        main(
            [
                str(EXAMPLES / "exports"),
                "--business",
                "Indigo Loom",
                "-o",
                str(out),
                "--jsonl",
                str(jl),
            ]
        )
        == 0
    )
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# FAQ mined from Indigo Loom chats")
    assert "Needs a lookup" in md
    assert "98765" not in md
    assert main([str(tmp_path / "missing.txt")]) == 2


def test_big_export_is_fast(tmp_path):
    import time

    lines = []
    for i in range(3000):
        lines.append(f"01/02/26, 10:{i % 60:02d} am - Customer {i}: shipping free hai?")
        lines.append(f"01/02/26, 10:{i % 60:02d} am - Store: Free above ₹1,499.")
    (tmp_path / "big.txt").write_text("\n".join(lines), encoding="utf-8")
    start = time.perf_counter()
    qas = pair(parse_path(tmp_path / "big.txt"), "Store")
    v = Vectorizer([q.asked for q in qas] + [q.answered or "" for q in qas])
    groups = merge_by_answer(group(qas, v, 0.3), v)
    assert time.perf_counter() - start < 10  # pairing and grouping used to be quadratic
    assert len(qas) == 3000 and len(groups) == 1
