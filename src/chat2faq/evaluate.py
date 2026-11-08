"""Score a mined FAQ against per-line intent labels (for example from nakli --labels).

- question recall: share of labelled, non-greeting customer messages detected as questions
- purity: share of questions in each FAQ entry that carry the entry's majority intent,
  weighted by entry size. Low purity means unrelated questions were merged.
- intent coverage: share of labelled intents that ended up with their own entry
- held-out coverage: build the FAQ from the first 80% of questions by time, then for each
  later question find the most similar FAQ question; it counts as covered if similarity
  clears the threshold and the entry's majority intent matches the question's label
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .mine import QA, Group, Vectorizer, faq, group, merge_by_answer, templatize
from .redact import redact

Key = tuple[str | None, int]


def load_labels(path: Path) -> dict[Key, str]:
    """Rows are {"line", "intent"} for a single export, or {"file", "line", "intent"} for a
    folder of exports (what `nakli chats --split` writes)."""
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {(r.get("file"), r["line"]): r["intent"] for r in rows}


def _key(qa: QA, labels: dict[Key, str]) -> Key:
    k: Key = (qa.question.source, qa.question.line)
    return k if k in labels else (None, qa.question.line)


def _build(qas: list[QA], threshold: float):
    v = Vectorizer([q.asked for q in qas] + [q.answered for q in qas if q.answered])
    groups = merge_by_answer(group(qas, v, threshold), v)
    return v, groups


def score(qas: list[QA], labels: dict[Key, str], threshold: float = 0.3) -> dict:
    labelled = [q for q in qas if _key(q, labels) in labels]
    v, groups = _build(labelled, threshold)
    entries = [g for g in groups if len(g.members) >= 2]
    majority = []
    pure = 0
    for g in entries:
        counts = Counter(labels[_key(m, labels)] for m in g.members)
        intent, n = counts.most_common(1)[0]
        majority.append(intent)
        pure += n
    total = sum(len(g.members) for g in entries) or 1
    all_intents = set(labels[_key(q, labels)] for q in labelled)

    ordered = sorted(labelled, key=lambda q: q.question.at)
    cut = int(len(ordered) * 0.8)
    train, test = ordered[:cut], ordered[cut:]
    v2, groups2 = _build(train, threshold)
    built = [g for g in groups2 if len(g.members) >= 2]
    intents2 = [
        Counter(labels[_key(m, labels)] for m in g.members).most_common(1)[0][0] for g in built
    ]
    covered = 0
    for q in test:
        qv = v2.vec(q.asked)
        sims = [g.similarity(qv) for g in built]
        if sims:
            i = max(range(len(sims)), key=sims.__getitem__)
            covered += sims[i] >= threshold and intents2[i] == labels[_key(q, labels)]
    customer_lines = {key for key, intent in labels.items() if intent != "greeting"}
    found = {_key(q, labels) for q in qas} & customer_lines
    return {
        "question_recall": round(100 * len(found) / (len(customer_lines) or 1), 1),
        "questions": len(labelled),
        "entries": len(entries),
        "purity": round(100 * pure / total, 1),
        "intents": len(all_intents),
        "intents_with_entry": len(set(majority)),
        "heldout": len(test),
        "heldout_covered": covered,
        "faq": faq(groups, v),
    }


def load_probe(path: Path) -> list[dict]:
    """Questions to try against the FAQ: JSON lines with "text" (and optionally "intent"),
    or plain lines of text."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        if line.lstrip().startswith("{"):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: not JSON ({e.msg})") from e
            if not isinstance(row.get("text"), str):
                raise ValueError(f"{path}:{n}: needs a 'text' string")
            out.append(row)
        else:
            out.append({"text": line.strip()})
    return out


def best_entry(groups: list[Group], v: Vectorizer, text: str) -> tuple[int | None, float]:
    """The entry a bot built from this FAQ would answer `text` with, and how sure it is."""
    qv = v.vec(templatize(redact(text)))
    sims = [g.similarity(qv) for g in groups]
    if not sims:
        return None, 0.0
    i = max(range(len(sims)), key=sims.__getitem__)
    return i, sims[i]


def probe_score(
    qas: list[QA], labels: dict[Key, str], probes: list[dict], threshold: float = 0.3
) -> dict:
    """Ask the FAQ questions it was not built from. Each probe is answered by the entry it
    is most similar to, if similarity clears the threshold; the answer is right when that
    entry's main intent is the probe's intent."""
    labelled = [q for q in qas if _key(q, labels) in labels]
    v, groups = _build(labelled, threshold)
    entries = [g for g in groups if len(g.members) >= 2]
    intents = [
        Counter(labels[_key(m, labels)] for m in g.members).most_common(1)[0][0] for g in entries
    ]
    right, wrong, unanswered = 0, [], []
    for p in probes:
        i, sim = best_entry(entries, v, p["text"])
        if i is None or sim < threshold:
            unanswered.append(p["text"])
        elif intents[i] == p.get("intent"):
            right += 1
        else:
            wrong.append((p["text"], intents[i]))
    return {"probes": len(probes), "right": right, "wrong": wrong, "unanswered": unanswered}
