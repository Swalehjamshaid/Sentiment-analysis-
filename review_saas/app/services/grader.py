def grade_health(kpis: dict) -> str:
        # Very simple grader; extend with real rules.
        pos = kpis.get("positive_pct", 0)
        if pos >= 70:
            return "A"
        if pos >= 50:
            return "B"
        if pos >= 30:
            return "C"
        return "D"