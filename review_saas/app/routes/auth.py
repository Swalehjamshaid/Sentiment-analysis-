# filename: app/routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from ..db import db
from ..models import User

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            flash('Logged in', 'success')
            return redirect(url_for('dashboard.dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'warning')
        else:
            user = User(email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            flash('Registered successfully', 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')

@bp.route('/logout')
def logout():
    flash('Logged out', 'info')
    return redirect(url_for('auth.login'))
