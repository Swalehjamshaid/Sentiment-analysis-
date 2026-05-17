# ==========================================================
# FILE: app/services/response_formatter.py
# WORLD-CLASS HUMAN RESPONSE FORMATTER
# ENTERPRISE AI CONVERSATIONAL INTELLIGENCE ENGINE
# ==========================================================

import re
import random
from typing import Dict, Any, List


# ==========================================================
# RESPONSE FORMATTER
# ==========================================================

class ResponseFormatter:

    """
    ======================================================
    HUMAN-LIKE AI RESPONSE ENGINE
    ======================================================

    FEATURES:
    - Human-like responses
    - Executive formatting
    - Smart shortening
    - Conversational responses
    - Bullet formatting
    - Executive summaries
    - Natural response cleanup
    - AI tone control
    - Dynamic response styling
    """

    def __init__(self):

        # ==================================================
        # HUMAN RESPONSE STARTERS
        # ==================================================

        self.casual_starters = [

            "Based on the reviews,",
            "Customers mainly feel that",
            "From the customer feedback,",
            "Most customers are saying that",
            "Looking at the reviews,",
            "The main concern seems to be",
            "Customers mostly complain about"

        ]

        self.executive_starters = [

            "Executive analysis indicates that",
            "Strategic review analysis shows that",
            "Operational intelligence suggests that",
            "Business performance indicators reveal that",
            "Customer sentiment analysis indicates that"

        ]

        self.short_starters = [

            "Mainly,",
            "Mostly,",
            "The biggest issue is",
            "Customers mostly complain about",
            "The primary concern is"

        ]

    # ======================================================
    # MAIN FORMATTER
    # ======================================================

    def format_response(

        self,
        response: str,
        routing_data: Dict[str, Any]

    ) -> str:

        try:

            if not response:
                return "No response generated."

            response_mode = routing_data.get(
                "response_mode",
                "NORMAL_MODE"
            )

            # ==============================================
            # CLEAN RESPONSE
            # ==============================================

            response = self.clean_response(
                response
            )

            # ==============================================
            # ROUTE FORMATTING
            # ==============================================

            if response_mode == "SHORT_MODE":

                response = self.format_short_response(
                    response
                )

            elif response_mode == "BULLET_MODE":

                response = self.format_bullet_response(
                    response
                )

            elif response_mode == "EXECUTIVE_MODE":

                response = self.format_executive_response(
                    response
                )

            elif response_mode == "SUMMARY_MODE":

                response = self.format_summary_response(
                    response
                )

            elif response_mode == "CASUAL_MODE":

                response = self.format_casual_response(
                    response
                )

            elif response_mode == "ISSUE_MODE":

                response = self.format_issue_response(
                    response
                )

            elif response_mode == "KPI_MODE":

                response = self.format_kpi_response(
                    response
                )

            elif response_mode == "RECOMMENDATION_MODE":

                response = self.format_recommendation_response(
                    response
                )

            else:

                response = self.format_normal_response(
                    response
                )

            # ==============================================
            # HUMANIZE RESPONSE
            # ==============================================

            response = self.humanize_response(
                response,
                routing_data
            )

            return response.strip()

        except Exception as e:

            print(
                f"❌ Response Formatting Error: {e}"
            )

            return response

    # ======================================================
    # CLEAN RESPONSE
    # ======================================================

    def clean_response(
        self,
        response: str
    ):

        response = re.sub(
            r"\n{3,}",
            "\n\n",
            response
        )

        response = re.sub(
            r"\s{2,}",
            " ",
            response
        )

        response = response.replace(
            "Operational dissatisfaction indicators",
            "Customers appear unhappy"
        )

        response = response.replace(
            "Strategic analysis indicates",
            "The reviews suggest"
        )

        response = response.replace(
            "Customer sentiment reflects",
            "Customers feel that"
        )

        response = response.replace(
            "Operational inefficiencies",
            "service problems"
        )

        return response.strip()

    # ======================================================
    # SHORT RESPONSE
    # ======================================================

    def format_short_response(
        self,
        response: str
    ):

        sentences = re.split(
            r"(?<=[.!?]) +",
            response
        )

        short_response = sentences[0]

        if len(sentences) > 1:

            second = sentences[1]

            if len(short_response) < 140:

                short_response += " " + second

        if len(short_response) > 220:

            short_response = (
                short_response[:220] + "..."
            )

        return short_response

    # ======================================================
    # BULLET RESPONSE
    # ======================================================

    def format_bullet_response(
        self,
        response: str
    ):

        sentences = re.split(
            r"(?<=[.!?]) +",
            response
        )

        bullets = []

        for sentence in sentences[:6]:

            sentence = sentence.strip()

            if len(sentence) > 10:

                sentence = sentence.replace(
                    "\n",
                    " "
                )

                bullets.append(
                    f"• {sentence}"
                )

        return "\n".join(bullets)

    # ======================================================
    # EXECUTIVE RESPONSE
    # ======================================================

    def format_executive_response(
        self,
        response: str
    ):

        intro = random.choice(
            self.executive_starters
        )

        formatted = f"""

{intro}

{response}

Key Executive Insight:
Operational consistency and customer experience quality remain the strongest drivers of customer sentiment and brand perception.

"""

        return formatted.strip()

    # ======================================================
    # SUMMARY RESPONSE
    # ======================================================

    def format_summary_response(
        self,
        response: str
    ):

        sentences = re.split(
            r"(?<=[.!?]) +",
            response
        )

        summary = " ".join(
            sentences[:3]
        )

        return f"Summary: {summary}"

    # ======================================================
    # CASUAL RESPONSE
    # ======================================================

    def format_casual_response(
        self,
        response: str
    ):

        response = self.make_more_natural(
            response
        )

        if len(response) > 300:

            response = response[:300] + "..."

        return response

    # ======================================================
    # ISSUE RESPONSE
    # ======================================================

    def format_issue_response(
        self,
        response: str
    ):

        sentences = re.split(
            r"(?<=[.!?]) +",
            response
        )

        important_sentences = []

        keywords = [

            "issue",
            "problem",
            "complaint",
            "negative",
            "poor",
            "bad",
            "staff",
            "cleanliness",
            "service"

        ]

        for sentence in sentences:

            lower = sentence.lower()

            if any(

                keyword in lower

                for keyword in keywords

            ):

                important_sentences.append(
                    sentence
                )

        if important_sentences:

            response = " ".join(
                important_sentences[:3]
            )

        return response

    # ======================================================
    # KPI RESPONSE
    # ======================================================

    def format_kpi_response(
        self,
        response: str
    ):

        formatted = f"""

Business KPI Analysis

{response}

Key Metrics Focus:
• Customer Sentiment
• Reputation Performance
• Operational Stability
• Customer Satisfaction

"""

        return formatted.strip()

    # ======================================================
    # RECOMMENDATION RESPONSE
    # ======================================================

    def format_recommendation_response(
        self,
        response: str
    ):

        recommendations = re.split(
            r"(?<=[.!?]) +",
            response
        )

        formatted = [

            "Recommended Improvements:"
        ]

        count = 0

        for recommendation in recommendations:

            recommendation = recommendation.strip()

            if len(recommendation) > 15:

                formatted.append(
                    f"• {recommendation}"
                )

                count += 1

            if count >= 5:
                break

        return "\n".join(
            formatted
        )

    # ======================================================
    # NORMAL RESPONSE
    # ======================================================

    def format_normal_response(
        self,
        response: str
    ):

        response = self.make_more_natural(
            response
        )

        if len(response) > 1200:

            response = response[:1200] + "..."

        return response

    # ======================================================
    # HUMANIZATION ENGINE
    # ======================================================

    def humanize_response(

        self,
        response,
        routing_data

    ):

        humanization_level = routing_data.get(
            "humanization_level",
            "HIGH"
        )

        # ==============================================
        # VERY HIGH HUMANIZATION
        # ==============================================

        if humanization_level == "VERY_HIGH":

            response = self.make_more_natural(
                response
            )

        # ==============================================
        # HIGH HUMANIZATION
        # ==============================================

        elif humanization_level == "HIGH":

            response = self.reduce_robotic_language(
                response
            )

        return response

    # ======================================================
    # NATURAL LANGUAGE ENGINE
    # ======================================================

    def make_more_natural(
        self,
        response
    ):

        replacements = {

            "Operational":
                "Business",

            "customer sentiment":
                "customer feedback",

            "negative sentiment":
                "negative reviews",

            "positive sentiment":
                "positive reviews",

            "operational performance":
                "service quality",

            "business intelligence":
                "review analysis",

            "strategic recommendations":
                "recommended improvements",

            "elevated dissatisfaction":
                "customer frustration",

            "operational instability":
                "service inconsistency"

        }

        for old, new in replacements.items():

            response = response.replace(
                old,
                new
            )

        return response

    # ======================================================
    # REDUCE ROBOTIC LANGUAGE
    # ======================================================

    def reduce_robotic_language(
        self,
        response
    ):

        robotic_phrases = [

            "Executive analysis indicates that",
            "Strategic intelligence suggests that",
            "Operational intelligence reveals that",
            "Business intelligence indicates that"

        ]

        for phrase in robotic_phrases:

            response = response.replace(
                phrase,
                random.choice(
                    self.casual_starters
                )
            )

        return response

    # ======================================================
    # SMART RESPONSE TRIMMER
    # ======================================================

    def trim_response_smartly(

        self,
        response,
        limit=1000

    ):

        if len(response) <= limit:
            return response

        sentences = re.split(
            r"(?<=[.!?]) +",
            response
        )

        trimmed = ""

        for sentence in sentences:

            if len(trimmed + sentence) < limit:

                trimmed += sentence + " "

            else:
                break

        return trimmed.strip() + "..."

    # ======================================================
    # DETECT IF RESPONSE TOO ROBOTIC
    # ======================================================

    def detect_robotic_response(
        self,
        response
    ):

        robotic_keywords = [

            "operational",
            "strategic",
            "executive",
            "business intelligence",
            "optimization",
            "market positioning"

        ]

        score = 0

        lower = response.lower()

        for keyword in robotic_keywords:

            if keyword in lower:
                score += 1

        return score >= 4

    # ======================================================
    # FIX ROBOTIC RESPONSE
    # ======================================================

    def fix_robotic_response(
        self,
        response
    ):

        if self.detect_robotic_response(
            response
        ):

            response = self.make_more_natural(
                response
            )

        return response

    # ======================================================
    # FORMAT FINAL CHATBOT RESPONSE
    # ======================================================

    def format_chatbot_output(

        self,
        ai_response: str,
        routing_data: Dict[str, Any]

    ):

        try:

            formatted = self.format_response(

                ai_response,
                routing_data

            )

            formatted = self.fix_robotic_response(
                formatted
            )

            formatted = formatted.strip()

            return formatted

        except Exception as e:

            print(
                f"❌ Final Formatter Error: {e}"
            )

            return ai_response


# ==========================================================
# GLOBAL INSTANCE
# ==========================================================

response_formatter = ResponseFormatter()
