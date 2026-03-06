# File: sync_google_reviews.py
# Fetch Google Business Profile reviews using OAuth refresh token
# and store them in Railway PostgreSQL

import os
import requests
import psycopg2
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# ------------------------------------------------
# Environment variables (Railway)
# ------------------------------------------------
DATABASE_URL   = os.getenv("DATABASE_URL")
CLIENT_ID      = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET  = os.getenv("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN  = os.getenv("GOOGLE_REFRESH_TOKEN")


# ------------------------------------------------
# Refresh Access Token
# ------------------------------------------------
def get_access_token():

    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/business.manage"]
    )

    creds.refresh(Request())

    return creds.token


# ------------------------------------------------
# Get Account + Location
# ------------------------------------------------
def get_account_location(headers):

    acc_resp = requests.get(
        "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
        headers=headers
    )

    acc_resp.raise_for_status()

    accounts = acc_resp.json().get("accounts", [])

    if not accounts:
        raise Exception("No Google Business accounts found")

    account_id = accounts[0]["name"].split("/")[1]

    print("Account ID:", account_id)

    loc_resp = requests.get(
        f"https://mybusinessbusinessinformation.googleapis.com/v1/accounts/{account_id}/locations",
        headers=headers
    )

    loc_resp.raise_for_status()

    locations = loc_resp.json().get("locations", [])

    if not locations:
        raise Exception("No locations found")

    location_id = locations[0]["name"].split("/")[-1]
    location_title = locations[0].get("title")

    print("Location:", location_title)

    return account_id, location_id


# ------------------------------------------------
# Fetch Reviews
# ------------------------------------------------
def fetch_reviews(headers, account_id, location_id):

    all_reviews = []

    page_token = None

    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

    while True:

        url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"

        params = {"pageSize": 50}

        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(url, headers=headers, params=params)

        if resp.status_code != 200:
            print("Reviews API error:", resp.text)
            break

        data = resp.json()

        reviews = data.get("reviews", [])

        for r in reviews:

            date = r.get("createTime")

            if date:

                dt = datetime.fromisoformat(date.replace("Z", "+00:00"))

                if dt >= one_year_ago:

                    rating = r.get("starRating", "STAR_RATING_UNSPECIFIED")

                    rating = rating.replace("STAR_RATING_", "")

                    all_reviews.append({
                        "author": r.get("reviewer", {}).get("displayName", "Anonymous"),
                        "rating": rating,
                        "comment": r.get("comment", ""),
                        "date": date
                    })

        page_token = data.get("nextPageToken")

        if not page_token:
            break

    print("Total Reviews:", len(all_reviews))

    return all_reviews


# ------------------------------------------------
# Save to PostgreSQL
# ------------------------------------------------
def save_reviews(reviews):

    conn = psycopg2.connect(DATABASE_URL)

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS google_reviews (
        id SERIAL PRIMARY KEY,
        author TEXT,
        rating INTEGER,
        comment TEXT,
        date TIMESTAMP,
        unique_id TEXT UNIQUE
    )
    """)

    inserted = 0

    for r in reviews:

        uid = f"{r['author']}_{r['date']}"

        rating = int(r["rating"]) if r["rating"].isdigit() else None

        cur.execute("""
        INSERT INTO google_reviews (author,rating,comment,date,unique_id)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (unique_id) DO NOTHING
        """, (r["author"], rating, r["comment"], r["date"], uid))

        if cur.rowcount > 0:
            inserted += 1

    conn.commit()

    cur.close()
    conn.close()

    print("Inserted reviews:", inserted)


# ------------------------------------------------
# MAIN
# ------------------------------------------------
def main():

    try:

        token = get_access_token()

        headers = {"Authorization": f"Bearer {token}"}

        account_id, location_id = get_account_location(headers)

        reviews = fetch_reviews(headers, account_id, location_id)

        if reviews:
            save_reviews(reviews)

    except Exception as e:

        print("ERROR:", e)


if __name__ == "__main__":
    main()
