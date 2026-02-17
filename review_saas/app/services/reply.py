from .sentiment import analyze

    def suggest(review_text: str) -> str:
        cat, score, _ = analyze(review_text or "")
        if cat == "negative":
            return ("We’re sorry for the experience. Please email support@example.com so we can make this right.")
        if cat == "positive":
            return ("Thank you for your kind words! We appreciate your feedback and hope to see you again.")
        return ("Thanks for sharing your thoughts. We value your feedback and will keep improving.")