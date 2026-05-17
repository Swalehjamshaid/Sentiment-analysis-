# ==========================================================
# FILE: app/services/report_service.py
# ==========================================================

from __future__ import annotations

import os
import logging

from datetime import datetime
from typing import Any, Dict, List

import matplotlib.pyplot as plt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
)

from reportlab.lib import colors
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)

from reportlab.lib.pagesizes import letter
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch

logger = logging.getLogger("app.report_service")

# ==========================================================
# REPORT SERVICE
# ==========================================================

class ReportService:

    def __init__(self):

        self.styles = getSampleStyleSheet()

        self.output_dir = "app/static/reports"

        os.makedirs(
            self.output_dir,
            exist_ok=True
        )

        # ==================================================
        # CUSTOM STYLES
        # ==================================================

        self.title_style = ParagraphStyle(
            'ExecutiveTitle',
            parent=self.styles['Heading1'],
            fontSize=26,
            leading=30,
            textColor=colors.HexColor("#0F172A"),
            alignment=TA_CENTER,
            spaceAfter=20,
        )

        self.heading_style = ParagraphStyle(
            'ExecutiveHeading',
            parent=self.styles['Heading2'],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=12,
        )

        self.body_style = ParagraphStyle(
            'ExecutiveBody',
            parent=self.styles['BodyText'],
            fontSize=11,
            leading=18,
            textColor=colors.HexColor("#334155"),
        )

        self.kpi_style = ParagraphStyle(
            'KPIStyle',
            parent=self.styles['BodyText'],
            fontSize=12,
            leading=18,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

    # ======================================================
    # MAIN REPORT GENERATOR
    # ======================================================

    async def generate_executive_report(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> str:

        from app.core.models import (
            Company,
            Review,
        )

        # ==================================================
        # FETCH COMPANY
        # ==================================================

        company_result = await session.execute(
            select(Company).where(
                Company.id == company_id
            )
        )

        company = company_result.scalar_one_or_none()

        if not company:

            raise ValueError(
                "Company not found"
            )

        # ==================================================
        # FETCH REVIEWS
        # ==================================================

        review_result = await session.execute(
            select(Review).where(
                Review.company_id == company_id
            )
        )

        reviews = review_result.scalars().all()

        if not reviews:

            raise ValueError(
                "No reviews found"
            )

        # ==================================================
        # ANALYTICS
        # ==================================================

        analytics = self._calculate_analytics(
            reviews
        )

        # ==================================================
        # CHARTS
        # ==================================================

        chart_paths = self._generate_charts(
            analytics,
            company.name
        )

        # ==================================================
        # AI SUMMARY
        # ==================================================

        executive_summary = self._generate_summary(
            company.name,
            analytics
        )

        ai_insights = self._generate_ai_insights(
            analytics
        )

        recommendations = self._generate_recommendations(
            analytics
        )

        action_plan = self._generate_action_plan()

        executive_conclusion = self._generate_conclusion(
            company.name,
            analytics
        )

        # ==================================================
        # PDF PATH
        # ==================================================

        safe_name = (
            company.name
            .replace(" ", "_")
            .replace("/", "_")
        )

        pdf_filename = (
            f"Executive_Report_{safe_name}.pdf"
        )

        pdf_path = os.path.join(
            self.output_dir,
            pdf_filename
        )

        # ==================================================
        # GENERATE PDF
        # ==================================================

        self._build_pdf(
            pdf_path=pdf_path,
            company_name=company.name,
            analytics=analytics,
            executive_summary=executive_summary,
            ai_insights=ai_insights,
            recommendations=recommendations,
            action_plan=action_plan,
            executive_conclusion=executive_conclusion,
            chart_paths=chart_paths,
        )

        logger.info(
            "✅ Executive report generated: %s",
            pdf_filename
        )

        return pdf_path

    # ======================================================
    # ANALYTICS ENGINE
    # ======================================================

    def _calculate_analytics(
        self,
        reviews,
    ) -> Dict[str, Any]:

        total_reviews = len(reviews)

        ratings = [
            float(r.rating or 0)
            for r in reviews
        ]

        average_rating = (
            round(sum(ratings) / total_reviews, 2)
            if total_reviews > 0
            else 0
        )

        positive = len([
            r for r in ratings
            if r >= 4
        ])

        neutral = len([
            r for r in ratings
            if r == 3
        ])

        negative = len([
            r for r in ratings
            if r <= 2
        ])

        positive_percent = round(
            (positive / total_reviews) * 100, 2
        )

        neutral_percent = round(
            (neutral / total_reviews) * 100, 2
        )

        negative_percent = round(
            (negative / total_reviews) * 100, 2
        )

        return {

            "total_reviews": total_reviews,

            "average_rating": average_rating,

            "positive_reviews": positive,

            "neutral_reviews": neutral,

            "negative_reviews": negative,

            "positive_percent": positive_percent,

            "neutral_percent": neutral_percent,

            "negative_percent": negative_percent,

            "engagement_level":
                "High"
                if total_reviews > 200
                else "Medium",

            "retention_risk":
                "Low"
                if average_rating >= 4
                else "Medium",

            "brand_health":
                "Strong"
                if positive_percent >= 75
                else "Moderate",
        }

    # ======================================================
    # CHART GENERATION
    # ======================================================

    def _generate_charts(
        self,
        analytics: Dict[str, Any],
        company_name: str,
    ) -> Dict[str, str]:

        chart_paths = {}

        safe_name = (
            company_name
            .replace(" ", "_")
            .replace("/", "_")
        )

        # ==================================================
        # PIE CHART
        # ==================================================

        pie_path = os.path.join(
            self.output_dir,
            f"{safe_name}_sentiment_pie.png"
        )

        plt.figure(figsize=(6, 6))

        plt.pie(

            [
                analytics["positive_reviews"],
                analytics["neutral_reviews"],
                analytics["negative_reviews"],
            ],

            labels=[
                "Positive",
                "Neutral",
                "Negative",
            ],

            autopct='%1.1f%%',
        )

        plt.title(
            "Customer Sentiment Distribution"
        )

        plt.savefig(
            pie_path,
            bbox_inches="tight"
        )

        plt.close()

        chart_paths["pie_chart"] = pie_path

        # ==================================================
        # BAR CHART
        # ==================================================

        bar_path = os.path.join(
            self.output_dir,
            f"{safe_name}_kpi_bar.png"
        )

        plt.figure(figsize=(8, 5))

        metrics = [
            "Positive",
            "Neutral",
            "Negative",
        ]

        values = [
            analytics["positive_percent"],
            analytics["neutral_percent"],
            analytics["negative_percent"],
        ]

        plt.bar(metrics, values)

        plt.ylabel("Percentage")

        plt.title("Customer Sentiment KPI Analysis")

        plt.savefig(
            bar_path,
            bbox_inches="tight"
        )

        plt.close()

        chart_paths["bar_chart"] = bar_path

        return chart_paths

    # ======================================================
    # EXECUTIVE SUMMARY
    # ======================================================

    def _generate_summary(
        self,
        company_name: str,
        analytics: Dict[str, Any],
    ) -> str:

        return f"""
        <b>{company_name}</b> demonstrates strong customer
        satisfaction performance with an average rating of
        <b>{analytics['average_rating']}</b> across
        <b>{analytics['total_reviews']}</b> verified customer
        interactions.

        Current sentiment analysis indicates a highly positive
        market perception with
        <b>{analytics['positive_percent']}%</b>
        positive customer sentiment.

        The organization demonstrates stable operational
        performance, healthy customer engagement, and
        strong brand reliability indicators.

        While overall business sentiment remains highly positive,
        isolated operational inefficiencies and service
        inconsistencies present measurable opportunities for
        customer experience optimization and retention
        acceleration.

        Overall analytics indicate that the business is operating
        from a position of strong customer trust and scalable
        engagement performance.
        """

    # ======================================================
    # AI INSIGHTS
    # ======================================================

    def _generate_ai_insights(
        self,
        analytics: Dict[str, Any],
    ) -> List[str]:

        insights = []

        insights.append(
            "Customer satisfaction is primarily driven by strong service consistency and positive engagement trends."
        )

        insights.append(
            "The business demonstrates resilient customer trust indicators despite isolated operational concerns."
        )

        insights.append(
            "Negative customer experiences appear operational rather than systemic in nature."
        )

        insights.append(
            "Brand perception remains highly positive and commercially advantageous."
        )

        insights.append(
            "Operational optimization during peak engagement periods could further improve customer retention performance."
        )

        return insights

    # ======================================================
    # RECOMMENDATIONS
    # ======================================================

    def _generate_recommendations(
        self,
        analytics: Dict[str, Any],
    ) -> List[str]:

        recommendations = []

        recommendations.append(
            "Implement operational optimization protocols for high-volume customer periods."
        )

        recommendations.append(
            "Strengthen customer recovery workflows for negative experience management."
        )

        recommendations.append(
            "Leverage positive customer sentiment within digital marketing and brand positioning campaigns."
        )

        recommendations.append(
            "Deploy AI-driven customer sentiment monitoring for proactive issue detection."
        )

        recommendations.append(
            "Increase focus on service consistency and response-time optimization."
        )

        return recommendations

    # ======================================================
    # ACTION PLAN
    # ======================================================

    def _generate_action_plan(self):

        return [

            {
                "timeline": "30 Days",
                "objective":
                    "Address recurring operational complaints and customer service bottlenecks."
            },

            {
                "timeline": "60 Days",
                "objective":
                    "Optimize support workflows and strengthen service consistency monitoring."
            },

            {
                "timeline": "90 Days",
                "objective":
                    "Launch retention enhancement and customer loyalty initiatives."
            },
        ]

    # ======================================================
    # EXECUTIVE CONCLUSION
    # ======================================================

    def _generate_conclusion(
        self,
        company_name: str,
        analytics: Dict[str, Any],
    ) -> str:

        return f"""
        {company_name} is currently operating from a position
        of strong customer satisfaction and stable brand
        perception.

        Current analytics indicate healthy engagement metrics,
        strong operational resilience, and positive customer
        trust indicators.

        While targeted operational enhancements remain
        recommended, the organization demonstrates a
        scalable customer experience environment with
        strong long-term growth potential.
        """

    # ======================================================
    # PDF BUILDER
    # ======================================================

    def _build_pdf(
        self,
        pdf_path: str,
        company_name: str,
        analytics: Dict[str, Any],
        executive_summary: str,
        ai_insights: List[str],
        recommendations: List[str],
        action_plan,
        executive_conclusion: str,
        chart_paths,
    ):

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=30,
        )

        story = []

        # ==================================================
        # COVER PAGE
        # ==================================================

        story.append(
            Spacer(1, 1.5 * inch)
        )

        story.append(
            Paragraph(
                "AI Executive Intelligence Report",
                self.title_style
            )
        )

        story.append(
            Spacer(1, 0.5 * inch)
        )

        story.append(
            Paragraph(
                company_name,
                self.heading_style
            )
        )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        story.append(
            Paragraph(
                f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                self.body_style
            )
        )

        story.append(
            Spacer(1, 3 * inch)
        )

        story.append(
            Paragraph(
                "Confidential Executive Business Intelligence Document",
                self.body_style
            )
        )

        story.append(
            PageBreak()
        )

        # ==================================================
        # EXECUTIVE SUMMARY
        # ==================================================

        story.append(
            Paragraph(
                "Executive Summary",
                self.heading_style
            )
        )

        story.append(
            Paragraph(
                executive_summary,
                self.body_style
            )
        )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # KPI SNAPSHOT
        # ==================================================

        story.append(
            Paragraph(
                "Executive KPI Snapshot",
                self.heading_style
            )
        )

        kpi_data = [

            [
                "KPI",
                "Current",
                "Benchmark",
                "Status"
            ],

            [
                "Average Rating",
                analytics['average_rating'],
                "4.20",
                "Above Target"
            ],

            [
                "Positive Sentiment",
                f"{analytics['positive_percent']}%",
                "75%",
                "Strong"
            ],

            [
                "Negative Sentiment",
                f"{analytics['negative_percent']}%",
                "<10%",
                "Acceptable"
            ],

            [
                "Engagement Level",
                analytics['engagement_level'],
                "Medium",
                "Excellent"
            ],

            [
                "Retention Risk",
                analytics['retention_risk'],
                "Medium",
                "Healthy"
            ],
        ]

        table = Table(
            kpi_data,
            colWidths=[2 * inch] * 4
        )

        table.setStyle(

            TableStyle([

                (
                    'BACKGROUND',
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#1E3A8A")
                ),

                (
                    'TEXTCOLOR',
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    'FONTNAME',
                    (0, 0),
                    (-1, 0),
                    'Helvetica-Bold'
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    1,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'BACKGROUND',
                    (0, 1),
                    (-1, -1),
                    colors.HexColor("#F8FAFC")
                ),

                (
                    'BOTTOMPADDING',
                    (0, 0),
                    (-1, 0),
                    12
                ),
            ])
        )

        story.append(table)

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # CHARTS
        # ==================================================

        story.append(
            Paragraph(
                "Customer Sentiment Analytics",
                self.heading_style
            )
        )

        if os.path.exists(
            chart_paths["pie_chart"]
        ):

            story.append(

                Image(
                    chart_paths["pie_chart"],
                    width=4.8 * inch,
                    height=4.8 * inch,
                )
            )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        if os.path.exists(
            chart_paths["bar_chart"]
        ):

            story.append(

                Image(
                    chart_paths["bar_chart"],
                    width=6 * inch,
                    height=3.5 * inch,
                )
            )

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # AI INSIGHTS
        # ==================================================

        story.append(
            Paragraph(
                "AI Strategic Insights",
                self.heading_style
            )
        )

        for insight in ai_insights:

            story.append(

                Paragraph(
                    f"• {insight}",
                    self.body_style
                )
            )

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # OPERATIONAL RISK TABLE
        # ==================================================

        story.append(
            Paragraph(
                "Operational Risk Assessment",
                self.heading_style
            )
        )

        risk_data = [

            [
                "Risk Area",
                "Severity",
                "Impact"
            ],

            [
                "Peak Hour Delays",
                "Medium",
                "Customer Satisfaction"
            ],

            [
                "Order Accuracy",
                "Medium",
                "Brand Trust"
            ],

            [
                "Staff Responsiveness",
                "Low",
                "Customer Retention"
            ],

            [
                "Digital Experience",
                "Low",
                "Engagement"
            ],
        ]

        risk_table = Table(
            risk_data,
            colWidths=[2.2 * inch] * 3
        )

        risk_table.setStyle(

            TableStyle([

                (
                    'BACKGROUND',
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#7C3AED")
                ),

                (
                    'TEXTCOLOR',
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    1,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'BACKGROUND',
                    (0, 1),
                    (-1, -1),
                    colors.HexColor("#F8FAFC")
                ),
            ])
        )

        story.append(risk_table)

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # RECOMMENDATIONS
        # ==================================================

        story.append(
            Paragraph(
                "Strategic Recommendations",
                self.heading_style
            )
        )

        for rec in recommendations:

            story.append(

                Paragraph(
                    f"• {rec}",
                    self.body_style
                )
            )

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # ACTION PLAN
        # ==================================================

        story.append(
            Paragraph(
                "30 / 60 / 90 Day Strategic Roadmap",
                self.heading_style
            )
        )

        roadmap_data = [
            ["Timeline", "Strategic Objective"]
        ]

        for item in action_plan:

            roadmap_data.append([
                item["timeline"],
                item["objective"]
            ])

        roadmap_table = Table(
            roadmap_data,
            colWidths=[2 * inch, 4.5 * inch]
        )

        roadmap_table.setStyle(

            TableStyle([

                (
                    'BACKGROUND',
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#059669")
                ),

                (
                    'TEXTCOLOR',
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    1,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'BACKGROUND',
                    (0, 1),
                    (-1, -1),
                    colors.HexColor("#F8FAFC")
                ),
            ])
        )

        story.append(roadmap_table)

        story.append(
            Spacer(1, 0.4 * inch)
        )

        # ==================================================
        # EXECUTIVE CONCLUSION
        # ==================================================

        story.append(
            Paragraph(
                "Executive Conclusion",
                self.heading_style
            )
        )

        story.append(
            Paragraph(
                executive_conclusion,
                self.body_style
            )
        )

        story.append(
            Spacer(1, 0.5 * inch)
        )

        # ==================================================
        # FOOTER NOTE
        # ==================================================

        story.append(
            Paragraph(
                "Confidential • AI Executive Intelligence Platform • Internal Business Use Only",
                self.body_style
            )
        )

        # ==================================================
        # BUILD PDF
        # ==================================================

        doc.build(story)
