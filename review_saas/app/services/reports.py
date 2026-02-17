from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from datetime import datetime
    import io, requests
    from ..core.config import settings

    def build_pdf(path: str, company_name: str, kpis: dict, samples: list[dict]):
        c = canvas.Canvas(path, pagesize=A4)
        w, h = A4
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, h-60, f"Reputation Report — {company_name}")
        c.setFont("Helvetica", 10)
        c.drawString(40, h-80, f"Generated: {datetime.utcnow().isoformat()}Z")
        if settings.REPORT_LOGO_URL:
            try:
                img = ImageReader(io.BytesIO(requests.get(settings.REPORT_LOGO_URL, timeout=5).content))
                c.drawImage(img, w-160, h-110, width=120, height=60, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        y = h-120
        for k, v in kpis.items():
            c.drawString(40, y, f"{k}: {v}")
            y -= 14
        y -= 10
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Sample Reviews:"); y -= 16
        c.setFont("Helvetica", 10)
        for rv in samples:
            line = f"- {rv.get('rating','?')}★ {rv.get('sentiment','?')}: {(rv.get('text') or '')[:180]}"
            c.drawString(40, y, line)
            y -= 14
            if y < 80:
                c.showPage(); y = h-80
        c.showPage(); c.save()
        return path