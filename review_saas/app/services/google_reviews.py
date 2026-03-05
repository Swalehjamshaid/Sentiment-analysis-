import os
import requests
import json
import base64
import psycopg2
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import InstalledAppFlow

# ----------------------------
# 1️⃣ Configuration & OAuth
# ----------------------------
# These will be pulled from your Railway Environment Variables
DATABASE_URL = os.getenv("DATABASE_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = "your_github_username"
REPO_NAME = "google-business-reviews"

SCOPES = ["https://www.googleapis.com/auth/business.manage"]
# This file should match the JSON you shared earlier
CREDENTIALS_FILE = "client_secret.json" 

flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
creds = flow.run_local_server(port=0)
access_token = creds.token
headers = {"Authorization": f"Bearer {access_token}"}

# ----------------------------
# 2️⃣ Get IDs (Accounts & Locations)
# ----------------------------
# Step A: Get Account ID
acc_resp = requests.get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", headers=headers)
account_id = acc_resp.json()['accounts'][0]['name'] 

# Step B: Get Location ID (using the correct v1 businessinformation endpoint)
loc_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_id}/locations?readMask=name,title"
loc_resp = requests.get(loc_url, headers=headers)
location_id = loc_resp.json()['locations'][0]['name'] 

print(f"✅ Syncing: {account_id} | {location_id}")

# ----------------------------
# 3️⃣ Fetch ALL Reviews (Pagination Loop)
# ----------------------------
all_reviews = []
page_token = None
one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

while True:
    # Use the correct v4 reviews endpoint for 'Unlimited' access
    reviews_url = f"https://mybusiness.googleapis.com/v4/{location_id}/reviews"
    params = {"pageSize": 50} # Maximize batch size
    if page_token:
        params["pageToken"] = page_token

    resp = requests.get(reviews_url, headers=headers, params=params)
    data = resp.json()

    if "reviews" not in data:
        break

    for r in data["reviews"]:
        # Parse Google's ISO date format: 2026-03-05T10:00:00Z
        review_date = datetime.fromisoformat(r['createTime'].replace("Z", "+00:00"))
        
        if review_date >= one_year_ago:
            all_reviews.append({
                "author": r['reviewer'].get('displayName', 'Anonymous'),
                "rating": r.get('starRating', 'STAR_RATING_UNSPECIFIED').replace("STAR_RATING_", ""),
                "comment": r.get('comment', ''),
                "date": r.get('createTime')
            })

    page_token = data.get("nextPageToken")
    if not page_token:
        break

print(f"✅ Total Reviews fetched (last 1 year): {len(all_reviews)}")

# ----------------------------
# 4️⃣ Save Locally & Push to GitHub
# ----------------------------
output_file = "reviews_last_year.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_reviews, f, indent=4, ensure_ascii=False)

if GITHUB_TOKEN:
    content_encoded = base64.b64encode(open(output_file, "rb").read()).decode()
    gh_url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{output_file}"
    gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # Get SHA if file exists to update it
    curr = requests.get(gh_url, headers=gh_headers)
    sha = curr.json().get("sha") if curr.status_code == 200 else None
    
    gh_data = {"message": "Update reviews", "content": content_encoded, "branch": "main"}
    if sha: gh_data["sha"] = sha
    
    requests.put(gh_url, headers=gh_headers, data=json.dumps(gh_data))
    print("✅ Pushed to GitHub.")

# ----------------------------
# 5️⃣ Save to Railway PostgreSQL
# ----------------------------
if DATABASE_URL:
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
        # Create a unique ID to prevent duplicates if the script runs twice
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
