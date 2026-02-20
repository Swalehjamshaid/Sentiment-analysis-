# review_saas/app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter
import re
import openai

# Google API
from google.oauth2 import service_account
from googleapiclient.discovery import build

router = APIRouter(prefix="/reviews", tags=["reviews"])

# =========================
# Google Business API Setup
# =========================
SERVICE_ACCOUNT_FILE = "path_to_your_service_account.json"
SCOPES = ['https://www.googleapis.com/auth/business.manage']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

google_service = build('mybusiness', 'v4', credentials=credentials)

def fetch_google_reviews(place_id: str):
    """Fetch reviews from Google Business Profile API"""
    reviews = []
    try:
        response = google_service.accounts().locations().reviews().list(
            parent=f'locations/{place_id}'
        ).execute()
        for r in response.get("reviews", []):
            reviews.append({
                "review_text": r.get("comment", ""),
                "rating": r.get("starRating", 0),
                "reviewer_name": r.get("reviewer", {}).get("displayName"),
                "review_date": r.get("createTime")
            })
    except Exception as e:
        print(f"Google API fetch error: {e}")
    return reviews

# =========================
# OpenAI API Setup
# =========================
openai.api_key = "YOUR_OPENAI_API_KEY"

def generate_reply(review_text: str, sentiment: str):
    """Generate AI suggested reply based on sentiment"""
    if sentiment == "Positive":
        prompt = f"Write a professional and friendly reply to this positive review: '{review_text}'"
    elif sentiment == "Neutral":
        prompt = f"Write a polite reply to this neutral review: '{review_text}'"
    else:
        prompt = f"Write a professional apology and support offer reply to this negative review: '{review_text}'"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=60
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print(f"OpenAI API error: {e}")
        # fallback simple reply
        if sentiment == "Positive":
            return "Thank you for your feedback!"
        elif sentiment == "Neutral":
            return "Thanks for your review."
        else:
            return "We are sorry to hear this. Please contact support."

# =========================
# Utilities
# =========================
def classify_sentiment(rating: float):
    if rating >= 4:
        return "Positive"
    elif rating == 3:
        return "Neutral"
    else:
        return "Negative"

def extract_keywords(text: str):
    words = re.findall(r'\b\w+\b', text.lower())
    stopwords = set(["the","and","a","of","to","in","is","it","for","on","with","this","that","at","as"])
    return [w for w in words if w not in stopwords and len(w) > 2]

def save_reviews_to_db(company_id: int, reviews: list, db: Session):
    """Save fetched Google reviews to database, avoid duplicates"""
    for r in reviews:
        exists = db.query(Review).filter(
            Review.company_id == company_id,
            Review.review_text == r['review_text']
        ).first()
        if not exists:
            review_obj = Review(
                company_id=company_id,
                review_text=r['review_text'],
                rating=int(r['rating']),
                reviewer_name=r.get('reviewer_name'),
                review_date=r.get('review_date')
            )
            db.add(review_obj)
    db.commit()

# =========================
# API Endpoints
# =========================
@router.get("/")
def list_reviews(db: Session = Depends(get_db)):
    """Return all reviews (raw data)"""
    return db.query(Review).all()


@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, db: Session = Depends(get_db)):
    """Return summary of reviews for a company"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Step 1: Fetch Google reviews and save
    google_reviews = fetch_google_reviews(company.place_id)
    save_reviews_to_db(company_id, google_reviews, db)

    # Step 2: Fetch all reviews from DB
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    if not reviews:
        return {
            "total_reviews": 0,
            "avg_rating": 0,
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "positive_keywords": [],
            "negative_keywords": [],
            "reviews": []
        }

    # Step 3: Compute KPIs
    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 2)
    sentiments = {"Positive": 0, "Neutral": 0, "Negative": 0}
    positive_keywords = []
    negative_keywords = []
    review_list = []

    for r in reviews:
        s = classify_sentiment(r.rating)
        sentiments[s] += 1
        keywords = extract_keywords(r.review_text)
        if s == "Positive":
            positive_keywords.extend(keywords)
        elif s == "Negative":
            negative_keywords.extend(keywords)

        suggested_reply = generate_reply(r.review_text, s)

        review_list.append({
            "id": r.id,
            "review_text": r.review_text,
            "rating": r.rating,
            "reviewer_name": r.reviewer_name,
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": s,
            "suggested_reply": suggested_reply
        })

    top_positive = [k for k, v in Counter(positive_keywords).most_common(5)]
    top_negative = [k for k, v in Counter(negative_keywords).most_common(5)]

    return {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "positive_keywords": top_positive,
        "negative_keywords": top_negative,
        "reviews": review_list
    }
