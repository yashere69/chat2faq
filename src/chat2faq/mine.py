"""Find customer questions, pair each with the store's answer, group similar questions.

Questions are compared with TF-IDF over character 3-5-grams of the redacted text, not over
words. Hinglish has no fixed spelling ("kab aayega", "kab ayega", "kb aaega"), and
character n-grams survive that variation where word overlap doesn't.

Grouping is single-pass: each question joins the most similar existing group if the
cosine similarity to that group's centroid clears `threshold`, otherwise it starts a new
group. It's order-dependent but deterministic, and fast enough for tens of thousands of
messages without numpy.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from .parse import Message
from .redact import redact

INTERROGATIVES = re.compile(
    r"\b(kya|kab|kaise|kitna|kitne|kitni|kaunsa|kaun|kahan|kyu|kyun|"
    r"what|when|where|why|how|which|can|could|is|are|do|does|will)\b",
    re.I,
)
REQUESTY = re.compile(r"\b(please|plz|pls|bhej do|bata do|batao|chahiye|milega|hai kya)\b", re.I)
GREETING = re.compile(r"^\s*(hi+|hello|hey|namaste|thanks?|thank you|ok+|okay)\W*$", re.I)


def is_question(text: str) -> bool:
    if GREETING.match(text):
        return False
    return "?" in text or bool(INTERROGATIVES.search(text)) or bool(REQUESTY.search(text))


@dataclass
class QA:
    question: Message
    asked: str  # redacted
    answer: Message | None
    answered: str | None  # redacted


def pair(msgs: list[Message], business: str, window_hours: int = 6) -> list[QA]:
    """Pair each customer question with the store's next message to that customer.

    Exports from the business phone may hold one customer per file or many; pairing is done
    per (source file, customer) thread, so both work.
    """
    threads: dict[tuple[str, str], list[Message]] = {}
    for m in sorted(msgs, key=lambda m: (m.source, m.at, m.line)):
        if m.sender != business:
            threads.setdefault((m.source, m.sender), []).append(m)
    biz = [m for m in msgs if m.sender == business]
    out = []
    for (source, _), cust_msgs in threads.items():
        for i, q in enumerate(cust_msgs):
            if not is_question(q.text):
                continue
            nxt_q = cust_msgs[i + 1].at if i + 1 < len(cust_msgs) else None
            limit = q.at + timedelta(hours=window_hours)
            answer = next(
                (
                    b
                    for b in biz
                    if b.source == source
                    and q.at <= b.at <= limit
                    and (nxt_q is None or b.at <= nxt_q)
                    and _addresses(b, q)
                ),
                None,
            )
            out.append(
                QA(
                    q,
                    templatize(redact(q.text)),
                    answer,
                    templatize(redact(answer.text)) if answer else None,
                )
            )
    return out


def templatize(text: str) -> str:
    """Order numbers and links are per-customer; an FAQ answer can't hard-code them."""
    text = re.sub(r"https?://\S+", "[LINK]", text)
    return re.sub(r"#\d{3,}", "#[ORDER]", text)


def _addresses(reply: Message, question: Message) -> bool:
    """In a single-customer export every store message is to that customer. In a merged
    export, a reply naming a different customer isn't an answer to this one."""
    first = question.sender.split()[0]
    named = re.findall(r"\b(?:Hi|Namaste|Noted|Theek hai|Hello)\s+([A-Z][a-z]+)", reply.text)
    return not named or first in named


def _grams(text: str) -> Counter[str]:
    t = re.sub(r"\[[A-Z]+\]", " ", text.lower())
    t = re.sub(r"[^\wऀ-ॿ ]+", " ", t)
    t = " " + re.sub(r"\s+", " ", t).strip() + " "
    return Counter(t[i : i + n] for n in (3, 4, 5) for i in range(len(t) - n + 1))


class Vectorizer:
    def __init__(self, docs: list[str]):
        grams = [_grams(d) for d in docs]
        df: Counter[str] = Counter()
        for g in grams:
            df.update(g.keys())
        n = len(docs)
        self.idf = {k: math.log((1 + n) / (1 + v)) + 1 for k, v in df.items()}

    def vec(self, text: str) -> dict[str, float]:
        g = _grams(text)
        v = {k: c * self.idf.get(k, 1.0) for k, c in g.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {k: x / norm for k, x in v.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


@dataclass
class Group:
    members: list[QA] = field(default_factory=list)
    vecs: list[dict[str, float]] = field(default_factory=list)
    centroid: dict[str, float] = field(default_factory=dict)

    def add(self, qa: QA, v: dict[str, float]) -> None:
        self.members.append(qa)
        self.vecs.append(v)
        acc: Counter[str] = Counter()
        for vec in self.vecs:
            acc.update(vec)
        norm = math.sqrt(sum(x * x for x in acc.values())) or 1.0
        self.centroid = {k: x / norm for k, x in acc.items()}


def group(qas: list[QA], vectorizer: Vectorizer, threshold: float = 0.3) -> list[Group]:
    groups: list[Group] = []
    for qa in qas:
        v = vectorizer.vec(qa.asked)
        best, best_sim = None, threshold
        for g in groups:
            s = cosine(v, g.centroid)
            if s >= best_sim:
                best, best_sim = g, s
        if best is None:
            best = Group()
            groups.append(best)
        best.add(qa, v)
    return sorted(groups, key=lambda g: -len(g.members))


@dataclass
class Entry:
    question: str
    answer: str | None
    asked: int
    answered: int
    sources: list[str]
    variants: list[str]

    @property
    def needs_lookup(self) -> bool:
        """The answer depends on the customer's order, so a bot needs a tool for it."""
        return bool(self.answer and ("[ORDER]" in self.answer or "[LINK]" in self.answer))


def _canonical(answers: list[str]) -> str:
    """Most common answer, with a customer's first name swapped for a neutral greeting."""
    cleaned = [
        re.sub(r"\b(Hi|Namaste|Noted|Theek hai)\s+[A-Z][a-z]+([!,])?", r"\1\2", a) for a in answers
    ]
    return Counter(cleaned).most_common(1)[0][0]


def merge_by_answer(
    groups: list[Group], vectorizer: Vectorizer, threshold: float = 0.6
) -> list[Group]:
    """Two groups the store answers the same way are the same FAQ.

    "shipping charges?" and "delivery charge kitna hai" share almost no characters, but the
    store sends the same reply to both. Questions vary far more than the store's answers do,
    so the answers are the better signal for merging.
    """

    def answer_vec(g: Group) -> dict[str, float] | None:
        answers = [m.answered for m in g.members if m.answered]
        return vectorizer.vec(_canonical(answers)) if answers else None

    merged: list[Group] = []
    vecs: list[dict[str, float] | None] = []
    for g in groups:
        av = answer_vec(g)
        target = None
        if av is not None:
            for i, other in enumerate(vecs):
                if other is not None and cosine(av, other) >= threshold:
                    target = i
                    break
        if target is None:
            merged.append(g)
            vecs.append(av)
        else:
            for qa, v in zip(g.members, g.vecs, strict=True):
                merged[target].add(qa, v)
    return sorted(merged, key=lambda g: -len(g.members))


def faq(groups: list[Group], vectorizer: Vectorizer, min_asked: int = 2) -> list[Entry]:
    out = []
    for g in groups:
        if len(g.members) < min_asked:
            continue
        sims = [cosine(v, g.centroid) for v in g.vecs]
        rep = g.members[max(range(len(sims)), key=sims.__getitem__)].asked
        answers = [m.answered for m in g.members if m.answered]
        out.append(
            Entry(
                question=rep,
                answer=_canonical(answers) if answers else None,
                asked=len(g.members),
                answered=len(answers),
                sources=[f"{m.question.source}:{m.question.line}" for m in g.members],
                variants=sorted({m.asked for m in g.members})[:5],
            )
        )
    return out
