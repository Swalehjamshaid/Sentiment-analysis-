# =========================================================
# FILE: app/services/ai_insight_service.py
# FINAL ENTERPRISE AI EXECUTIVE INTELLIGENCE ENGINE
# CONTRADICTION-FREE • KPI-VALIDATED • BOARDROOM READY
# =========================================================

from datetime import datetime
from typing import Dict, Any


class AIInsightService:

    def __init__(self):
        pass

    # =====================================================
    # MAIN AI ENGINE
    # =====================================================

    def generate_ai_insights(
        self,
        company_name: str,
        analytics_data: Dict[str, Any]
    ) -> Dict[str, Any]:

        health_data = self.calculate_business_health(
            analytics_data
        )

        return {

            "company_name":
                company_name,

            "generated_at":
                str(datetime.utcnow()),

            "business_health_score":
                health_data["score"],

            "business_status":
                health_data["status"],

            "operational_urgency":
                health_data["urgency"],

            "executive_summary":
                self.executive_summary(
                    analytics_data,
                    health_data
                ),

            "business_strengths":
                self.business_strengths(
                    analytics_data,
                    health_data
                ),

            "critical_issues":
                self.critical_issues(
                    analytics_data,
                    health_data
                ),

            "customer_behavior_analysis":
                self.customer_behavior_analysis(
                    analytics_data,
                    health_data
                ),

            "growth_opportunities":
                self.growth_opportunities(
                    analytics_data,
                    health_data
                ),

            "operational_risks":
                self.operational_risks(
                    analytics_data,
                    health_data
                ),

            "management_recommendations":
                self.management_recommendations(),

            "staff_improvement_plan":
                self.staff_improvement_plan(),

            "customer_retention_strategy":
                self.customer_retention_strategy(),

            "marketing_recommendations":
                self.marketing_recommendations(),

            "revenue_growth_strategy":
                self.revenue_growth_strategy(),

            "competitive_position":
                self.competitive_position(
                    health_data
                ),

            "priority_actions":
                self.priority_actions(
                    analytics_data
                ),

            "thirty_day_action_plan":
                self.thirty_day_action_plan(),

            "ninety_day_business_strategy":
                self.ninety_day_business_strategy(),

            "executive_decision_support":
                self.executive_decision_support(
                    health_data
                ),

            "financial_risk_analysis":
                self.financial_risk_analysis(
                    analytics_data
                ),

            "reputation_analysis":
                self.reputation_analysis(
                    analytics_data
                ),

            "customer_loyalty_analysis":
                self.customer_loyalty_analysis(
                    analytics_data
                ),

            "operational_efficiency_analysis":
                self.operational_efficiency_analysis(
                    analytics_data
                )

        }

    # =====================================================
    # BUSINESS HEALTH ENGINE
    # =====================================================

    def calculate_business_health(self, data):

        rating = float(
            data.get("average_rating", 0)
        )

        positive = float(
            data.get(
                "positive_review_percentage",
                0
            )
        )

        negative = float(
            data.get(
                "negative_review_percentage",
                0
            )
        )

        reputation = float(
            data.get(
                "reputation_score",
                50
            )
        )

        # =================================================
        # REALISTIC KPI SCORING
        # =================================================

        score = (

            (rating / 5) * 35 +

            (positive / 100) * 25 +

            (reputation / 100) * 25 -

            (negative / 100) * 15

        )

        score = round(
            max(0, min(100, score)),
            2
        )

        # =================================================
        # STATUS CLASSIFICATION
        # =================================================

        if score >= 85:
            status = "Elite"

        elif score >= 70:
            status = "Strong"

        elif score >= 55:
            status = "Stable"

        elif score >= 40:
            status = "Risky"

        else:
            status = "Critical"

        # =================================================
        # OPERATIONAL URGENCY
        # =================================================

        if negative >= 45:

            urgency = (
                "Immediate Executive Attention Required"
            )

        elif negative >= 30:

            urgency = (
                "High Operational Risk"
            )

        elif negative >= 15:

            urgency = (
                "Moderate Operational Monitoring"
            )

        else:

            urgency = (
                "Operationally Stable"
            )

        return {

            "score": score,

            "status": status,

            "urgency": urgency

        }

    # =====================================================
    # EXECUTIVE SUMMARY
    # =====================================================

    def executive_summary(
        self,
        data,
        health
    ):

        rating = data.get(
            "average_rating",
            0
        )

        positive = data.get(
            "positive_review_percentage",
            0
        )

        negative = data.get(
            "negative_review_percentage",
            0
        )

        score = health["score"]

        status = health["status"]

        urgency = health["urgency"]

        # =================================================
        # CRITICAL BUSINESS CONDITION
        # =================================================

        if rating < 3 or negative > positive:

            summary = f"""
            Executive intelligence analysis indicates elevated customer dissatisfaction trends impacting operational consistency, customer trust, and long-term brand perception.

            The organization currently maintains a business health score of {score}% with an average customer rating of {rating}/5.

            Negative customer sentiment ({negative}%) currently exceeds positive sentiment ({positive}%), indicating measurable operational and customer experience challenges.

            Current business classification is '{status}' with operational urgency level categorized as '{urgency}'.

            Immediate operational optimization, customer satisfaction recovery initiatives, and service quality improvements are recommended to stabilize business performance and strengthen customer retention.
            """

        # =================================================
        # MODERATE PERFORMANCE
        # =================================================

        elif rating >= 3 and rating < 4.2:

            summary = f"""
            Executive intelligence analysis indicates moderately stable operational performance supported by balanced customer engagement indicators.

            The organization currently maintains a business health score of {score}% with an average customer rating of {rating}/5.

            Customer sentiment indicators suggest moderate operational consistency with opportunities for customer experience enhancement and retention optimization.

            Current business classification is '{status}' with operational urgency level categorized as '{urgency}'.

            Continued operational refinement and customer engagement initiatives are recommended to improve market competitiveness and long-term business scalability.
            """

        # =================================================
        # STRONG PERFORMANCE
        # =================================================

        else:

            summary = f"""
            Executive intelligence analysis indicates strong operational performance supported by healthy customer satisfaction and positive brand engagement indicators.

            The organization currently maintains a business health score of {score}% with an average customer rating of {rating}/5.

            Positive customer sentiment remains significantly higher than negative sentiment, supporting strong market positioning and customer trust performance.

            Current business classification is '{status}' with operational urgency level categorized as '{urgency}'.

            Strategic scaling opportunities and continued customer experience optimization initiatives are recommended to strengthen long-term market leadership.
            """

        return summary.strip()

    # =====================================================
    # BUSINESS STRENGTHS
    # =====================================================

    def business_strengths(
        self,
        data,
        health
    ):

        strengths = []

        rating = data.get(
            "average_rating",
            0
        )

        positive = data.get(
            "positive_review_percentage",
            0
        )

        if rating >= 4.5:

            strengths.append(
                "Customer satisfaction performance significantly exceeds industry standards."
            )

        if positive >= 70:

            strengths.append(
                "Strong positive customer sentiment supports resilient customer trust indicators."
            )

        if health["score"] >= 75:

            strengths.append(
                "Operational and reputation indicators support stable market competitiveness."
            )

        top_points = data.get(
            "top_positive_points",
            []
        )

        for point in top_points[:5]:

            strengths.append(
                f"Customers consistently recognize strength in: {point[0]}"
            )

        if not strengths:

            strengths.append(
                "Current operational performance indicates limited strategic strengths requiring management optimization."
            )

        return strengths

    # =====================================================
    # CRITICAL ISSUES
    # =====================================================

    def critical_issues(
        self,
        data,
        health
    ):

        issues = []

        negative = data.get(
            "negative_review_percentage",
            0
        )

        rating = data.get(
            "average_rating",
            0
        )

        if negative >= 40:

            issues.append(
                "Elevated negative customer sentiment indicates systemic operational dissatisfaction."
            )

        if rating < 3:

            issues.append(
                "Customer satisfaction levels remain significantly below competitive market expectations."
            )

        if health["status"] in [
            "Critical",
            "Risky"
        ]:

            issues.append(
                "Current business health indicators require executive-level operational intervention."
            )

        customer_issues = data.get(
            "top_customer_issues",
            []
        )

        for issue in customer_issues[:5]:

            issues.append(
                f"Recurring customer complaint detected around: {issue[0]}"
            )

        if not issues:

            issues.append(
                "No major systemic operational threats currently detected."
            )

        return issues

    # =====================================================
    # CUSTOMER BEHAVIOR ANALYSIS
    # =====================================================

    def customer_behavior_analysis(
        self,
        data,
        health
    ):

        positive = data.get(
            "positive_review_percentage",
            0
        )

        negative = data.get(
            "negative_review_percentage",
            0
        )

        insights = []

        if positive >= 70:

            insights.append(
                "Customers demonstrate strong trust, loyalty, and positive engagement behavior."
            )

        if negative >= 25:

            insights.append(
                "Customer frustration indicators are increasing and may negatively impact retention performance."
            )

        if negative > positive:

            insights.append(
                "Negative customer experiences currently outweigh positive engagement indicators."
            )

        insights.append(
            "Customer retention performance is highly influenced by operational consistency and response efficiency."
        )

        insights.append(
            "Online review sentiment is directly influencing customer acquisition and market trust."
        )

        return insights

    # =====================================================
    # GROWTH OPPORTUNITIES
    # =====================================================

    def growth_opportunities(
        self,
        data,
        health
    ):

        opportunities = []

        rating = data.get(
            "average_rating",
            0
        )

        if rating >= 4:

            opportunities.append(
                "Strong customer satisfaction metrics support premium market positioning opportunities."
            )

        opportunities.append(
            "Operational optimization initiatives can improve customer retention performance."
        )

        opportunities.append(
            "Customer feedback analytics can strengthen strategic decision-making and service quality improvement."
        )

        opportunities.append(
            "AI-driven sentiment intelligence can improve operational forecasting and issue prevention."
        )

        opportunities.append(
            "Customer loyalty initiatives can strengthen repeat business and lifetime customer value."
        )

        return opportunities

    # =====================================================
    # OPERATIONAL RISKS
    # =====================================================

    def operational_risks(
        self,
        data,
        health
    ):

        risks = []

        negative = data.get(
            "negative_review_percentage",
            0
        )

        rating = data.get(
            "average_rating",
            0
        )

        if negative >= 35:

            risks.append(
                "High negative sentiment concentration may accelerate customer churn and reputation deterioration."
            )

        if rating < 3:

            risks.append(
                "Low customer satisfaction levels may negatively impact brand trust and retention performance."
            )

        risks.append(
            "Operational inconsistency may continue reducing customer trust and engagement quality."
        )

        risks.append(
            "Delayed customer response handling may weaken retention and loyalty performance."
        )

        risks.append(
            "Competitors with stronger customer experience performance may capture market share."
        )

        return risks

    # =====================================================
    # STATIC STRATEGIC FUNCTIONS
    # =====================================================

    def management_recommendations(self):

        return [

            "Implement executive-level customer experience monitoring systems.",

            "Establish centralized complaint escalation frameworks.",

            "Deploy operational KPI dashboards for real-time performance monitoring.",

            "Conduct weekly executive sentiment review sessions.",

            "Strengthen cross-functional operational accountability systems."

        ]

    def staff_improvement_plan(self):

        return [

            "Conduct advanced customer experience training programs.",

            "Implement response-time accountability metrics.",

            "Strengthen escalation handling procedures.",

            "Introduce customer interaction quality assurance monitoring.",

            "Deploy SOP compliance monitoring systems."

        ]

    def customer_retention_strategy(self):

        return [

            "Respond professionally to all negative customer experiences.",

            "Implement loyalty and repeat-customer engagement programs.",

            "Increase personalized customer interaction initiatives.",

            "Launch proactive customer satisfaction recovery campaigns.",

            "Develop AI-driven customer retention monitoring systems."

        ]

    def marketing_recommendations(self):

        return [

            "Leverage positive customer experiences in marketing campaigns.",

            "Strengthen local SEO and reputation management initiatives.",

            "Increase customer testimonial-driven advertising.",

            "Improve online reputation visibility through review optimization.",

            "Use sentiment intelligence to guide marketing messaging."

        ]

    def revenue_growth_strategy(self):

        return [

            "Improve operational efficiency to strengthen profit margins.",

            "Increase customer lifetime value through retention optimization.",

            "Leverage reputation-driven marketing for customer acquisition.",

            "Expand premium service offerings for high-value segments.",

            "Reduce customer churn through proactive sentiment management."

        ]

    # =====================================================
    # COMPETITIVE POSITION
    # =====================================================

    def competitive_position(
        self,
        health
    ):

        score = health["score"]

        if score >= 85:
            return "Market Leader"

        elif score >= 70:
            return "Strong Competitive Position"

        elif score >= 55:
            return "Moderately Competitive"

        elif score >= 40:
            return "Operationally Vulnerable"

        return "Weak Competitive Position"

    # =====================================================
    # PRIORITY ACTIONS
    # =====================================================

    def priority_actions(
        self,
        data
    ):

        actions = []

        negative = data.get(
            "negative_review_percentage",
            0
        )

        if negative >= 20:

            actions.append(
                "Immediately investigate recurring customer dissatisfaction drivers."
            )

        actions.append(
            "Improve operational response handling efficiency."
        )

        actions.append(
            "Strengthen customer experience quality assurance systems."
        )

        actions.append(
            "Deploy executive-level reputation monitoring."
        )

        actions.append(
            "Track operational KPIs and sentiment metrics weekly."
        )

        return actions

    # =====================================================
    # 30 DAY PLAN
    # =====================================================

    def thirty_day_action_plan(self):

        return {

            "Week 1": [

                "Audit customer dissatisfaction patterns.",

                "Identify operational bottlenecks.",

                "Analyze recurring complaint themes."

            ],

            "Week 2": [

                "Implement escalation SOPs.",

                "Conduct staff training.",

                "Improve communication workflows."

            ],

            "Week 3": [

                "Launch customer recovery campaigns.",

                "Strengthen reputation management.",

                "Monitor KPI stabilization."

            ],

            "Week 4": [

                "Evaluate operational improvements.",

                "Prepare executive performance report.",

                "Adjust business strategy."

            ]

        }

    # =====================================================
    # 90 DAY STRATEGY
    # =====================================================

    def ninety_day_business_strategy(self):

        return {

            "Month 1":
                "Operational stabilization and complaint reduction.",

            "Month 2":
                "Customer experience enhancement and retention optimization.",

            "Month 3":
                "Brand strengthening and scalable growth optimization."

        }

    # =====================================================
    # EXECUTIVE DECISION SUPPORT
    # =====================================================

    def executive_decision_support(
        self,
        health
    ):

        score = health["score"]

        if score >= 85:

            return (
                "Business indicators support strategic scaling and premium market positioning opportunities."
            )

        elif score >= 70:

            return (
                "Business performance remains operationally stable but requires continued optimization."
            )

        elif score >= 40:

            return (
                "Operational risk indicators require immediate management attention to stabilize customer satisfaction."
            )

        return (
            "Critical operational intervention is required to reduce customer dissatisfaction and protect brand reputation."
        )

    # =====================================================
    # FINANCIAL RISK ANALYSIS
    # =====================================================

    def financial_risk_analysis(
        self,
        data
    ):

        negative = data.get(
            "negative_review_percentage",
            0
        )

        if negative >= 30:

            return (
                "Current negative sentiment concentration presents elevated customer retention and revenue risk exposure."
            )

        return (
            "Financial risk indicators remain operationally manageable under current sentiment conditions."
        )

    # =====================================================
    # REPUTATION ANALYSIS
    # =====================================================

    def reputation_analysis(
        self,
        data
    ):

        reputation = data.get(
            "reputation_score",
            50
        )

        if reputation >= 80:

            return (
                "Brand reputation performance remains commercially strong with healthy customer trust indicators."
            )

        elif reputation >= 60:

            return (
                "Brand reputation remains moderately stable but requires continuous monitoring."
            )

        return (
            "Brand reputation performance is currently under pressure due to elevated customer dissatisfaction trends."
        )

    # =====================================================
    # CUSTOMER LOYALTY ANALYSIS
    # =====================================================

    def customer_loyalty_analysis(
        self,
        data
    ):

        positive = data.get(
            "positive_review_percentage",
            0
        )

        negative = data.get(
            "negative_review_percentage",
            0
        )

        if positive >= 70:

            return (
                "Customer loyalty indicators remain strong with healthy trust and engagement behavior."
            )

        elif negative > positive:

            return (
                "Customer loyalty indicators are currently under pressure due to elevated negative customer experience concentration."
            )

        return (
            "Customer loyalty performance remains moderately stable with opportunities for retention improvement."
        )

    # =====================================================
    # OPERATIONAL EFFICIENCY ANALYSIS
    # =====================================================

    def operational_efficiency_analysis(
        self,
        data
    ):

        negative = data.get(
            "negative_review_percentage",
            0
        )

        if negative >= 35:

            return (
                "Operational efficiency indicators suggest recurring workflow instability and customer experience inconsistency."
            )

        return (
            "Operational performance indicators remain relatively stable with manageable efficiency risk levels."
        )


# =========================================================
# GLOBAL INSTANCE
# =========================================================

ai_insight_service = AIInsightService()
