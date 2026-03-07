# sentiment.py
# Enterprise Review Intelligence Engine

import numpy as np
import pandas as pd
from datetime import datetime
from collections import Counter, defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import pipeline

# -----------------------------
# AI MODELS
# -----------------------------

sentiment_engine = SentimentIntensityAnalyzer()

emotion_model = pipeline(
    "text-classification",
    model="j-hartmann/emotion-english-distilroberta-base",
    return_all_scores=True
)

summarizer = pipeline(
    "summarization",
    model="facebook/bart-large-cnn"
)

# -----------------------------
# KEYWORD DATABASES
# -----------------------------

complaint_keywords = [
    "refund","bad","terrible","worst",
    "complaint","angry","broken","rude",
    "poor","late","delay"
]

urgency_keywords = [
    "urgent","immediately","asap",
    "emergency","critical","now"
]

churn_keywords = [
    "never again",
    "switching",
    "cancel",
    "leaving",
    "stop using"
]

fake_patterns = [
    "best ever!!!",
    "perfect service!!!",
    "amazing amazing amazing"
]

# -----------------------------
# SENTIMENT ANALYSIS
# -----------------------------

def sentiment_analysis(text):

    score = sentiment_engine.polarity_scores(text)["compound"]

    if score > 0.05:
        label = "positive"
    elif score < -0.05:
        label = "negative"
    else:
        label = "neutral"

    return label, score


# -----------------------------
# EMOTION DETECTION
# -----------------------------

def emotion_detection(text):

    result = emotion_model(text)[0]

    emotion_scores = {r["label"]: r["score"] for r in result}

    dominant = max(emotion_scores, key=emotion_scores.get)

    return dominant, emotion_scores


# -----------------------------
# COMPLAINT DETECTION
# -----------------------------

def detect_complaint(text):

    t = text.lower()

    return any(word in t for word in complaint_keywords)


# -----------------------------
# URGENCY DETECTION
# -----------------------------

def detect_urgency(text):

    t = text.lower()

    return any(word in t for word in urgency_keywords)


# -----------------------------
# CHURN RISK
# -----------------------------

def detect_churn(text):

    t = text.lower()

    return any(word in t for word in churn_keywords)


# -----------------------------
# FAKE REVIEW DETECTION
# -----------------------------

def fake_review_score(text):

    score = 0

    if len(text.split()) < 5:
        score += 0.4

    if text.lower() in fake_patterns:
        score += 0.6

    if text.count("!") > 3:
        score += 0.3

    return min(score,1)


# -----------------------------
# TOPIC MODELING
# -----------------------------

def topic_modeling(texts, n_topics=5):

    vectorizer = TfidfVectorizer(stop_words="english",max_features=2000)

    X = vectorizer.fit_transform(texts)

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=42
    )

    lda.fit(X)

    words = vectorizer.get_feature_names_out()

    topics = []

    for topic in lda.components_:

        topic_words = [
            words[i]
            for i in topic.argsort()[-10:]
        ]

        topics.append(topic_words)

    return topics


# -----------------------------
# REVIEW CLUSTERING
# -----------------------------

def cluster_reviews(texts, k=4):

    vectorizer = TfidfVectorizer(stop_words="english")

    X = vectorizer.fit_transform(texts)

    model = KMeans(n_clusters=k,random_state=42)

    labels = model.fit_predict(X)

    return labels.tolist()


# -----------------------------
# CUSTOMER SATISFACTION INDEX
# -----------------------------

def customer_satisfaction_index(ratings):

    if len(ratings)==0:
        return 0

    return round((sum(ratings)/(len(ratings)*5))*100,2)


# -----------------------------
# NET SENTIMENT SCORE
# -----------------------------

def net_sentiment_score(sentiments):

    total = len(sentiments)

    pos = sentiments.count("positive")
    neg = sentiments.count("negative")

    return round(((pos-neg)/total)*100,2)


# -----------------------------
# BUSINESS HEALTH SCORE
# -----------------------------

def business_health_score(csi,nss,complaint_rate):

    score = (
        csi*0.4 +
        (nss+100)/2*0.4 +
        (1-complaint_rate)*100*0.2
    )

    return round(score,2)


# -----------------------------
# TREND ANALYSIS
# -----------------------------

def sentiment_trend(data):

    df = pd.DataFrame(data)

    df["date"] = pd.to_datetime(df["date"])

    df["month"] = df["date"].dt.to_period("M")

    trend = df.groupby("month")["rating"].mean()

    return trend.astype(float).to_dict()


# -----------------------------
# EXECUTIVE SUMMARY
# -----------------------------

def generate_summary(texts):

    joined = " ".join(texts[:50])

    result = summarizer(
        joined,
        max_length=120,
        min_length=40,
        do_sample=False
    )

    return result[0]["summary_text"]


# -----------------------------
# AI RECOMMENDATIONS
# -----------------------------

def generate_recommendations(metrics):

    rec = []

    if metrics["complaint_rate"] > 0.2:
        rec.append("Improve customer service response time.")

    if metrics["business_health_score"] < 70:
        rec.append("Focus on service recovery and reputation repair.")

    if metrics["net_sentiment"] < 0:
        rec.append("Launch a customer satisfaction initiative.")

    return rec


# -----------------------------
# MAIN ANALYSIS ENGINE
# -----------------------------

def deep_review_analysis(reviews,competitor_rating=None):

    texts = [r["comment"] for r in reviews]
    ratings = [r["rating"] for r in reviews]

    sentiments=[]
    emotions=[]
    complaints=[]
    urgency=[]
    churn=[]
    fake_scores=[]

    emotion_heatmap=defaultdict(int)

    for r in reviews:

        text=r["comment"]

        s,_ = sentiment_analysis(text)
        sentiments.append(s)

        e,_ = emotion_detection(text)
        emotions.append(e)
        emotion_heatmap[e]+=1

        complaints.append(detect_complaint(text))
        urgency.append(detect_urgency(text))
        churn.append(detect_churn(text))
        fake_scores.append(fake_review_score(text))

    sentiment_counts=dict(Counter(sentiments))

    complaint_rate=sum(complaints)/len(complaints)

    csi=customer_satisfaction_index(ratings)

    nss=net_sentiment_score(sentiments)

    health=business_health_score(csi,nss,complaint_rate)

    topics=topic_modeling(texts)

    clusters=cluster_reviews(texts)

    trend=sentiment_trend(reviews)

    summary=generate_summary(texts)

    recommendations=generate_recommendations({
        "complaint_rate":complaint_rate,
        "business_health_score":health,
        "net_sentiment":nss
    })

    benchmarking=None

    if competitor_rating:

        if np.mean(ratings) > competitor_rating:
            benchmarking="Above Market"

        elif np.mean(ratings)==competitor_rating:
            benchmarking="Market Average"

        else:
            benchmarking="Below Market"

    return {

        "executive_summary":summary,

        "metrics":{

            "customer_satisfaction_index":csi,
            "net_sentiment_score":nss,
            "business_health_score":health,
            "complaint_rate":round(complaint_rate*100,2),
            "churn_risk":round(sum(churn)/len(churn)*100,2),
            "fake_review_probability":round(np.mean(fake_scores)*100,2)

        },

        "sentiment_distribution":sentiment_counts,

        "emotion_heatmap":dict(emotion_heatmap),

        "topics":topics,

        "clusters":clusters,

        "trend":trend,

        "competitor_benchmark":benchmarking,

        "recommendations":recommendations,

        "total_reviews":len(reviews),

        "average_rating":round(np.mean(ratings),2)

    }


# -----------------------------
# API ENDPOINT
# -----------------------------

from fastapi import APIRouter

router = APIRouter()

@router.get("/analytics/deep/{company_id}")
def deep_sentiment(company_id:int):

    reviews = fetch_reviews(company_id)

    return deep_review_analysis(reviews,competitor_rating=4.2)


# -----------------------------
# DATABASE MOCK
# -----------------------------

def fetch_reviews(company_id):

    return [

        {
            "comment":"Great service and friendly staff",
            "rating":5,
            "date":"2024-01-05"
        },

        {
            "comment":"Very bad support and rude staff",
            "rating":1,
            "date":"2024-01-10"
        },

        {
            "comment":"Delivery was late but product good",
            "rating":3,
            "date":"2024-02-02"
        },

        {
            "comment":"Excellent quality and fast delivery",
            "rating":5,
            "date":"2024-02-10"
        }

    ]
