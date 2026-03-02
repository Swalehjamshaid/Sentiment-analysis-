
# filename: app/services/keywords.py
from __future__ import annotations
from collections import Counter
import re

STOP = set("""
a the an and or but if then else when while for to of in on at from with about into by over after under again further
i me my we our you your he him his she her it its they them their is are was were be been being do does did doing
""".split())

_token = re.compile(r"[A-Za-z][A-Za-z']+")

def top_keywords(texts: list[str], n: int = 15) -> list[tuple[str,int]]:
    words = []
    for t in texts:
        for w in _token.findall((t or '').lower()):
            if w in STOP or len(w) < 3:
                continue
            words.append(w)
    return Counter(words).most_common(n)
