# analytics_service.py

```python
from collections import Counter
from datetime import datetime, timedelta
from statistics import mean
from typing import List, Dict, Any


class AnalyticsService:
    """
    Advanced Business Analytics Engine
    ----------------------------------
    Provides:
    - KPI calculations
    - Rating analytics
    - Sentiment analytics
    - Trend analytics
    - Review intelligence
    - Decision-making metrics
    """

    def __init__(self):
        pass

    # =========================================================
    # MAIN ANALYTICS ENGINE
    # =========================================================

    def generate_complete_analytics(
        self,
        company_name: str,
        reviews: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        if not reviews:
            return {
                "company_name": company_name,
                "generated_at": str(datetime.utcnow()),
                "total_reviews": 0,
                "message": "No reviews available"
            }

        ratings = [self._safe_rating(r) for r in reviews]
        sentiments = [self._safe_sentiment(r) for r in reviews]

        analytics = {
            "company_name": company_name,
            "generated_at": str(datetime.utcnow()),
            "total_reviews": len(reviews),
            "average_rating": round(mean(ratings), 2),
            "rating_distribution": self.rating_distribution(ratings),
            "sentiment_distribution": self.sentiment_distribution(sentiments),
            "customer_satisfaction_score": self.customer_satisfaction_score(ratings),
            "review_growth_trend": self.review_growth_trend(reviews),
            "negative_review_percentage": self.negative_review_percentage(sentiments),
            "positive_review_percentage": self.positive_review_percentage(sentiments),
            "business_health_score": self.business_health_score(ratings, sentiments),
            "top_customer_issues": self.top_customer_issues(reviews),
            "top_positive_points": self.top_positive_points(reviews),
            "business_risk_level": self.business_risk_level(ratings, sentiments),
            "decision_metrics": self.decision_metrics(ratings, sentiments),
            "monthly_review_breakdown": self.monthly_review_breakdown(reviews),
            "response_priority": self.response_priority(sentiments),
            "executive_summary": self.executive_summary(
                company_name,
                ratings,
                sentiments
            )
        }

        return analytics

    # =========================================================
    # BASIC HELPERS
    # =========================================================

    def _safe_rating(self, review):
        try:
            return float(review.get("rating", 0))
        except:
            return 0

    def _safe_sentiment(self, review):
        sentiment = str(review.get("sentiment", "neutral")).lower()

        if sentiment not in ["positive", "negative", "neutral"]:
            return "neutral"

        return sentiment

    # =========================================================
    # RATING ANALYTICS
    # =========================================================

    def rating_distribution(self, ratings: List[float]):
        distribution = {
            "1_star": 0,
            "2_star": 0,
            "3_star": 0,
            "4_star": 0,
            "5_star": 0,
        }

        for rating in ratings:
            if rating <= 1:
                distribution["1_star"] += 1
            elif rating <= 2:
                distribution["2_star"] += 1
            elif rating <= 3:
                distribution["3_star"] += 1
            elif rating <= 4:
                distribution["4_star"] += 1
            else:
                distribution["5_star"] += 1

        return distribution

    # =========================================================
    # SENTIMENT ANALYTICS
    # =========================================================

    def sentiment_distribution(self, sentiments: List[str]):
        counter = Counter(sentiments)

        total = len(sentiments)

        return {
            "positive": counter.get("positive", 0),
            "negative": counter.get("negative", 0),
            "neutral": counter.get("neutral", 0),
            "positive_percentage": round(
                (counter.get("positive", 0) / total) * 100,
                2
            ),
            "negative_percentage": round(
                (counter.get("negative", 0) / total) * 100,
                2
            ),
            "neutral_percentage": round(
                (counter.get("neutral", 0) / total) * 100,
                2
            )
        }

    # =========================================================
    # CUSTOMER SATISFACTION SCORE
    # =========================================================

    def customer_satisfaction_score(self, ratings):
        if not ratings:
            return 0

        avg = mean(ratings)

        return round((avg / 5) * 100, 2)

    # =========================================================
    # BUSINESS HEALTH SCORE
    # =========================================================

    def business_health_score(self, ratings, sentiments):
        avg_rating = mean(ratings)

        positive = sentiments.count("positive")
        negative = sentiments.count("negative")

        sentiment_score = (
            (positive - negative + len(sentiments))
            / (2 * len(sentiments))
        ) * 100

        rating_score = (avg_rating / 5) * 100

        final_score = (rating_score * 0.6) + (sentiment_score * 0.4)

        return round(final_score, 2)

    # =========================================================
    # BUSINESS RISK LEVEL
    # =========================================================

    def business_risk_level(self, ratings, sentiments):
        avg_rating = mean(ratings)
        negative = sentiments.count("negative")

        negative_ratio = negative / len(sentiments)

        if avg_rating >= 4.5 and negative_ratio < 0.10:
            return "Low"

        if avg_rating >= 3.5 and negative_ratio < 0.30:
            return "Moderate"

        return "High"

    # =========================================================
    # REVIEW GROWTH TREND
    # =========================================================

    def review_growth_trend(self, reviews):
        monthly_data = {}

        for review in reviews:
            date_str = review.get("date")

            if not date_str:
                continue

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                month_key = dt.strftime("%Y-%m")

                monthly_data[month_key] = monthly_data.get(month_key, 0) + 1

            except:
                continue

        return monthly_data

    # =========================================================
    # MONTHLY BREAKDOWN
    # =========================================================

    def monthly_review_breakdown(self, reviews):
        breakdown = {}

        for review in reviews:
            date_str = review.get("date")

            if not date_str:
                continue

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                key = dt.strftime("%B %Y")

                if key not in breakdown:
                    breakdown[key] = {
                        "reviews": 0,
                        "positive": 0,
                        "negative": 0,
                        "neutral": 0
                    }

                breakdown[key]["reviews"] += 1

                sentiment = self._safe_sentiment(review)
                breakdown[key][sentiment] += 1

            except:
                continue

        return breakdown

    # =========================================================
    # REVIEW PERCENTAGES
    # =========================================================

    def negative_review_percentage(self, sentiments):
        if not sentiments:
            return 0

        negative = sentiments.count("negative")

        return round((negative / len(sentiments)) * 100, 2)

    def positive_review_percentage(self, sentiments):
        if not sentiments:
            return 0

        positive = sentiments.count("positive")

        return round((positive / len(sentiments)) * 100, 2)

    # =========================================================
    # TOP CUSTOMER ISSUES
    # =========================================================

    def top_customer_issues(self, reviews):
        issue_keywords = [
            "slow",
            "late",
            "bad",
            "worst",
            "dirty",
            "expensive",
            "delay",
            "poor",
            "rude",
            "refund",
            "problem",
            "issue",
            "broken",
            "damage",
            "waiting",
            "unprofessional",
            "disappointed"
        ]

        issues = []

        for review in reviews:
            text = str(review.get("review_text", "")).lower()

            for keyword in issue_keywords:
                if keyword in text:
                    issues.append(keyword)

        counter = Counter(issues)

        return counter.most_common(10)

    # =========================================================
    # TOP POSITIVE POINTS
    # =========================================================

    def top_positive_points(self, reviews):
        positive_keywords = [
            "excellent",
            "amazing",
            "great",
            "friendly",
            "fast",
            "perfect",
            "best",
            "professional",
            "clean",
            "good",
            "awesome",
            "recommended",
            "satisfied",
            "quality",
            "fresh"
        ]

        positives = []

        for review in reviews:
            text = str(review.get("review_text", "")).lower()

            for keyword in positive_keywords:
                if keyword in text:
                    positives.append(keyword)

        counter = Counter(positives)

        return counter.most_common(10)

    # =========================================================
    # RESPONSE PRIORITY
    # =========================================================

    def response_priority(self, sentiments):
        negative_percentage = self.negative_review_percentage(sentiments)

        if negative_percentage >= 40:
            return "Critical"

        if negative_percentage >= 20:
            return "High"

        if negative_percentage >= 10:
            return "Medium"

        return "Low"

    # =========================================================
    # DECISION METRICS
    # =========================================================

    def decision_metrics(self, ratings, sentiments):
        avg_rating = mean(ratings)

        positive = sentiments.count("positive")
        negative = sentiments.count("negative")

        metrics = {
            "customer_loyalty": round((positive / len(sentiments)) * 100, 2),
            "reputation_score": round((avg_rating / 5) * 100, 2),
            "risk_score": round((negative / len(sentiments)) * 100, 2),
            "growth_potential": self.calculate_growth_potential(avg_rating),
            "brand_strength": self.calculate_brand_strength(avg_rating, positive),
        }

        return metrics

    # =========================================================
    # GROWTH POTENTIAL
    # =========================================================

    def calculate_growth_potential(self, avg_rating):
        if avg_rating >= 4.5:
            return "Very High"

        if avg_rating >= 4.0:
            return "High"

        if avg_rating >= 3.0:
            return "Moderate"

        return "Low"

    # =========================================================
    # BRAND STRENGTH
    # =========================================================

    def calculate_brand_strength(self, avg_rating, positive_reviews):
        if avg_rating >= 4.5 and positive_reviews >= 50:
            return "Excellent"

        if avg_rating >= 4.0:
            return "Strong"

        if avg_rating >= 3.0:
            return "Average"

        return "Weak"

    # =========================================================
    # EXECUTIVE SUMMARY
    # =========================================================

    def executive_summary(self, company_name, ratings, sentiments):
        avg_rating = round(mean(ratings), 2)

        positive = sentiments.count("positive")
        negative = sentiments.count("negative")

        if avg_rating >= 4.5:
            performance = "excellent"
        elif avg_rating >= 4.0:
            performance = "strong"
        elif avg_rating >= 3.0:
            performance = "average"
        else:
            performance = "weak"

        summary = f"""
        {company_name} currently demonstrates {performance} business performance
        based on customer sentiment analysis and review analytics.

        The business maintains an average rating of {avg_rating}/5.

        Positive customer sentiment count: {positive}
        Negative customer sentiment count: {negative}

        The analytics engine suggests focusing on customer experience,
        service quality, and operational efficiency to improve long-term
        brand reputation and customer loyalty.
        """

        return summary.strip()


# =========================================================
# GLOBAL INSTANCE
# =========================================================

analytics_service = AnalyticsService()

```
