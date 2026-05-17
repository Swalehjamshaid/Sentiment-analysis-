# ==========================================================
# FILE: app/services/intent_router.py
# WORLD-CLASS HUMAN-LIKE INTENT ROUTER
# ENTERPRISE AI RESPONSE ORCHESTRATION ENGINE
# ==========================================================

import re
from typing import Dict, Any


# ==========================================================
# INTENT ROUTER CLASS
# ==========================================================

class IntentRouter:

    """
    ======================================================
    HUMAN-LIKE INTELLIGENT RESPONSE ROUTER
    ======================================================

    PURPOSE:
    - Detect user intent
    - Detect response style
    - Route AI behavior dynamically
    - Make chatbot conversational
    - Improve human-like interaction
    - Reduce robotic responses
    - Improve executive intelligence

    MODES:
    - SHORT_MODE
    - BULLET_MODE
    - EXECUTIVE_MODE
    - SUMMARY_MODE
    - CASUAL_MODE
    - KPI_MODE
    - RECOMMENDATION_MODE
    - COMPARISON_MODE
    """

    # ======================================================
    # MAIN ROUTER
    # ======================================================

    def detect_intent(
        self,
        query: str
    ) -> Dict[str, Any]:

        if not query:

            return self.default_response()

        original_query = query

        query = query.lower().strip()

        # ==================================================
        # RESPONSE LENGTH DETECTION
        # ==================================================

        short_patterns = [

            "one sentence",
            "single sentence",
            "short answer",
            "briefly",
            "in short",
            "quick answer",
            "just tell me",
            "shortly",
            "simple answer"

        ]

        bullet_patterns = [

            "bullet",
            "bullet points",
            "5 points",
            "list",
            "top points",
            "key points"

        ]

        detailed_patterns = [

            "detailed",
            "deep analysis",
            "executive analysis",
            "complete analysis",
            "full analysis",
            "strategic analysis",
            "professional analysis"

        ]

        summary_patterns = [

            "summary",
            "summarize",
            "overview",
            "overall",
            "final summary"

        ]

        recommendation_patterns = [

            "recommend",
            "recommendation",
            "improve",
            "solution",
            "fix",
            "how to improve",
            "what should",
            "what needs improvement"

        ]

        comparison_patterns = [

            "compare",
            "comparison",
            "better than",
            "difference",
            "vs"

        ]

        kpi_patterns = [

            "kpi",
            "metrics",
            "rating",
            "score",
            "sentiment",
            "statistics",
            "numbers",
            "performance"

        ]

        issue_patterns = [

            "issue",
            "problem",
            "complaint",
            "negative",
            "bad reviews",
            "major issue"

        ]

        casual_patterns = [

            "hello",
            "hi",
            "hey",
            "thanks",
            "thank you",
            "ok",
            "okay"

        ]

        # ==================================================
        # DETECT RESPONSE MODE
        # ==================================================

        response_mode = "NORMAL_MODE"

        # ==================================================
        # SHORT MODE
        # ==================================================

        if self.contains_pattern(
            query,
            short_patterns
        ):

            response_mode = "SHORT_MODE"

        # ==================================================
        # BULLET MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            bullet_patterns
        ):

            response_mode = "BULLET_MODE"

        # ==================================================
        # EXECUTIVE MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            detailed_patterns
        ):

            response_mode = "EXECUTIVE_MODE"

        # ==================================================
        # SUMMARY MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            summary_patterns
        ):

            response_mode = "SUMMARY_MODE"

        # ==================================================
        # KPI MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            kpi_patterns
        ):

            response_mode = "KPI_MODE"

        # ==================================================
        # RECOMMENDATION MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            recommendation_patterns
        ):

            response_mode = "RECOMMENDATION_MODE"

        # ==================================================
        # COMPARISON MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            comparison_patterns
        ):

            response_mode = "COMPARISON_MODE"

        # ==================================================
        # ISSUE MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            issue_patterns
        ):

            response_mode = "ISSUE_MODE"

        # ==================================================
        # CASUAL MODE
        # ==================================================

        elif self.contains_pattern(
            query,
            casual_patterns
        ):

            response_mode = "CASUAL_MODE"

        # ==================================================
        # DETECT COMPLEXITY
        # ==================================================

        complexity = self.detect_complexity(query)

        # ==================================================
        # DETECT USER TONE
        # ==================================================

        tone = self.detect_tone(query)

        # ==================================================
        # DETECT EXECUTIVE NEED
        # ==================================================

        executive_required = self.detect_executive_need(
            query
        )

        # ==================================================
        # DETECT RESPONSE LENGTH
        # ==================================================

        response_length = self.detect_response_length(
            response_mode
        )

        # ==================================================
        # DETECT HUMANIZATION LEVEL
        # ==================================================

        humanization_level = self.detect_humanization_level(
            response_mode
        )

        # ==================================================
        # DETECT FORMAT STYLE
        # ==================================================

        format_style = self.detect_format_style(
            response_mode
        )

        # ==================================================
        # DETECT STRATEGIC LEVEL
        # ==================================================

        strategic_level = self.detect_strategic_level(
            response_mode
        )

        # ==================================================
        # FINAL RESULT
        # ==================================================

        result = {

            "original_query":
                original_query,

            "clean_query":
                query,

            "response_mode":
                response_mode,

            "complexity":
                complexity,

            "tone":
                tone,

            "executive_required":
                executive_required,

            "response_length":
                response_length,

            "humanization_level":
                humanization_level,

            "format_style":
                format_style,

            "strategic_level":
                strategic_level,

            "needs_bullets":
                response_mode == "BULLET_MODE",

            "needs_short_answer":
                response_mode == "SHORT_MODE",

            "needs_summary":
                response_mode == "SUMMARY_MODE",

            "needs_recommendations":
                response_mode == "RECOMMENDATION_MODE",

            "needs_kpi_focus":
                response_mode == "KPI_MODE",

            "needs_issue_focus":
                response_mode == "ISSUE_MODE"

        }

        return result

    # ======================================================
    # PATTERN MATCHING
    # ======================================================

    def contains_pattern(
        self,
        query,
        patterns
    ):

        for pattern in patterns:

            if pattern in query:
                return True

        return False

    # ======================================================
    # COMPLEXITY DETECTION
    # ======================================================

    def detect_complexity(
        self,
        query
    ):

        word_count = len(
            query.split()
        )

        if word_count <= 5:
            return "LOW"

        elif word_count <= 15:
            return "MEDIUM"

        return "HIGH"

    # ======================================================
    # USER TONE DETECTION
    # ======================================================

    def detect_tone(
        self,
        query
    ):

        professional_patterns = [

            "executive",
            "analysis",
            "strategic",
            "business",
            "professional"

        ]

        casual_patterns = [

            "hey",
            "hi",
            "what",
            "tell me",
            "just"

        ]

        if self.contains_pattern(
            query,
            professional_patterns
        ):

            return "PROFESSIONAL"

        if self.contains_pattern(
            query,
            casual_patterns
        ):

            return "CASUAL"

        return "NORMAL"

    # ======================================================
    # EXECUTIVE NEED DETECTION
    # ======================================================

    def detect_executive_need(
        self,
        query
    ):

        executive_patterns = [

            "executive",
            "strategy",
            "business",
            "risk",
            "kpi",
            "market",
            "revenue",
            "financial"

        ]

        return self.contains_pattern(
            query,
            executive_patterns
        )

    # ======================================================
    # RESPONSE LENGTH
    # ======================================================

    def detect_response_length(
        self,
        mode
    ):

        mapping = {

            "SHORT_MODE": "SHORT",

            "BULLET_MODE": "MEDIUM",

            "EXECUTIVE_MODE": "LONG",

            "SUMMARY_MODE": "MEDIUM",

            "KPI_MODE": "MEDIUM",

            "RECOMMENDATION_MODE": "MEDIUM",

            "COMPARISON_MODE": "LONG",

            "ISSUE_MODE": "SHORT",

            "CASUAL_MODE": "SHORT",

            "NORMAL_MODE": "MEDIUM"

        }

        return mapping.get(
            mode,
            "MEDIUM"
        )

    # ======================================================
    # HUMANIZATION LEVEL
    # ======================================================

    def detect_humanization_level(
        self,
        mode
    ):

        mapping = {

            "SHORT_MODE": "VERY_HIGH",

            "CASUAL_MODE": "VERY_HIGH",

            "ISSUE_MODE": "HIGH",

            "SUMMARY_MODE": "HIGH",

            "BULLET_MODE": "MEDIUM",

            "EXECUTIVE_MODE": "LOW",

            "KPI_MODE": "LOW",

            "COMPARISON_MODE": "MEDIUM",

            "RECOMMENDATION_MODE": "MEDIUM",

            "NORMAL_MODE": "HIGH"

        }

        return mapping.get(
            mode,
            "HIGH"
        )

    # ======================================================
    # FORMAT STYLE
    # ======================================================

    def detect_format_style(
        self,
        mode
    ):

        mapping = {

            "SHORT_MODE": "SIMPLE",

            "CASUAL_MODE": "CONVERSATIONAL",

            "ISSUE_MODE": "DIRECT",

            "BULLET_MODE": "BULLET",

            "EXECUTIVE_MODE": "EXECUTIVE",

            "SUMMARY_MODE": "SUMMARY",

            "KPI_MODE": "ANALYTICS",

            "COMPARISON_MODE": "COMPARISON",

            "RECOMMENDATION_MODE": "RECOMMENDATION",

            "NORMAL_MODE": "NORMAL"

        }

        return mapping.get(
            mode,
            "NORMAL"
        )

    # ======================================================
    # STRATEGIC LEVEL
    # ======================================================

    def detect_strategic_level(
        self,
        mode
    ):

        mapping = {

            "EXECUTIVE_MODE": "HIGH",

            "KPI_MODE": "HIGH",

            "COMPARISON_MODE": "HIGH",

            "RECOMMENDATION_MODE": "MEDIUM",

            "SUMMARY_MODE": "MEDIUM",

            "BULLET_MODE": "LOW",

            "SHORT_MODE": "LOW",

            "ISSUE_MODE": "LOW",

            "CASUAL_MODE": "LOW",

            "NORMAL_MODE": "MEDIUM"

        }

        return mapping.get(
            mode,
            "MEDIUM"
        )

    # ======================================================
    # DEFAULT RESPONSE
    # ======================================================

    def default_response(self):

        return {

            "response_mode":
                "NORMAL_MODE",

            "complexity":
                "MEDIUM",

            "tone":
                "NORMAL",

            "executive_required":
                False,

            "response_length":
                "MEDIUM",

            "humanization_level":
                "HIGH",

            "format_style":
                "NORMAL",

            "strategic_level":
                "MEDIUM"

        }


# ==========================================================
# GLOBAL INSTANCE
# ==========================================================

intent_router = IntentRouter()
