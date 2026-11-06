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

from .mine import QA, Vectorizer, cosine, faq, group, merge_by_answer


def load_labels(path: Path) -> dict[int, str]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["line"]: r["intent"] for r in rows}


def _build(qas: list[QA], threshold: float):
    v = Vectorizer([q.asked for q in qas] + [q.answered for q in qas if q.answered])
    groups = merge_by_answer(group(qas, v, threshold), v)
    return v, groups


def score(qas: list[QA], labels: dict[int, str], threshold: float = 0.3) -> dict:
    labelled = [q for q in qas if q.question.line in labels]
    v, groups = _build(labelled, threshold)
    entries = [g for g in groups if len(g.members) >= 2]
    majority = []
    pure = 0
    for g in entries:
        counts = Counter(labels[m.question.line] for m in g.members)
        intent, n = counts.most_common(1)[0]
        majority.append(intent)
        pure += n
    total = sum(len(g.members) for g in entries) or 1
    all_intents = set(labels[q.question.line] for q in labelled)

    ordered = sorted(labelled, key=lambda q: q.question.at)
    cut = int(len(ordered) * 0.8)
    train, test = ordered[:cut], ordered[cut:]
    v2, groups2 = _build(train, threshold)
    built = [g for g in groups2 if len(g.members) >= 2]
    intents2 = [
        Counter(labels[m.question.line] for m in g.members).most_common(1)[0][0] for g in built
    ]
    covered = 0
    for q in test:
        qv = v2.vec(q.asked)
        sims = [cosine(qv, g.centroid) for g in built]
        if sims:
            i = max(range(len(sims)), key=sims.__getitem__)
            covered += sims[i] >= threshold and intents2[i] == labels[q.question.line]
    customer_lines = {line for line, intent in labels.items() if intent != "greeting"}
    found = {q.question.line for q in qas} & customer_lines
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
