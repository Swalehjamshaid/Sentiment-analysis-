import os
import requests
import json
import psycopg2
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ----------------------------
# 1️⃣ Configuration & Auth
# ----------------------------
# These MUST be in your Railway Variables
DATABASE_URL = os.getenv("DATABASE_URL")
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# The Refresh Token is what makes this run forever without crashing
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

def get_valid_headers():
    """Uses the Refresh Token to get a fresh Access Token automatically."""
    creds = Credentials(
        token=None,  # We let the refresh process handle this
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    
    # Trigger the refresh
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}

if not REFRESH_TOKEN:
    print("❌ ERROR: GOOGLE_REFRESH_TOKEN is missing in Railway Variables.")
    exit(1)

try:
    headers = get_valid_headers()
except Exception as e:
    print(f"❌ Auth Error: Could not refresh token. Check your Secret/ID. {e}")
    exit(1)

# ----------------------------
# 2️⃣ Get IDs (Accounts & Locations)
# ----------------------------
try:
    # Get Account ID
    acc_resp = requests.get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", headers=headers)
    acc_resp.raise_for_status()
    account_id = acc_resp.json()['accounts'][0]['name'] 

    # Get Location ID
    loc_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_id}/locations?readMask=name,title"
    loc_resp = requests.get(loc_url, headers=headers)
    loc_resp.raise_for_status()
    location_id = loc_resp.json()['locations'][0]['name'] 

    print(f"✅ Syncing reviews for: {location_id}")
except Exception as e:
    print(f"❌ Error fetching Google IDs: {e}")
    exit(1)

# ----------------------------
# 3️⃣ Fetch ALL Reviews (Unlimited Pagination)
# ----------------------------
all_reviews = []
page_token = None
one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

while True:
    # The v4 endpoint allows fetching ALL reviews using nextPageToken
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

print(f"✅ Successfully fetched {len(all_reviews)} reviews.")

# ----------------------------
# 4️⃣ Save to Railway PostgreSQL
# ----------------------------
if DATABASE_URL and all_reviews:
    try:
        # Connect using the URL string from Railway
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
            # unique_id prevents duplicate entries if script runs multiple times
            uid = f"{r['author']}_{r['date']}"
            cursor.execute("""
                INSERT INTO reviews (author, rating, comment, date, unique_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (unique_id) DO NOTHING
            """, (r["author"], int(r["rating"]), r["comment"], r["date"], uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database synchronization complete.")
    except Exception as e:
        print(f"❌ Database Error: {e}")
