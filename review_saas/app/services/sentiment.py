from typing import Tuple, List
    import re

    def analyze(text: str) -> Tuple[str, float, List[str]]:
        # Simple heuristic sentiment: based on star rating usually; for demo, keyword-based
        positive = len(re.findall(r"(great|good|excellent|love|amazing)", text, re.I))
        negative = len(re.findall(r"(bad|poor|terrible|hate|awful)", text, re.I))
        score = max(0.0, min(1.0, 0.5 + (positive - negative) * 0.1))
        category = "positive" if score > 0.6 else ("negative" if score < 0.4 else "neutral")
        keywords = re.findall(r"\w{6,}", text)
        return category, score, keywords[:10]