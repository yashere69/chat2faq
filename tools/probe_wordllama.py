"""Would static word embeddings answer the probe better than character n-grams?

Not part of the package. Needs `pip install wordllama` (its weights ship in the wheel, so
this runs offline). Builds the FAQ from the sample exactly as tools/evaluate.py does, then
answers each probe question with the entry whose questions are closest by n-gram
similarity, by WordLlama cosine, and by the mean of the two. The FAQ is grouped at the
default 0.3 throughout; only the answering threshold varies (tools/evaluate.py regroups at
each threshold, so its rows away from 0.3 differ slightly).

    python tools/probe_wordllama.py
"""

from collections import Counter
from pathlib import Path

import numpy as np
import wordllama
from wordllama import WordLlama

from chat2faq.evaluate import _build, _key, load_labels, load_probe
from chat2faq.mine import pair, templatize
from chat2faq.parse import parse_path
from chat2faq.redact import redact

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    labels = load_labels(ROOT / "examples/labels.jsonl")
    qas = pair(parse_path(ROOT / "examples/exports"), "Indigo Loom")
    labelled = [q for q in qas if _key(q, labels) in labels]
    v, groups = _build(labelled, 0.3)
    entries = [g for g in groups if len(g.members) >= 2]
    intents = [
        Counter(labels[_key(m, labels)] for m in g.members).most_common(1)[0][0] for g in entries
    ]
    probes = load_probe(ROOT / "examples/probe.jsonl")
    texts = [templatize(redact(p["text"])) for p in probes]

    wl = WordLlama.load(cache_dir=Path(wordllama.__file__).parent, disable_download=True)

    def emb(xs: list[str]) -> np.ndarray:
        e = np.asarray(wl.embed(xs), dtype=float)
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    cent = np.stack([emb([m.asked for m in g.members]).mean(0) for g in entries])
    cent /= np.linalg.norm(cent, axis=1, keepdims=True)
    dense = emb(texts) @ cent.T
    ngram = np.array([[g.similarity(v.vec(t)) for g in entries] for t in texts])

    def tally(sim: np.ndarray, t: float) -> tuple[int, int, int]:
        right = wrong = none = 0
        for k, p in enumerate(probes):
            i = int(sim[k].argmax())
            if sim[k, i] < t:
                none += 1
            elif intents[i] == p["intent"]:
                right += 1
            else:
                wrong += 1
        return right, wrong, none

    print("| Similarity | Threshold | Right | Wrong | No entry |\n|---|---|---|---|---|")
    for name, sim, ts in (
        ("n-gram", ngram, (0.2, 0.25, 0.3)),
        ("WordLlama", dense, (0.3, 0.4, 0.5)),
        ("mean of both", (ngram + dense) / 2, (0.3, 0.35, 0.4)),
    ):
        for t in ts:
            print(f"| {name} | {t} | " + " | ".join(map(str, tally(sim, t))) + " |")
    for name, sim in (("n-gram", ngram), ("WordLlama", dense)):
        best = sum(intents[int(sim[k].argmax())] == p["intent"] for k, p in enumerate(probes))
        print(f"\n{name}: closest entry is the right one for {best}/{len(probes)} probes")


if __name__ == "__main__":
    main()
