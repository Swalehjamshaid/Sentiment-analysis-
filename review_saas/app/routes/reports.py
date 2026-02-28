from fastapi import APIRouter
    from ..services.pdf_report import build_pdf
    from pathlib import Path

    router = APIRouter(prefix="/reports", tags=["reports"])

    @router.post("/export")
    def export_report(company: str):
        Path("app/data").mkdir(parents=True, exist_ok=True)
        path = f"app/data/report_{company.replace(' ', '_')}.pdf"
        pdf = build_pdf(path, company, {"total_reviews": 0, "avg_rating": 0})
        return {"path": pdf}