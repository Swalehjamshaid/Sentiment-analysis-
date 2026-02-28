# filename: app/routes/reports.py
from flask import Blueprint, jsonify
from ..models import Company, Review
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file

bp = Blueprint('reports', __name__)

@bp.route('/reports/pdf/<int:company_id>')
def generate_pdf(company_id):
    comp = Company.query.get_or_404(company_id)
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 800, f"Report for {comp.name}")
    c.setFont("Helvetica", 11)
    c.drawString(72, 780, f"City: {comp.city or '-'} | Status: {comp.status}")
    c.drawString(72, 765, f"Total reviews: {len(comp.reviews)}")
    c.showPage()
    c.save()
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=f"report_{company_id}.pdf")
