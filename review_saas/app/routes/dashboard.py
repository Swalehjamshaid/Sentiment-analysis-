# filename: app/routes/dashboard.py

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Dict, Optional
import random
import io
import csv
import json

router = APIRouter()

# --------------------------------------------------
# Models
# --------------------------------------------------

class Company(BaseModel):
    name: str
    place_id: str
    address: str


class Review(BaseModel):
    id: str
    company_id: str
    author: str
    rating: int
    sentiment: str
    comment: str
    date: str
    competitor: Optional[str]


# --------------------------------------------------
# Mock Data
# --------------------------------------------------

COMPANIES: List[Dict] = [
    {"id": "c1", "name": "Haier Logistics", "place_id": "P123", "address": "Karachi"},
    {"id": "c2", "name": "Pak Express", "place_id": "P124", "address": "Lahore"},
    {"id": "c3", "name": "QuickShip", "place_id": "P125", "address": "Islamabad"},
]

REVIEWS: List[Dict] = [
    {
        "id": f"r{i}",
        "company_id": random.choice(["c1", "c2", "c3"]),
        "author": f"User{i}",
        "rating": random.randint(1, 5),
        "sentiment": random.choice(["positive", "neutral", "negative"]),
        "comment": f"This is review {i}",
        "date": date.today().isoformat(),
        "competitor": random.choice(["FedEx", "TCS", "DHL", None]),
    }
    for i in range(1, 200)
]


# --------------------------------------------------
# HTML DASHBOARD
# --------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):

    html = """
<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Company Review Dashboard</title>

<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

body{background:#f7f7f7}

.card{border-radius:10px}

.kpi{font-size:20px;font-weight:bold}

</style>

</head>

<body>

<nav class="navbar navbar-dark bg-dark px-4">
<span class="navbar-brand">Review Analytics Dashboard</span>
</nav>


<div class="container mt-4">

<div class="row mb-3">

<div class="col-md-3">
<select id="companySelect" class="form-select"></select>
</div>

<div class="col-md-2">
<input type="date" id="startDate" class="form-control">
</div>

<div class="col-md-2">
<input type="date" id="endDate" class="form-control">
</div>

<div class="col-md-2">
<select id="limitSelect" class="form-select">
<option>10</option>
<option selected>50</option>
<option>100</option>
</select>
</div>

<div class="col-md-2">
<select id="groupSelect" class="form-select">
<option value="day">Day</option>
<option value="week">Week</option>
<option value="month">Month</option>
</select>
</div>

<div class="col-md-1">
<button onclick="loadReviews()" class="btn btn-primary w-100">Load</button>
</div>

</div>


<div class="row" id="kpis"></div>


<div class="row mt-4">

<div class="col-md-6">
<canvas id="ratingChart"></canvas>
</div>

<div class="col-md-6">
<canvas id="trendChart"></canvas>
</div>

</div>


<div class="row mt-4">

<div class="col-md-4">
<canvas id="sentimentChart"></canvas>
</div>

<div class="col-md-8">
<canvas id="competitorChart"></canvas>
</div>

</div>


<div class="mt-4">

<table class="table table-striped">

<thead>
<tr>
<th>Author</th>
<th>Rating</th>
<th>Sentiment</th>
<th>Date</th>
<th>Comment</th>
</tr>
</thead>

<tbody id="reviewTable"></tbody>

</table>

</div>


<div class="mt-3">

<button class="btn btn-success" onclick="exportData('csv')">CSV</button>
<button class="btn btn-primary" onclick="exportData('xlsx')">XLSX</button>
<button class="btn btn-danger" onclick="exportData('pdf')">PDF</button>

</div>


</div>


<script>

let reviews=[]

async function loadCompanies(){

const r=await fetch('/api/companies')
const data=await r.json()

let select=document.getElementById("companySelect")

select.innerHTML=""

data.forEach(c=>{

let opt=document.createElement("option")

opt.value=c.id
opt.innerText=c.name

select.appendChild(opt)

})

}

loadCompanies()



async function loadReviews(){

const company=document.getElementById("companySelect").value

const start=document.getElementById("startDate").value

const end=document.getElementById("endDate").value

const limit=document.getElementById("limitSelect").value

const group=document.getElementById("groupSelect").value


const r=await fetch(`/api/reviews?company_id=${company}&start=${start}&end=${end}&limit=${limit}&group=${group}`)

reviews=await r.json()

renderTable()

renderCharts()

renderKPI()

}



function renderTable(){

let table=document.getElementById("reviewTable")

table.innerHTML=""

reviews.data.forEach(r=>{

table.innerHTML+=`<tr>

<td>${r.author}</td>
<td>${r.rating}</td>
<td>${r.sentiment}</td>
<td>${r.date}</td>
<td>${r.comment.replace(/</g,"&lt;")}</td>

</tr>`

})

}



function renderKPI(){

let kpi=document.getElementById("kpis")

kpi.innerHTML=`

<div class="col-md-3">
<div class="card p-3">
Total Reviews
<div class="kpi">${reviews.total}</div>
</div>
</div>

<div class="col-md-3">
<div class="card p-3">
Average Rating
<div class="kpi">${reviews.avg_rating}</div>
</div>
</div>

`

}



function renderCharts(){

let ratings=[0,0,0,0,0]

let sentiment={positive:0,neutral:0,negative:0}

let competitor={}

reviews.data.forEach(r=>{

ratings[r.rating-1]++

sentiment[r.sentiment]++

if(r.competitor){

competitor[r.competitor]=(competitor[r.competitor]||0)+1

}

})


new Chart(document.getElementById("ratingChart"),{

type:"bar",

data:{labels:[1,2,3,4,5],datasets:[{data:ratings}]}

})


new Chart(document.getElementById("sentimentChart"),{

type:"doughnut",

data:{labels:["Positive","Neutral","Negative"],datasets:[{data:[sentiment.positive,sentiment.neutral,sentiment.negative]}]}

})


}



function exportData(type){

const company=document.getElementById("companySelect").value

window.location=`/api/export/${type}?company_id=${company}`

}

</script>


</body>
</html>
"""

    return HTMLResponse(html)


# --------------------------------------------------
# API ROUTES
# --------------------------------------------------

@router.get("/api/companies")
async def get_companies():
    return COMPANIES


@router.post("/api/companies")
async def add_company(company: Company):

    new_id = f"c{len(COMPANIES)+1}"

    obj = company.dict()

    obj["id"] = new_id

    COMPANIES.append(obj)

    return {"status": "created", "id": new_id}


@router.get("/api/reviews")
async def get_reviews(
    company_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    group: str = Query("day")
):

    start_dt = datetime.fromisoformat(start) if start else datetime.min
    end_dt = datetime.fromisoformat(end) if end else datetime.max

    data = [

        r for r in REVIEWS

        if r["company_id"] == company_id

        and start_dt.date() <= datetime.fromisoformat(r["date"]).date() <= end_dt.date()

    ]

    total = len(data)

    avg = round(sum(r["rating"] for r in data) / total, 2) if total else 0

    return {

        "total": total,

        "avg_rating": avg,

        "data": data[:limit]

    }


@router.get("/api/export/{fmt}")
async def export_data(fmt: str, company_id: str):

    data = [r for r in REVIEWS if r["company_id"] == company_id]

    if fmt == "csv":

        buffer = io.StringIO()

        writer = csv.DictWriter(buffer, fieldnames=data[0].keys())

        writer.writeheader()

        writer.writerows(data)

        buffer.seek(0)

        return StreamingResponse(buffer, media_type="text/csv")

    if fmt == "xlsx" or fmt == "pdf":

        return JSONResponse({"message": f"{fmt} export placeholder", "records": len(data)})

    raise HTTPException(400, "Invalid format")
