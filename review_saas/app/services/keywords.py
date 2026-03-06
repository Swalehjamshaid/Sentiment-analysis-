# filename: app/services/keywords.py
from __future__ import annotations
from collections import Counter
import re
from typing import List, Tuple

# Common stopwords to ignore
STOP = set("""
a the an and or but if then else when while for to of in on at from with about into by over after under again further
i me my we our you your he him his she her it its they them their is are was were be been being do does did doing
""".split())

# Token pattern: words with letters and optional apostrophes
_token = re.compile(r"[A-Za-z][A-Za-z']+")

def top_keywords(texts: List[str], n: int = 15) -> List[Tuple[str, int]]:
    """
    Extract the top `n` keywords from a list of text strings,
    ignoring common stopwords and short words (<3 chars).
    """
    words: list[str] = []

    for t in texts:
        if not t:
            continue
        for w in _token.findall(t.lower()):
            if w in STOP or len(w) < 3:
                continue
            words.append(w)

    return Counter(words).most_common(n)
