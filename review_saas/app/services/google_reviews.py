# filename: fetch_all_gbp_reviews.py

import os
import requests
import json
import base64
import psycopg2
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow

# ----------------------------
# 1️⃣ Configuration & OAuth Setup
# ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = "your_github_username"
REPO_NAME = "google-business-reviews"

# Build the client config from Railway Variables (Fixes FileNotFoundError)
GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "project_id": "gen-lang-client-0385070865",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
    }
}

SCOPES = ["https://www.googleapis.com/auth/business.manage"]

# Note: On a server, you typically use a pre-stored Refresh Token. 
# For this script to run automatically, ensure you provide a valid Access Token 
# or use the OAuth flow to generate one.
# For now, we will assume you are passing an access_token via environment variable
# or handling the redirect flow.
access_token = os.getenv("GOOGLE_ACCESS_TOKEN") 

if not access_token:
    print("❌ ERROR: GOOGLE_ACCESS_TOKEN variable is missing in Railway.")
    # Exit or implement token refresh logic here
    exit(1)

headers = {"Authorization": f"Bearer {access_token}"}

# ----------------------------
# 2️⃣ Get IDs (Accounts & Locations)
# ----------------------------
try:
    acc_resp = requests.get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", headers=headers)
    acc_resp.raise_for_status()
    account_id = acc_resp.json()['accounts'][0]['name'] 

    loc_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_id}/locations?readMask=name,title"
    loc_resp = requests.get(loc_url, headers=headers)
    loc_resp.raise_for_status()
    location_id = loc_resp.json()['locations'][0]['name'] 

    print(f"✅ Syncing: {account_id} | {location_id}")
except Exception as e:
    print(f"❌ Error fetching IDs: {e}")
    exit(1)

# ----------------------------
# 3️⃣ Fetch ALL Reviews (Unlimited Pagination)
# ----------------------------
all_reviews = []
page_token = None
one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

while True:
    reviews_url = f"https://mybusiness.googleapis.com/v4/{location_id}/reviews"
    params = {"pageSize": 50} 
    if page_token:
        params["pageToken"] = page_token

    resp = requests.get(reviews_url, headers=headers, params=params)
    if resp.status_code != 200:
        print(f"❌ API Error: {resp.text}")
        break
        
    data = resp.json()
    batch = data.get("reviews", [])

    for r in batch:
        review_date = datetime.fromisoformat(r['createTime'].replace("Z", "+00:00"))
        if review_date >= one_year_ago:
            all_reviews.append({
                "author": r['reviewer'].get('displayName', 'Anonymous'),
                "rating": r.get('starRating', 'STAR_RATING_0').replace("STAR_RATING_", ""),
                "comment": r.get('comment', ''),
                "date": r.get('createTime')
            })

    page_token = data.get("nextPageToken")
    if not page_token or not batch:
        break

print(f"✅ Total Reviews fetched: {len(all_reviews)}")

# ----------------------------
# 4️⃣ Save to Database
# ----------------------------
if DATABASE_URL and all_reviews:
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                author TEXT,
                rating INTEGER,
                comment TEXT,
                date TIMESTAMP,
                unique_id TEXT UNIQUE
            )
        """)
        
        for r in all_reviews:
            uid = f"{r['author']}_{r['date']}"
            cursor.execute("""
                INSERT INTO reviews (author, rating, comment, date, unique_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (unique_id) DO NOTHING
            """, (r["author"], int(r["rating"]), r["comment"], r["date"], uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database Sync Complete.")
    except Exception as e:
        print(f"❌ DB Error: {e}")
