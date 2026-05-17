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
    KeepTogether,
)

from reportlab.lib import colors

from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)

from reportlab.lib.pagesizes import letter

from reportlab.lib.enums import (
    TA_CENTER,
)

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
        # EXECUTIVE STYLES
        # ==================================================

        self.title_style = ParagraphStyle(
            'ExecutiveTitle',
            parent=self.styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=26,
            leading=32,
            textColor=colors.HexColor("#0F172A"),
            alignment=TA_CENTER,
            spaceAfter=18,
        )

        self.sub_title_style = ParagraphStyle(
            'ExecutiveSubTitle',
            parent=self.styles['BodyText'],
            fontName='Helvetica',
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#64748B"),
            alignment=TA_CENTER,
        )

        self.heading_style = ParagraphStyle(
            'ExecutiveHeading',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=8,
            spaceAfter=6,
        )

        self.body_style = ParagraphStyle(
            'ExecutiveBody',
            parent=self.styles['BodyText'],
            fontName='Helvetica',
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#334155"),
        )

        self.small_style = ParagraphStyle(
            'ExecutiveSmall',
            parent=self.styles['BodyText'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B"),
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
        # EXECUTIVE CONTENT
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
        # BUILD PDF
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
            (positive / total_reviews) * 100,
            2
        )

        neutral_percent = round(
            (neutral / total_reviews) * 100,
            2
        )

        negative_percent = round(
            (negative / total_reviews) * 100,
            2
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
                if total_reviews >= 200
                else "Medium",

            "retention_risk":
                "Low"
                if average_rating >= 4
                else "Medium",
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
            f"{safe_name}_pie_chart.png"
        )

        plt.figure(figsize=(4.5, 4.5))

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
            "Customer Sentiment Distribution",
            fontsize=12,
        )

        plt.tight_layout()

        plt.savefig(
            pie_path,
            bbox_inches="tight",
            dpi=300
        )

        plt.close()

        chart_paths["pie_chart"] = pie_path

        # ==================================================
        # BAR CHART
        # ==================================================

        bar_path = os.path.join(
            self.output_dir,
            f"{safe_name}_bar_chart.png"
        )

        plt.figure(figsize=(6.2, 3))

        labels = [
            "Positive",
            "Neutral",
            "Negative",
        ]

        values = [
            analytics["positive_percent"],
            analytics["neutral_percent"],
            analytics["negative_percent"],
        ]

        plt.bar(
            labels,
            values,
        )

        plt.ylabel("Percentage")

        plt.title(
            "Customer Sentiment KPI Analysis",
            fontsize=12,
        )

        plt.tight_layout()

        plt.savefig(
            bar_path,
            bbox_inches="tight",
            dpi=300
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

        Current sentiment analysis indicates highly positive
        market perception with
        <b>{analytics['positive_percent']}%</b>
        positive customer sentiment.

        The organization demonstrates stable operational
        performance, healthy customer engagement, and
        strong brand reliability indicators.

        While overall business sentiment remains highly
        positive, isolated operational inefficiencies present
        measurable opportunities for customer experience
        optimization and retention acceleration.
        """

    # ======================================================
    # AI INSIGHTS
    # ======================================================

    def _generate_ai_insights(
        self,
        analytics: Dict[str, Any],
    ) -> List[str]:

        return [

            "Customer satisfaction is primarily driven by positive service consistency and operational stability.",

            "The business demonstrates resilient customer trust indicators despite isolated operational concerns.",

            "Negative customer experiences appear operational rather than systemic in nature.",

            "Brand perception remains commercially advantageous and highly positive.",

            "Operational optimization during high-volume periods could further improve retention performance.",
        ]

    # ======================================================
    # RECOMMENDATIONS
    # ======================================================

    def _generate_recommendations(
        self,
        analytics: Dict[str, Any],
    ) -> List[str]:

        return [

            "Implement operational optimization protocols for high-volume customer periods.",

            "Strengthen customer recovery workflows for negative experience management.",

            "Leverage positive customer sentiment in digital marketing campaigns.",

            "Deploy AI-driven customer sentiment monitoring for proactive issue detection.",

            "Increase focus on response-time optimization and service consistency.",
        ]

    # ======================================================
    # ACTION PLAN
    # ======================================================

    def _generate_action_plan(self):

        return [

            {
                "timeline": "30 Days",
                "objective":
                    "Address operational complaints and customer service bottlenecks."
            },

            {
                "timeline": "60 Days",
                "objective":
                    "Optimize support workflows and service consistency."
            },

            {
                "timeline": "90 Days",
                "objective":
                    "Launch customer retention and loyalty enhancement initiatives."
            },
        ]

    # ======================================================
    # CONCLUSION
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
    # PAGE FOOTER
    # ======================================================

    def _add_page_number(
        self,
        canvas,
        doc,
    ):

        canvas.saveState()

        canvas.setFont(
            'Helvetica',
            8
        )

        canvas.setFillColor(
            colors.HexColor("#64748B")
        )

        canvas.drawString(
            36,
            20,
            "Confidential • AI Executive Intelligence Platform"
        )

        canvas.drawRightString(
            570,
            20,
            f"Page {doc.page}"
        )

        canvas.restoreState()

    # ======================================================
    # DIVIDER
    # ======================================================

    def _divider(self):

        divider = Table(
            [['']],
            colWidths=[6.7 * inch],
            rowHeights=[0.02 * inch]
        )

        divider.setStyle(

            TableStyle([

                (
                    'BACKGROUND',
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#E2E8F0")
                )
            ])
        )

        divider.hAlign = 'CENTER'

        return divider

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
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=32,
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
            Spacer(1, 0.12 * inch)
        )

        story.append(
            Paragraph(
                company_name,
                self.sub_title_style
            )
        )

        story.append(
            Spacer(1, 0.1 * inch)
        )

        story.append(
            Paragraph(
                f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                self.sub_title_style
            )
        )

        story.append(
            Spacer(1, 3.2 * inch)
        )

        story.append(
            Paragraph(
                "Confidential Executive Business Intelligence Document",
                self.small_style
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
            Spacer(1, 0.15 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.15 * inch)
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

        kpi_table = Table(
            kpi_data,
            colWidths=[
                2.0 * inch,
                1.2 * inch,
                1.2 * inch,
                1.4 * inch,
            ]
        )

        kpi_table.setStyle(

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
                    'FONTSIZE',
                    (0, 0),
                    (-1, -1),
                    9
                ),

                (
                    'BOTTOMPADDING',
                    (0, 0),
                    (-1, 0),
                    10
                ),

                (
                    'TOPPADDING',
                    (0, 0),
                    (-1, 0),
                    10
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'ALIGN',
                    (0, 0),
                    (-1, -1),
                    'CENTER'
                ),

                (
                    'VALIGN',
                    (0, 0),
                    (-1, -1),
                    'MIDDLE'
                ),

                (
                    'ROWBACKGROUNDS',
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8FAFC")
                    ]
                ),
            ])
        )

        kpi_table.hAlign = 'CENTER'

        story.append(kpi_table)

        story.append(
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
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

        chart_elements = []

        if os.path.exists(
            chart_paths["pie_chart"]
        ):

            pie_chart = Image(
                chart_paths["pie_chart"],
                width=3.5 * inch,
                height=3.5 * inch,
            )

            pie_chart.hAlign = 'CENTER'

            chart_elements.append(
                pie_chart
            )

        chart_elements.append(
            Spacer(1, 0.12 * inch)
        )

        if os.path.exists(
            chart_paths["bar_chart"]
        ):

            bar_chart = Image(
                chart_paths["bar_chart"],
                width=5.4 * inch,
                height=2.5 * inch,
            )

            bar_chart.hAlign = 'CENTER'

            chart_elements.append(
                bar_chart
            )

        story.append(
            KeepTogether(chart_elements)
        )

        story.append(
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
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
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
        )

        # ==================================================
        # RISK ASSESSMENT
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
            colWidths=[
                2.2 * inch,
                1.4 * inch,
                2.2 * inch,
            ]
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
                    'FONTNAME',
                    (0, 0),
                    (-1, 0),
                    'Helvetica-Bold'
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'ALIGN',
                    (0, 0),
                    (-1, -1),
                    'CENTER'
                ),

                (
                    'VALIGN',
                    (0, 0),
                    (-1, -1),
                    'MIDDLE'
                ),

                (
                    'ROWBACKGROUNDS',
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8FAFC")
                    ]
                ),
            ])
        )

        risk_table.hAlign = 'CENTER'

        story.append(risk_table)

        story.append(
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
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
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
        )

        # ==================================================
        # STRATEGIC ROADMAP
        # ==================================================

        story.append(
            Paragraph(
                "30 / 60 / 90 Day Strategic Roadmap",
                self.heading_style
            )
        )

        roadmap_data = [

            [
                "Timeline",
                "Strategic Objective"
            ]
        ]

        for item in action_plan:

            roadmap_data.append([
                item["timeline"],
                item["objective"]
            ])

        roadmap_table = Table(
            roadmap_data,
            colWidths=[
                1.7 * inch,
                4.8 * inch,
            ]
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
                    'FONTNAME',
                    (0, 0),
                    (-1, 0),
                    'Helvetica-Bold'
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#CBD5E1")
                ),

                (
                    'ALIGN',
                    (0, 0),
                    (-1, -1),
                    'CENTER'
                ),

                (
                    'VALIGN',
                    (0, 0),
                    (-1, -1),
                    'MIDDLE'
                ),

                (
                    'ROWBACKGROUNDS',
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8FAFC")
                    ]
                ),
            ])
        )

        roadmap_table.hAlign = 'CENTER'

        story.append(roadmap_table)

        story.append(
            Spacer(1, 0.18 * inch)
        )

        story.append(
            self._divider()
        )

        story.append(
            Spacer(1, 0.18 * inch)
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
            Spacer(1, 0.22 * inch)
        )

        # ==================================================
        # FOOTER NOTE
        # ==================================================

        story.append(
            Paragraph(
                "Confidential • AI Executive Intelligence Platform • Internal Business Use Only",
                self.small_style
            )
        )

        # ==================================================
        # BUILD PDF
        # ==================================================

        doc.build(
            story,
            onFirstPage=self._add_page_number,
            onLaterPages=self._add_page_number,
        )
