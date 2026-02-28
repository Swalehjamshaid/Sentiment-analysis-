# filename: app/routes/companies.py
from flask import Blueprint, request, jsonify
from ..db import db
from ..models import Company

bp = Blueprint('companies', __name__, url_prefix='/companies')

@bp.route('/create', methods=['POST'])
def create_company():
    data = request.get_json() or {}
    company = Company(
        name=data.get('name',''),
        place_id=data.get('place_id'),
        address=data.get('address'),
        phone=data.get('phone'),
        website=data.get('website'),
    )
    db.session.add(company)
    db.session.commit()
    return jsonify({'status': 'ok', 'id': company.id})
