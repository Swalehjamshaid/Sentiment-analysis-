# File: app/services/google_reviews.py
# Purpose: Fetch Google Business Profile reviews and save to PostgreSQL
# Author: Updated for Railway Deployment
# Last updated: March 2026

import os
import requests
import psycopg2
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ----------------------------
# 1️⃣ Configuration from env
# ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# ----------------------------
# 2️⃣ Helper: Get headers with refreshed token
# ----------------------------
def get_valid_headers():
    if not REFRESH_TOKEN:
        raise ValueError("GOOGLE_REFRESH_TOKEN is missing in environment variables")
    
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/business.manage"]
    )
    
    try:
        creds.refresh(Request())
    except Exception as e:
        raise RuntimeError(f"Auth Error: Could not refresh token: {e}")
    
    return {"Authorization": f"Bearer {creds.token}"}

# ----------------------------
# 3️⃣ Main function to fetch and save reviews
# ----------------------------
def ingest_company_reviews():
    try:
        headers = get_valid_headers()
    except Exception as e:
        print(f"❌ {e}")
        return
    
    # Get accounts
    try:
        acc_resp = requests.get(
            "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
            headers=headers
        )
        acc_resp.raise_for_status()
        accounts = acc_resp.json().get("accounts", [])
        if not accounts:
            print("❌ No Google Business accounts found")
            return
        
        account_name = accounts[0]["name"]
        print(f"Using account: {account_name}")
        
        # Get first location
        loc_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations?readMask=name,title"
        loc_resp = requests.get(loc_url, headers=headers)
        loc_resp.raise_for_status()
        locations = loc_resp.json().get("locations", [])
        if not locations:
            print("❌ No locations found")
            return
        
        location_name = locations[0]["name"]
        location_title = locations[0].get("title", "Unnamed location")
        print(f"✅ Syncing reviews for: {location_title} ({location_name})")
    
    except Exception as e:
        print(f"❌ Error fetching account/location IDs: {e}")
        return
    
    # Fetch reviews
    all_reviews = []
    page_token = None
    one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

    while True:
        reviews_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{location_name}/reviews"
        params = {"pageSize": 50}
        if page_token:
            params["pageToken"] = page_token
        
        resp = requests.get(reviews_url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"❌ Reviews API Error ({resp.status_code}): {resp.text}")
            break
        
        data = resp.json()
        batch = data.get("reviews", [])
        
        for r in batch:
            review_time = r.get("createTime")
            if review_time and review_time >= one_year_ago:
                all_reviews.append({
                    "author": r.get("reviewer", {}).get("displayName", "Anonymous"),
                    "rating": r.get("starRating", "STAR_RATING_UNSPECIFIED").replace("STAR_RATING_", ""),
                    "comment": r.get("comment", ""),
                    "date": review_time
                })
        
        page_token = data.get("nextPageToken")
        if not page_token or not batch:
            break
    
    print(f"✅ Fetched {len(all_reviews)} reviews from the last 365 days.")
    
    # Save to DB
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
                    date TIMESTAMPTZ,
                    unique_id TEXT UNIQUE NOT NULL
                );
            """)
            
            inserted = 0
            for r in all_reviews:
                uid = f"{r['author']}_{r['date']}"
                rating_value = int(r["rating"]) if r["rating"].isdigit() else None
                cursor.execute("""
                    INSERT INTO reviews (author, rating, comment, date, unique_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (unique_id) DO NOTHING
                """, (r["author"], rating_value, r["comment"], r["date"], uid))
                if cursor.rowcount > 0:
                    inserted += 1
            
            conn.commit()
            print(f"✅ Database sync complete. Inserted/updated {inserted} new reviews.")
        
        except Exception as e:
            print(f"❌ Database Error: {e}")
        
        finally:
            cursor.close()
            conn.close()
    else:
        print("Skipping DB write (no reviews or DATABASE_URL missing).")

# ----------------------------
# 4️⃣ Safe manual test
# ----------------------------
if __name__ == "__main__":
    ingest_company_reviews()
