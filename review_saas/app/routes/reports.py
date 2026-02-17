from fastapi import APIRouter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from pathlib import Path
    from datetime import datetime

    router = APIRouter(prefix="/reports", tags=["reports"])

    @router.post("/pdf")
    def build(company_name: str):
        Path("outputs").mkdir(parents=True, exist_ok=True)
        path = f"outputs/report_{company_name.replace(' ', '_')}.pdf"
        c = canvas.Canvas(path, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, 800, f"Reputation Report — {company_name}")
        c.setFont("Helvetica", 10)
        c.drawString(40, 780, f"Generated: {datetime.utcnow().isoformat()}Z")
        c.showPage(); c.save()
        return {"path": path}