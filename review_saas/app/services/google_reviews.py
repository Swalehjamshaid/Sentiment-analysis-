# fetch_all_gbp_reviews.py
# --------------------------------------------
# Fetch all Google Business Profile reviews (500+)
# for last 1 year, save locally, GitHub, and Railway DB
# --------------------------------------------

from google_auth_oauthlib.flow import InstalledAppFlow
import requests
from datetime import datetime, timedelta
import json
import base64
import psycopg2

# ----------------------------
# 1️⃣ OAuth Setup
# ----------------------------
SCOPES = ["https://www.googleapis.com/auth/business.manage"]
CREDENTIALS_FILE = "client_secret.json"  # your OAuth JSON

flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
creds = flow.run_local_server(port=0)
access_token = creds.token
print("✅ Access Token:", access_token)

headers = {"Authorization": f"Bearer {access_token}"}

# ----------------------------
# 2️⃣ Get accounts
# ----------------------------
accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
response = requests.get(accounts_url, headers=headers)
accounts = response.json()
account_id = accounts['accounts'][0]['name']  # first account
print("✅ Account ID:", account_id)

# ----------------------------
# 3️⃣ Get locations
# ----------------------------
locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_id}/locations"
locations_resp = requests.get(locations_url, headers=headers)
locations = locations_resp.json()
location_id = locations['locations'][0]['name']  # first location
print("✅ Location ID:", location_id)

# ----------------------------
# 4️⃣ Fetch all reviews (500+ possible)
# ----------------------------
reviews = []
page_token = None
one_year_ago = datetime.utcnow() - timedelta(days=365)

while True:
    reviews_url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/reviews"
    if page_token:
        reviews_url += f"?pageToken={page_token}"

    resp = requests.get(reviews_url, headers=headers)
    data = resp.json()

    for r in data.get("reviews", []):
        # filter last 1 year
        review_date = datetime.strptime(r['createTime'][:10], "%Y-%m-%d")
        if review_date >= one_year_ago:
            reviews.append({
                "author": r['reviewer'].get('displayName', 'Unknown'),
                "rating": r.get('starRating', 'Unknown'),
                "comment": r.get('comment', ''),
                "date": r.get('createTime')
            })

    page_token = data.get("nextPageToken")
    if not page_token:
        break

print(f"✅ Total Reviews from last 1 year: {len(reviews)}")

# ----------------------------
# 5️⃣ Save locally as JSON
# ----------------------------
output_file = "reviews_last_year.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(reviews, f, indent=4, ensure_ascii=False)
print(f"✅ Reviews saved locally: {output_file}")

# ----------------------------
# 6️⃣ Push to GitHub (optional)
# ----------------------------
GITHUB_USER = "your_github_username"
REPO_NAME = "google-business-reviews"
FILE_PATH = "reviews_last_year.json"
BRANCH = "main"
GITHUB_TOKEN = "your_github_personal_access_token"

with open(output_file, "r", encoding="utf-8") as f:
    content = f.read()

b64_content = base64.b64encode(content.encode()).decode()
url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{FILE_PATH}"
headers_github = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
response = requests.get(url, headers=headers_github)
sha = response.json()["sha"] if response.status_code == 200 else None

data = {"message": "Update reviews for last year", "content": b64_content, "branch": BRANCH}
if sha:
    data["sha"] = sha

response = requests.put(url, headers=headers_github, data=json.dumps(data))
if response.status_code in [200, 201]:
    print("✅ Reviews pushed to GitHub successfully!")
else:
    print("❌ Failed to push to GitHub:", response.json())

# ----------------------------
# 7️⃣ Save to Railway PostgreSQL
# ----------------------------
DB_HOST = "your_db_host"
DB_PORT = 5432
DB_NAME = "your_db_name"
DB_USER = "your_db_user"
DB_PASSWORD = "your_db_password"

conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    author TEXT,
    rating TEXT,
    comment TEXT,
    date TIMESTAMP
)
""")
conn.commit()

for r in reviews:
    cursor.execute("""
    INSERT INTO reviews (author, rating, comment, date)
    VALUES (%s, %s, %s, %s)
    """, (r["author"], r["rating"], r["comment"], r["date"]))

conn.commit()
cursor.close()
conn.close()
print("✅ Reviews saved to Railway database!")
