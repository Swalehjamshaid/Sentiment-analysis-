# filename: app/routes/companies.py
from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import func
from ..db import db
from ..models import Company, User
from ..services.google_client import GoogleClient
from ..utilities.validators import sanitize_input

bp = Blueprint('companies', __name__)

gclient = GoogleClient()

@bp.route('/', methods=['GET'])
def companies_page():
    companies = Company.query.order_by(Company.created_at.desc()).limit(50).all()
    return render_template('companies.html', companies=companies)

@bp.route('/create', methods=['POST'])
def create_company():
    data = request.get_json() or {}
    name = sanitize_input(data.get('name',''))
    place_id = sanitize_input(data.get('place_id',''))
    maps_link = sanitize_input(data.get('maps_link',''))
    city = sanitize_input(data.get('city',''))
    owner_id = data.get('owner_id')

    if not name and not place_id and not maps_link:
        return jsonify({'error':'Provide at least name or place_id or maps_link'}), 400

    if place_id and not gclient.validate_place_id(place_id):
        return jsonify({'error':'Invalid Google Place ID'}), 400

    # Prevent duplicates by owner + name
    q = Company.query.filter(Company.owner_id==owner_id, func.lower(Company.name)==name.lower())
    if q.first():
        return jsonify({'error':'Company already exists for this user'}), 409

    comp = Company(owner_id=owner_id, name=name, place_id=place_id, maps_link=maps_link, city=city)
    db.session.add(comp)
    db.session.commit()
    return jsonify({'status':'ok', 'id': comp.id})

@bp.route('/<int:company_id>', methods=['PATCH'])
def update_company(company_id):
    comp = Company.query.get_or_404(company_id)
    data = request.get_json() or {}
    for f in ['name','city','maps_link','place_id','logo_url','status','address','phone','email','description']:
        if f in data:
            setattr(comp, f, sanitize_input(data.get(f)))
    db.session.commit()
    return jsonify({'status':'updated'})

@bp.route('/<int:company_id>', methods=['DELETE'])
def delete_company(company_id):
    comp = Company.query.get_or_404(company_id)
    db.session.delete(comp)
    db.session.commit()
    return jsonify({'status':'deleted'})

@bp.route('/search')
def search_company():
    term = (request.args.get('q') or '').lower().strip()
    q = Company.query
    if term:
        like = f"%{term}%"
        q = q.filter(
            (func.lower(Company.name).like(like)) |
            (func.lower(Company.city).like(like)) |
            (func.lower(Company.place_id).like(like)) |
            (func.lower(Company.status).like(like))
        )
    items = q.order_by(Company.created_at.desc()).limit(50).all()
    return jsonify([{'id':c.id,'name':c.name,'city':c.city,'status':c.status} for c in items])
