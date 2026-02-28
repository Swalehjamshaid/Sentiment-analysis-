# filename: app/models.py
from .db import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    place_id = db.Column(db.String(128))
    address = db.Column(db.String(512))
    phone = db.Column(db.String(64))
    website = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    source = db.Column(db.String(64))
    rating = db.Column(db.Float)
    text = db.Column(db.Text)
    published_at = db.Column(db.DateTime)
    sentiment = db.Column(db.String(32))
