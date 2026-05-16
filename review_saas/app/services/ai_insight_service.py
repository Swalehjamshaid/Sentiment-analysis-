# ai_insight_service.py

```python
from datetime import datetime
from typing import Dict, Any, List
from statistics import mean


class AIInsightService:
    """
    AI Executive Insight Engine
    ----------------------------
    Generates:
    - Executive recommendations
    - Strategic business insights
    - Customer behavior intelligence
    - Operational risk alerts
    - Growth recommendations
    - Decision-making action plans
    """

    def __init__(self):
        pass

    # =========================================================
    # MAIN AI ENGINE
    # =========================================================

    def generate_ai_insights(
        self,
        company_name: str,
        analytics_data: Dict[str, Any]
    ) -> Dict[str, Any]:

        insights = {
            "company_name": company_name,
            "generated_at": str(datetime.utcnow()),
            "executive_summary": self.executive_summary(analytics_data),
            "business_strengths": self.business_strengths(analytics_data),
            "critical_issues": self.critical_issues(analytics_data),
            "customer_behavior_analysis": self.customer_behavior_analysis(analytics_data),
            "growth_opportunities": self.growth_opportunities(analytics_data),
            "operational_risks": self.operational_risks(analytics_data),
            "management_recommendations": self.management_recommendations(analytics_data),
            "staff_improvement_plan": self.staff_improvement_plan(analytics_data),
            "customer_retention_strategy": self.customer_retention_strategy(analytics_data),
            "marketing_recommendations": self.marketing_recommendations(analytics_data),
            "revenue_growth_strategy": self.revenue_growth_strategy(analytics_data),
            "competitive_position": self.competitive_position(analytics_data),
            "priority_actions": self.priority_actions(analytics_data),
            "thirty_day_action_plan": self.thirty_day_action_plan(analytics_data),
            "ninety_day_business_strategy": self.ninety_day_business_strategy(analytics_data),
            "executive_decision_support": self.executive_decision_support(analytics_data)
        }

        return insights

    # =========================================================
    # EXECUTIVE SUMMARY
    # =========================================================

    def executive_summary(self, data):
        rating = data.get("average_rating", 0)
        health = data.get("business_health_score", 0)
        risk = data.get("business_risk_level", "Unknown")

        if rating >= 4.5:
            status = "excellent"
        elif rating >= 4.0:
            status = "strong"
        elif rating >= 3.0:
            status = "moderate"
        else:
            status = "critical"

        return f"""
        The business currently demonstrates {status} market performance.

        Business health score is {health}% with a customer rating average of {rating}/5.

        Current operational risk level is classified as {risk}.

        AI analysis suggests focusing on customer experience optimization,
        operational efficiency, and reputation management to strengthen
        long-term business sustainability and market positioning.
        """.strip()

    # =========================================================
    # BUSINESS STRENGTHS
    # =========================================================

    def business_strengths(self, data):
        strengths = []

        rating = data.get("average_rating", 0)
        positive = data.get("positive_review_percentage", 0)

        if rating >= 4.5:
            strengths.append("Excellent customer satisfaction performance")

        if positive >= 70:
            strengths.append("Strong positive customer sentiment")

        if data.get("business_health_score", 0) >= 80:
            strengths.append("Healthy brand reputation")

        top_points = data.get("top_positive_points", [])

        for point in top_points[:5]:
            strengths.append(f"Customers frequently appreciate: {point[0]}")

        if not strengths:
            strengths.append("Business requires operational improvement focus")

        return strengths

    # =========================================================
    # CRITICAL ISSUES
    # =========================================================

    def critical_issues(self, data):
        issues = []

        negative = data.get("negative_review_percentage", 0)
        risk = data.get("business_risk_level", "Low")

        if negative >= 40:
            issues.append("High negative customer sentiment detected")

        if risk == "High":
            issues.append("Business risk level is critically high")

        customer_issues = data.get("top_customer_issues", [])

        for issue in customer_issues[:5]:
            issues.append(f"Recurring customer complaint: {issue[0]}")

        if not issues:
            issues.append("No major operational threats detected")

        return issues

    # =========================================================
    # CUSTOMER BEHAVIOR ANALYSIS
    # =========================================================

    def customer_behavior_analysis(self, data):
        positive = data.get("positive_review_percentage", 0)
        negative = data.get("negative_review_percentage", 0)

        insights = []

        if positive >= 70:
            insights.append(
                "Customers demonstrate strong brand trust and loyalty"
            )

        if negative >= 25:
            insights.append(
                "Customer frustration indicators are increasing"
            )

        if positive >= 50 and negative <= 15:
            insights.append(
                "Business is maintaining stable customer relationships"
            )

        insights.append(
            "Customers are highly influenced by service quality and response speed"
        )

        insights.append(
            "Online reputation is directly impacting customer perception"
        )

        return insights

    # =========================================================
    # GROWTH OPPORTUNITIES
    # =========================================================

    def growth_opportunities(self, data):
        opportunities = []

        rating = data.get("average_rating", 0)

        if rating >= 4:
            opportunities.append(
                "Strong reputation can be leveraged for premium positioning"
            )

        opportunities.append(
            "Increase customer retention through loyalty programs"
        )

        opportunities.append(
            "Use positive reviews in digital marketing campaigns"
        )

        opportunities.append(
            "Improve operational automation to reduce response delays"
        )

        opportunities.append(
            "Expand social media engagement using customer success stories"
        )

        return opportunities

    # =========================================================
    # OPERATIONAL RISKS
    # =========================================================

    def operational_risks(self, data):
        risks = []

        negative = data.get("negative_review_percentage", 0)

        if negative >= 30:
            risks.append(
                "Negative customer experiences may damage brand reputation"
            )

        risks.append(
            "Slow customer response handling may reduce retention"
        )

        risks.append(
            "Operational inconsistency may affect review quality"
        )

        risks.append(
            "Competitors with better service quality may capture market share"
        )

        return risks

    # =========================================================
    # MANAGEMENT RECOMMENDATIONS
    # =========================================================

    def management_recommendations(self, data):
        recommendations = []

        recommendations.append(
            "Monitor customer feedback weekly"
        )

        recommendations.append(
            "Establish a customer complaint resolution team"
        )

        recommendations.append(
            "Implement monthly staff performance reviews"
        )

        recommendations.append(
            "Track customer satisfaction KPIs regularly"
        )

        recommendations.append(
            "Develop an executive reporting system for decision-making"
        )

        return recommendations

    # =========================================================
    # STAFF IMPROVEMENT PLAN
    # =========================================================

    def staff_improvement_plan(self, data):
        return [
            "Conduct customer service training sessions",
            "Improve communication quality with customers",
            "Reduce response time to customer complaints",
            "Introduce customer handling SOPs",
            "Implement employee accountability tracking"
        ]

    # =========================================================
    # CUSTOMER RETENTION STRATEGY
    # =========================================================

    def customer_retention_strategy(self, data):
        return [
            "Respond to all negative reviews professionally",
            "Reward repeat customers",
            "Improve customer engagement after purchase",
            "Create loyalty and referral programs",
            "Offer personalized customer experiences"
        ]

    # =========================================================
    # MARKETING RECOMMENDATIONS
    # =========================================================

    def marketing_recommendations(self, data):
        return [
            "Promote positive reviews on social media",
            "Use customer testimonials in advertisements",
            "Improve Google Business profile optimization",
            "Increase local SEO visibility",
            "Launch customer reputation campaigns"
        ]

    # =========================================================
    # REVENUE GROWTH STRATEGY
    # =========================================================

    def revenue_growth_strategy(self, data):
        return [
            "Upsell services to satisfied customers",
            "Improve conversion rates using reputation marketing",
            "Increase customer retention to maximize lifetime value",
            "Focus on operational efficiency to improve profit margins",
            "Expand premium offerings for loyal customers"
        ]

    # =========================================================
    # COMPETITIVE POSITION
    # =========================================================

    def competitive_position(self, data):
        rating = data.get("average_rating", 0)

        if rating >= 4.5:
            return "Market Leader"

        if rating >= 4:
            return "Strong Competitor"

        if rating >= 3:
            return "Average Market Position"

        return "Weak Competitive Position"

    # =========================================================
    # PRIORITY ACTIONS
    # =========================================================

    def priority_actions(self, data):
        actions = []

        negative = data.get("negative_review_percentage", 0)

        if negative >= 20:
            actions.append(
                "Immediately address negative customer complaints"
            )

        actions.append(
            "Improve response handling process"
        )

        actions.append(
            "Strengthen customer support operations"
        )

        actions.append(
            "Monitor online reputation daily"
        )

        actions.append(
            "Track operational KPIs weekly"
        )

        return actions

    # =========================================================
    # 30 DAY ACTION PLAN
    # =========================================================

    def thirty_day_action_plan(self, data):
        return {
            "Week 1": [
                "Audit customer complaints",
                "Review operational weaknesses",
                "Analyze negative feedback patterns"
            ],
            "Week 2": [
                "Implement customer response SOPs",
                "Train staff on customer handling",
                "Improve communication workflows"
            ],
            "Week 3": [
                "Launch customer retention campaign",
                "Improve online reputation management",
                "Monitor KPI improvements"
            ],
            "Week 4": [
                "Evaluate operational performance",
                "Prepare executive management report",
                "Adjust business strategy based on analytics"
            ]
        }

    # =========================================================
    # 90 DAY BUSINESS STRATEGY
    # =========================================================

    def ninety_day_business_strategy(self, data):
        return {
            "Month 1": "Operational stabilization and complaint reduction",
            "Month 2": "Customer experience enhancement and retention growth",
            "Month 3": "Brand strengthening and revenue optimization"
        }

    # =========================================================
    # EXECUTIVE DECISION SUPPORT
    # =========================================================

    def executive_decision_support(self, data):
        health = data.get("business_health_score", 0)
        risk = data.get("business_risk_level", "Low")

        if health >= 85:
            return (
                "Business performance is strong. Management should focus on scaling operations and strengthening market leadership."
            )

        if health >= 70:
            return (
                "Business performance is stable. Management should prioritize customer experience improvements and operational optimization."
            )

        if risk == "High":
            return (
                "Immediate operational intervention is recommended to reduce customer dissatisfaction and protect brand reputation."
            )

        return (
            "Business requires structured operational improvements and stronger customer engagement strategies."
        )


# =========================================================
# GLOBAL INSTANCE
# =========================================================

ai_insight_service = AIInsightService()

```
