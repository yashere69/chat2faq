"""Devanagari questions should find the Roman-script entries they mean."""


def test_devanagari_is_romanized_for_matching():
    from chat2faq.mine import Vectorizer, cosine
    from chat2faq.roman import romanize

    assert romanize("मेरा ऑर्डर कब आएगा?") == "meraa ordar kab aaegaa?"
    assert romanize("रिफंड १२") == "rifand 12"
    assert romanize("समझ") == "samajh"  # no vowel written after the final consonant
    v = Vectorizer(["mera order kab tak aayega?", "size chart bhej do please"])
    same = cosine(v.vec("मेरा ऑर्डर कब आएगा?"), v.vec("mera order kab tak aayega?"))
    other = cosine(v.vec("मेरा ऑर्डर कब आएगा?"), v.vec("size chart bhej do please"))
    assert same > 0.3 > other
