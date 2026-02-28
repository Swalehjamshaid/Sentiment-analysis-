# filename: app/routes/auth.py
from flask import Blueprint, request, jsonify, make_response, render_template, redirect, url_for
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from ..db import db
from ..core.config import Settings
from ..models import User, VerificationToken, ResetToken, LoginAttempt
from ..services.security import hash_password, verify_password, validate_password_strength, create_jwt, decode_jwt, new_token
from ..services.email_service import EmailService
from ..utilities.validators import is_valid_email, sanitize_input

bp = Blueprint('auth', __name__)
email_service = EmailService()

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    data = request.form or request.get_json() or {}
    full_name = sanitize_input(data.get('full_name','')).strip()
    email = sanitize_input(data.get('email','')).lower().strip()
    password = data.get('password','')

    if not full_name or len(full_name) < 2:
        return jsonify({'error':'Full name is required'}), 400
    if not is_valid_email(email):
        return jsonify({'error':'Invalid email'}), 400
    if not validate_password_strength(password):
        return jsonify({'error':'Weak password'}), 400

    if User.query.filter(func.lower(User.email)==email).first():
        return jsonify({'error':'Email already registered'}), 409

    user = User(full_name=full_name, email=email, password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()

    # email verification token
    token = new_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=Settings().verify_token_hours)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=expires)
    db.session.add(vt)
    db.session.commit()

    verify_link = url_for('auth.verify_email', token=token, _external=True)
    email_service.send(email, 'Verify your account', f'Click to verify: {verify_link}')

    return jsonify({'status':'registered', 'message':'Verification email sent'})

@bp.route('/verify/<token>')
def verify_email(token):
    vt = VerificationToken.query.filter_by(token=token).first()
    if not vt:
        return render_template('message.html', title='Verification', message='Invalid token'), 400
    if vt.expires_at < datetime.now(timezone.utc):
        return render_template('message.html', title='Verification', message='Token expired'), 400

    user = vt.user
    user.status = 'active'
    db.session.delete(vt)
    db.session.commit()
    return render_template('message.html', title='Verification', message='Account verified. You can login now.')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    data = request.form or request.get_json() or {}
    email = (data.get('email') or '').lower().strip()
    password = data.get('password') or ''
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    user = User.query.filter(func.lower(User.email)==email).first()
    if not user:
        return jsonify({'error':'Invalid credentials'}), 400

    # lockout check
    s = Settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=s.lockout_minutes)
    recent_failed = LoginAttempt.query.filter_by(user_id=user.id, success=False).filter(LoginAttempt.created_at >= cutoff).count()
    if recent_failed >= s.lockout_threshold:
        return jsonify({'error':'Account locked. Try later.'}), 423

    ok = verify_password(password, user.password_hash)
    db.session.add(LoginAttempt(user_id=user.id, success=ok, ip_address=ip))
    db.session.commit()

    if not ok:
        return jsonify({'error':'Invalid credentials'}), 400

    if user.status != 'active':
        return jsonify({'error':'Account not verified or suspended'}), 403

    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    token = create_jwt({'sub': user.id, 'email': user.email})
    resp = make_response(jsonify({'status':'ok'}))
    resp.set_cookie(Settings().jwt_cookie_name, token, httponly=True, samesite='Lax', secure=False)
    return resp

@bp.route('/logout')
def logout():
    resp = make_response(redirect(url_for('auth.login')))
    resp.delete_cookie(Settings().jwt_cookie_name)
    return resp

@bp.route('/password/forgot', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get('email') or '').lower().strip()
    user = User.query.filter(func.lower(User.email)==email).first()
    if not user:
        return jsonify({'status':'ok'})  # do not reveal existence
    token = new_token()
    expires = datetime.now(timezone.utc) + timedelta(minutes=Settings().reset_token_minutes)
    rt = ResetToken(user_id=user.id, token=token, expires_at=expires)
    db.session.add(rt)
    db.session.commit()
    link = url_for('auth.reset_password_form', token=token, _external=True)
    email_service.send(email, 'Password reset', f'Reset your password: {link}')
    return jsonify({'status':'ok'})

@bp.route('/password/reset/<token>', methods=['GET'])
def reset_password_form(token):
    return render_template('reset.html', token=token)

@bp.route('/password/reset/<token>', methods=['POST'])
def reset_password_submit(token):
    data = request.form or request.get_json() or {}
    password = data.get('password','')
    confirm = data.get('confirm','')
    if password != confirm:
        return jsonify({'error':'Passwords do not match'}), 400
    if not validate_password_strength(password):
        return jsonify({'error':'Weak password'}), 400
    rt = ResetToken.query.filter_by(token=token).first()
    if not rt or rt.expires_at < datetime.now(timezone.utc):
        return jsonify({'error':'Invalid or expired token'}), 400
    user = rt.user
    user.password_hash = hash_password(password)
    db.session.delete(rt)
    db.session.commit()
    return jsonify({'status':'reset'})
