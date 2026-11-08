"""chat2faq command line."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .evaluate import best_entry, load_labels, load_probe, probe_score, score
from .mine import Entry, Vectorizer, faq, group, merge_by_answer, pair
from .parse import parse_path
from .redact import backend


def guess_business(msgs) -> str:
    """The sender present in the most files; ties go to whoever wrote the most messages."""
    files: dict[str, set[str]] = {}
    for m in msgs:
        files.setdefault(m.sender, set()).add(m.source)
    counts = Counter(m.sender for m in msgs)
    return max(counts, key=lambda s: (len(files[s]), counts[s]))


def to_markdown(entries: list[Entry], business: str) -> str:
    lines = [
        f"# FAQ mined from {business} chats",
        "",
        "Customer details are redacted. Each entry links back to the chat lines it came "
        "from. Review every answer before a bot uses it.",
        "",
    ]
    for i, e in enumerate(entries, start=1):
        lines.append(f"## {i}. {e.question}")
        lines.append("")
        if e.answer:
            lines.append(e.answer)
        else:
            lines.append("_No reply from the store found within the time window._")
        lines.append("")
        lines.append(f"Asked {e.asked} times, answered {e.answered}.")
        if e.needs_lookup:
            lines.append(
                "**Needs a lookup:** the answer depends on the customer's order, so a "
                "bot should call a tool here rather than reply with fixed text."
            )
        lines.append("")
        lines.append("Also asked as: " + "; ".join(f"“{v}”" for v in e.variants))
        lines.append("")
        lines.append(
            "Sources: " + ", ".join(e.sources[:8]) + (" ..." if len(e.sources) > 8 else "")
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chat2faq")
    ap.add_argument("--version", action="version", version=f"chat2faq {__version__}")
    ap.add_argument("export", type=Path, help="a WhatsApp .txt export, or a folder of them")
    ap.add_argument("--business", help="the store's name as it appears in the export")
    ap.add_argument("-o", "--out", type=Path, help="write the FAQ as markdown")
    ap.add_argument("--jsonl", type=Path, help="write the FAQ as JSON Lines")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument(
        "--date-order",
        choices=["auto", "dmy", "mdy"],
        default="auto",
        help="day/month order in timestamps (auto decides per file)",
    )
    ap.add_argument("--min-asked", type=int, default=2)
    ap.add_argument("--labels", type=Path, help="per-line intent labels; prints an evaluation")
    ap.add_argument(
        "--probe",
        type=Path,
        help="questions to try against the FAQ (text lines, or JSONL with text and intent)",
    )
    args = ap.parse_args(argv)

    try:
        msgs = parse_path(args.export, args.date_order)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if not msgs:
        print("error: no messages found; is this a WhatsApp export?", file=sys.stderr)
        return 2
    if args.business and args.business not in {m.sender for m in msgs}:
        print(f"error: nobody called {args.business!r} wrote in this export", file=sys.stderr)
        return 2
    business = args.business or guess_business(msgs)
    if not args.business:
        print(
            f"note: guessed the store is {business!r}; pass --business if that's wrong",
            file=sys.stderr,
        )
    qas = pair(msgs, business)
    v = Vectorizer([q.asked for q in qas] + [q.answered for q in qas if q.answered])
    entries = faq(merge_by_answer(group(qas, v, args.threshold), v), v, args.min_asked)

    print(f"{len(msgs)} messages, store = {business!r}, redaction: {backend()}")
    print(f"{len(qas)} customer questions -> {len(entries)} FAQ entries\n")
    for e in entries:
        flag = "  [lookup]" if e.needs_lookup else ""
        print(f"{e.asked:>4}x  {e.question}{flag}")
    if args.out:
        args.out.write_text(to_markdown(entries, business), encoding="utf-8")
    if args.jsonl:
        args.jsonl.write_text(
            "".join(
                json.dumps(e.__dict__ | {"needs_lookup": e.needs_lookup}, ensure_ascii=False) + "\n"
                for e in entries
            ),
            encoding="utf-8",
        )
    if args.probe:
        try:
            probes = load_probe(args.probe)
        except (OSError, ValueError) as err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        kept = [
            g
            for g in merge_by_answer(group(qas, v, args.threshold), v)
            if len(g.members) >= args.min_asked
        ]
        print(f"\nprobe: {len(probes)} questions")
        for p in probes:
            i, sim = best_entry(kept, v, p["text"])
            hit = entries[i].question if i is not None and sim >= args.threshold else "(no entry)"
            print(f"  {sim:4.2f}  {p['text']}  ->  {hit}")
        if args.labels and all("intent" in p for p in probes):
            r = probe_score(qas, load_labels(args.labels), probes, args.threshold)
            print(
                f"probe answered by the right entry  {r['right']}/{r['probes']}"
                f"  (wrong entry {len(r['wrong'])}, no entry {len(r['unanswered'])})"
            )
    if args.labels:
        r = score(qas, load_labels(args.labels), args.threshold)
        print(f"\nquestion detection recall   {r['question_recall']}%")
        print(f"entry purity                {r['purity']}%  ({r['entries']} entries)")
        print(f"intents with an entry       {r['intents_with_entry']}/{r['intents']}")
        print(f"held-out questions covered  {r['heldout_covered']}/{r['heldout']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
