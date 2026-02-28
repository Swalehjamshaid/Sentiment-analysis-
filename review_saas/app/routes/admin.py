# filename: app/routes/admin.py
from flask import Blueprint, jsonify
from ..models import User, Company, Review

bp = Blueprint('admin', __name__)

@bp.route('/admin/health')
def health():
    return jsonify({'status':'healthy'})

@bp.route('/admin/stats')
def stats():
    return jsonify({
        'users': User.query.count(),
        'companies': Company.query.count(),
        'reviews': Review.query.count(),
    })
