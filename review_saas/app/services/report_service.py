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
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
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

        recommendations = self._generate_recommendations(
            analytics
        )

        action_plan = self._generate_action_plan()

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
            recommendations=recommendations,
            action_plan=action_plan,
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

        return {

            "total_reviews": total_reviews,

            "average_rating": average_rating,

            "positive_reviews": positive,

            "neutral_reviews": neutral,

            "negative_reviews": negative,

            "positive_percent":
                round((positive / total_reviews) * 100, 2),

            "neutral_percent":
                round((neutral / total_reviews) * 100, 2),

            "negative_percent":
                round((negative / total_reviews) * 100, 2),
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

        # ==================================================
        # PIE CHART
        # ==================================================

        pie_path = os.path.join(
            self.output_dir,
            f"{company_name}_sentiment_pie.png"
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

            autopct='%1.1f%%'
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

        return chart_paths

    # ======================================================
    # SUMMARY
    # ======================================================

    def _generate_summary(
        self,
        company_name: str,
        analytics: Dict[str, Any],
    ) -> str:

        return f"""
        {company_name} currently maintains an average
        rating of {analytics['average_rating']} based on
        {analytics['total_reviews']} customer reviews.

        Positive customer sentiment stands at
        {analytics['positive_percent']}%.

        The business demonstrates healthy customer
        engagement with opportunities for operational
        optimization and service enhancement.
        """

    # ======================================================
    # RECOMMENDATIONS
    # ======================================================

    def _generate_recommendations(
        self,
        analytics: Dict[str, Any],
    ) -> List[str]:

        recommendations = []

        if analytics["negative_percent"] > 25:

            recommendations.append(
                "Improve customer response time."
            )

            recommendations.append(
                "Enhance staff customer handling training."
            )

        if analytics["average_rating"] < 4:

            recommendations.append(
                "Improve operational quality control."
            )

        if analytics["positive_percent"] > 70:

            recommendations.append(
                "Use positive reviews in marketing campaigns."
            )

        if not recommendations:

            recommendations.append(
                "Maintain current operational standards."
            )

        return recommendations

    # ======================================================
    # ACTION PLAN
    # ======================================================

    def _generate_action_plan(self):

        return [

            {
                "week": "Week 1",
                "task": "Review negative customer feedback."
            },

            {
                "week": "Week 2",
                "task": "Improve customer support workflow."
            },

            {
                "week": "Week 3",
                "task": "Optimize operational bottlenecks."
            },

            {
                "week": "Week 4",
                "task": "Launch customer retention campaigns."
            },
        ]

    # ======================================================
    # PDF BUILDER
    # ======================================================

    def _build_pdf(
        self,
        pdf_path: str,
        company_name: str,
        analytics: Dict[str, Any],
        executive_summary: str,
        recommendations: List[str],
        action_plan,
        chart_paths,
    ):

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
        )

        story = []

        title_style = self.styles['Heading1']
        heading_style = self.styles['Heading2']
        body_style = self.styles['BodyText']

        # ==================================================
        # TITLE
        # ==================================================

        story.append(

            Paragraph(
                f"Executive Report - {company_name}",
                title_style
            )
        )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # DATE
        # ==================================================

        story.append(

            Paragraph(
                f"Generated: {datetime.utcnow()}",
                body_style
            )
        )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # SUMMARY
        # ==================================================

        story.append(
            Paragraph(
                "Executive Summary",
                heading_style
            )
        )

        story.append(
            Paragraph(
                executive_summary,
                body_style
            )
        )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # KPI TABLE
        # ==================================================

        kpi_data = [

            ["Metric", "Value"],

            ["Total Reviews", analytics['total_reviews']],

            ["Average Rating", analytics['average_rating']],

            ["Positive Reviews", analytics['positive_reviews']],

            ["Negative Reviews", analytics['negative_reviews']],
        ]

        table = Table(kpi_data)

        table.setStyle(

            TableStyle([

                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),

                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),

                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ])
        )

        story.append(table)

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # CHART
        # ==================================================

        if os.path.exists(
            chart_paths["pie_chart"]
        ):

            story.append(

                Image(
                    chart_paths["pie_chart"],
                    width=4.5 * inch,
                    height=4.5 * inch,
                )
            )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # RECOMMENDATIONS
        # ==================================================

        story.append(
            Paragraph(
                "Recommendations",
                heading_style
            )
        )

        for rec in recommendations:

            story.append(

                Paragraph(
                    f"• {rec}",
                    body_style
                )
            )

        story.append(
            Spacer(1, 0.3 * inch)
        )

        # ==================================================
        # ACTION PLAN
        # ==================================================

        story.append(
            Paragraph(
                "30-Day Action Plan",
                heading_style
            )
        )

        for item in action_plan:

            story.append(

                Paragraph(
                    f"{item['week']} - {item['task']}",
                    body_style
                )
            )

        doc.build(story)
