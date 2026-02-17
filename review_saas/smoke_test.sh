#!/usr/bin/env bash
    set -euo pipefail

    if [ $# -lt 1 ]; then
      echo "Usage: $0 https://YOUR_DOMAIN"; exit 1
    fi
    BASE_URL="$1"

    echo "== Health =="
    curl -sf "$BASE_URL/health" && echo -e "
"

    EMAIL="user$(date +%s)@example.com"
    PASS="Strong@123"
    NAME="Railway User"
    CITY="Lahore"
    COMP="Railway Cafe"

    echo "== Register =="
    REG_JSON=$(curl -sf -X POST "$BASE_URL/auth/register"       -F "full_name=$NAME"       -F "email=$EMAIL"       -F "password=$PASS")
    echo "$REG_JSON"
    VERIFY_TOKEN=$(echo "$REG_JSON" | python - <<'PY'
import sys, json
print(json.load(sys.stdin).get("verify_token",""))
PY
)

    if [ -z "$VERIFY_TOKEN" ]; then
      echo "No verify_token returned. If SMTP is configured, check email or logs."; exit 1
    fi

    echo "== Verify =="
    curl -sf "$BASE_URL/auth/verify?token=$VERIFY_TOKEN" && echo -e "
"

    echo "== Login =="
    LOGIN_JSON=$(curl -sf -X POST "$BASE_URL/auth/login"       -H "Content-Type: application/json"       -d '{"email":"'$EMAIL'","password":"'$PASS'"}')
    echo "$LOGIN_JSON"
    TOKEN=$(echo "$LOGIN_JSON" | python - <<'PY'
import sys, json
print(json.load(sys.stdin).get("access_token",""))
PY
)
    if [ -z "$TOKEN" ]; then echo "No access token"; exit 1; fi
    AUTH="Authorization: Bearer $TOKEN"

    echo "== Add Company =="
    ADD_JSON=$(curl -sf -X POST "$BASE_URL/companies?name=$(printf %s "$COMP" | sed 's/ /%20/g')&city=$(printf %s "$CITY" | sed 's/ /%20/g')" -H "$AUTH")
    echo "$ADD_JSON"
    CID=$(echo "$ADD_JSON" | python - <<'PY'
import sys, json
print(json.load(sys.stdin).get("id",0))
PY
)
    if [ "$CID" -eq 0 ]; then echo "Company creation failed"; exit 1; fi

    echo "== Fetch Reviews (demo) =="
    curl -sf -X POST "$BASE_URL/reviews/fetch/$CID?count=25" -H "$AUTH" && echo -e "
"

    echo "== KPIs =="
    curl -sf "$BASE_URL/dashboard/kpis" -H "$AUTH" && echo -e "
"

    echo "== Export CSV =="
    curl -sf "$BASE_URL/reports/export/$CID?fmt=csv" && echo -e "
"

    echo "✅ Smoke test finished"