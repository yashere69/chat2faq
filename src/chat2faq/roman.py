"""Write Devanagari in the Roman letters Hinglish chats use, so that "मेरा ऑर्डर कब आएगा"
and "mera order kab aayega" share character n-grams.

This is a lossy, rule-of-thumb transliteration for matching, not for display: the inherent
vowel is dropped at the end of a word ("कब" -> "kab", not "kaba"), and फ is written "f"
because in chat it mostly spells English words ("रिफंड" -> "rifand").
"""

from __future__ import annotations

_CONSONANTS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "n",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "n",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "f",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "ळ": "l",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"}
_VOWELS = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "ऑ": "o",
    "ऍ": "e",
}
_SIGNS = {
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ॉ": "o",
    "ॅ": "e",
}
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
VIRAMA, NUKTA = "्", "़"
_MARKS = {"ं": "n", "ँ": "n", "ः": "h"}


def romanize(text: str) -> str:
    out: list[str] = []
    chars = text.translate(_DIGITS)
    i = 0
    while i < len(chars):
        c = chars[i]
        if c in _CONSONANTS:
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == NUKTA:
                out.append(_NUKTA.get(c, _CONSONANTS[c]))
                i += 1
                nxt = chars[i + 1] if i + 1 < len(chars) else ""
            else:
                out.append(_CONSONANTS[c])
            if nxt in _SIGNS:
                out.append(_SIGNS[nxt])
                i += 1
            elif nxt == VIRAMA:
                i += 1
            elif "ऀ" <= nxt <= "ॿ" and nxt not in _MARKS:
                out.append("a")  # inherent vowel inside a word
            elif nxt in _MARKS:
                out.append("a")
            # word end: the inherent vowel is not pronounced in Hindi, so it's not written
        elif c in _VOWELS:
            out.append(_VOWELS[c])
        elif c in _MARKS:
            out.append(_MARKS[c])
        elif c in _SIGNS or c in (VIRAMA, NUKTA):
            pass  # a stray sign with no consonant before it
        else:
            out.append(c)
        i += 1
    return "".join(out)
