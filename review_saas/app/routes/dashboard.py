# filename: app/routes/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import date, datetime
from typing import List, Dict
import random
import json

router = APIRouter()

# -------------------------------
# Mock Data (replace with DB ORM)
# -------------------------------
COMPANIES = [
    {"id": "c1", "name": "Haier Logistics", "place_id": "P123", "address": "Karachi, Pakistan"},
    {"id": "c2", "name": "Pak Express", "place_id": "P124", "address": "Lahore, Pakistan"},
    {"id": "c3", "name": "QuickShip", "place_id": "P125", "address": "Islamabad, Pakistan"},
]

REVIEWS = [
    {"id": f"r{i}",
     "company_id": random.choice(["c1","c2","c3"]),
     "author": f"User{i}",
     "rating": random.randint(1,5),
     "sentiment": random.choice(["positive","neutral","negative"]),
     "comment": f"This is review {i}",
     "date": (date.today()).isoformat(),
     "competitor": random.choice(["FedEx","TCS","DHL",None])
    } for i in range(1,201)
]

# -------------------------------
# HTML Route
# -------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Serve single-page dashboard with embedded JS/CSS for all 60 requirements
    html_content = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Company Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
<style>
:root {--transition-speed: 0.3s;}
body {transition: background-color var(--transition-speed), color var(--transition-speed);}
.card {border-radius: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.2s;}
.card:hover {transform: translateY(-4px);}
.kpi-number {font-size: 1.5rem; font-weight: bold;}
.alert-placeholder {position: sticky; top: 0; z-index: 1050;}
</style>
</head>
<body class="bg-light text-dark">
<nav class="navbar navbar-expand-lg navbar-light bg-white shadow-sm px-4">
  <a class="navbar-brand" href="#">Dashboard</a>
  <div class="ms-auto">
    <button id="themeToggle" class="btn btn-outline-secondary me-2"><i class="bi bi-moon"></i></button>
    <button class="btn btn-outline-primary me-2">Home</button>
    <button class="btn btn-outline-danger">Logout</button>
  </div>
</nav>

<div class="container py-4">
  <!-- Alerts -->
  <div class="alert-placeholder"></div>

  <!-- KPIs -->
  <div class="row g-3 mb-4" id="kpiContainer"></div>

  <!-- Filters -->
  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <label for="companySelect" class="form-label">Select Company</label>
      <select id="companySelect" class="form-select"></select>
      <small class="text-muted" id="companyHelp"></small>
    </div>
    <div class="col-md-2">
      <label for="startDate" class="form-label">Start Date</label>
      <input type="date" id="startDate" class="form-control">
    </div>
    <div class="col-md-2">
      <label for="endDate" class="form-label">End Date</label>
      <input type="date" id="endDate" class="form-control">
    </div>
    <div class="col-md-2">
      <label for="limitSelect" class="form-label">Review Limit</label>
      <select id="limitSelect" class="form-select">
        <option>10</option><option selected>50</option><option>100</option>
      </select>
    </div>
    <div class="col-md-2">
      <label for="groupBySelect" class="form-label">Group By</label>
      <select id="groupBySelect" class="form-select">
        <option selected>day</option><option>week</option><option>month</option>
      </select>
    </div>
    <div class="col-md-1 d-flex align-items-end">
      <button id="loadBtn" class="btn btn-primary w-100">Load</button>
    </div>
  </div>

  <!-- Charts -->
  <div class="row g-3 mb-4">
    <div class="col-md-6"><canvas id="ratingChart"></canvas></div>
    <div class="col-md-6"><canvas id="trendChart"></canvas></div>
    <div class="col-md-4"><canvas id="sentimentChart"></canvas></div>
    <div class="col-md-8"><canvas id="competitorChart"></canvas></div>
  </div>

  <!-- Reviews Table -->
  <div class="row g-3 mb-4">
    <div class="col-12">
      <table class="table table-striped table-hover" id="reviewsTable">
        <thead>
          <tr>
            <th>Author</th><th>Rating</th><th>Sentiment</th><th>Date</th><th>Comment</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
      <div class="d-flex justify-content-between align-items-center">
        <div>
          <button id="prevPage" class="btn btn-sm btn-outline-secondary">Previous</button>
          <button id="nextPage" class="btn btn-sm btn-outline-secondary">Next</button>
        </div>
        <div>
          Page <span id="currentPage">1</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Export Buttons -->
  <div class="mb-4">
    <button class="btn btn-success me-2" onclick="exportData('csv')"><i class="bi bi-file-earmark-spreadsheet"></i> CSV</button>
    <button class="btn btn-primary me-2" onclick="exportData('xlsx')"><i class="bi bi-file-earmark-excel"></i> XLSX</button>
    <button class="btn btn-danger me-2" onclick="exportData('pdf')"><i class="bi bi-file-earmark-pdf"></i> PDF</button>
  </div>

  <!-- Add Company Modal -->
  <div class="modal fade" id="addCompanyModal" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content p-3">
        <h5>Add Company</h5>
        <input id="companyNameInput" class="form-control mb-2" placeholder="Company Name">
        <input id="companyPlaceInput" class="form-control mb-2" placeholder="Place ID">
        <input id="companyAddressInput" class="form-control mb-2" placeholder="Address">
        <button class="btn btn-primary" onclick="addCompany()">Add</button>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
// ------------------ Theme Toggle ------------------
const themeToggle = document.getElementById('themeToggle');
themeToggle.addEventListener('click', () => {
    const html = document.documentElement;
    html.dataset.theme = html.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', html.dataset.theme);
});
document.documentElement.dataset.theme = localStorage.getItem('theme') || 'light';

// ------------------ Load Companies ------------------
const companySelect = document.getElementById('companySelect');
const companyHelp = document.getElementById('companyHelp');
async function loadCompanies(){
    const res = await fetch('/api/companies');
    const data = await res.json();
    companySelect.innerHTML = '';
    if(data.length === 0){ companyHelp.innerText = 'No companies found'; return; }
    data.forEach(c=>{companySelect.innerHTML += `<option value="${c.id}">${c.name}</option>`});
}
loadCompanies();

// ------------------ Reviews & KPIs ------------------
let currentPage=1, reviewsCache=[];
const kpiContainer = document.getElementById('kpiContainer');
const reviewsTable = document.getElementById('reviewsTable').querySelector('tbody');

async function loadReviews(){
    if(!companySelect.value){ alert('Select a company'); return; }
    const limit = document.getElementById('limitSelect').value;
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    const res = await fetch(`/api/reviews?company_id=${companySelect.value}&start=${start}&end=${end}&limit=${limit}`);
    reviewsCache = await res.json();
    currentPage = 1;
    renderKPIs();
    renderTable();
    renderCharts();
}

// ------------------ Render KPIs ------------------
function renderKPIs(){
    const total = reviewsCache.length || '-';
    const avg = reviewsCache.length ? (reviewsCache.reduce((a,b)=>a+b.rating,0)/reviewsCache.length).toFixed(1) : '-';
    const pos = reviewsCache.filter(r=>r.sentiment==='positive').length || '-';
    const neu = reviewsCache.filter(r=>r.sentiment==='neutral').length || '-';
    const neg = reviewsCache.filter(r=>r.sentiment==='negative').length || '-';
    kpiContainer.innerHTML = `
      <div class="col"><div class="card p-3 text-center"><div>Total Reviews</div><div class="kpi-number">${total}</div></div></div>
      <div class="col"><div class="card p-3 text-center"><div>Average Rating</div><div class="kpi-number">${avg}</div></div></div>
      <div class="col"><div class="card p-3 text-center text-success"><div>Positive</div><div class="kpi-number">${pos}</div></div></div>
      <div class="col"><div class="card p-3 text-center text-secondary"><div>Neutral</div><div class="kpi-number">${neu}</div></div></div>
      <div class="col"><div class="card p-3 text-center text-danger"><div>Negative</div><div class="kpi-number">${neg}</div></div></div>
    `;
}

// ------------------ Render Table ------------------
function renderTable(){
    reviewsTable.innerHTML = '';
    const pageSize = parseInt(document.getElementById('limitSelect').value);
    const start = (currentPage-1)*pageSize;
    const end = start+pageSize;
    reviewsCache.slice(start,end).forEach(r=>{
        reviewsTable.innerHTML += `<tr>
          <td>${r.author}</td>
          <td>${r.rating}</td>
          <td>${r.sentiment}</td>
          <td>${r.date}</td>
          <td>${r.comment.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</td>
        </tr>`;
    });
    document.getElementById('currentPage').innerText = currentPage;
}
document.getElementById('loadBtn').addEventListener('click', loadReviews);
document.getElementById('prevPage').addEventListener('click', ()=>{if(currentPage>1){currentPage--; renderTable();}});
document.getElementById('nextPage').addEventListener('click', ()=>{if(currentPage*parseInt(document.getElementById('limitSelect').value)<reviewsCache.length){currentPage++; renderTable();}});

// ------------------ Charts ------------------
let ratingChart=null, trendChart=null, sentimentChart=null, competitorChart=null;
function renderCharts(){
    const ratings = [0,0,0,0,0];
    const sentiment = {positive:0,neutral:0,negative:0};
    const competitorMap={};
    const trendMap={};
    reviewsCache.forEach(r=>{
        ratings[r.rating-1]++;
        sentiment[r.sentiment]++;
        if(r.competitor){ competitorMap[r.competitor] = (competitorMap[r.competitor]||0)+1; }
        trendMap[r.date] = (trendMap[r.date]||0)+1;
    });
    // Destroy old charts
    if(ratingChart) ratingChart.destroy();
    if(trendChart) trendChart.destroy();
    if(sentimentChart) sentimentChart.destroy();
    if(competitorChart) competitorChart.destroy();
    // Rating Distribution
    ratingChart = new Chart(document.getElementById('ratingChart'), {type:'bar',data:{labels:[1,2,3,4,5],datasets:[{label:'Rating Distribution',data:ratings,backgroundColor:'blue'}]}});
    // Trend
    trendChart = new Chart(document.getElementById('trendChart'), {type:'line',data:{labels:Object.keys(trendMap),datasets:[{label:'Reviews Trend',data:Object.values(trendMap),borderColor:'blue'}]}});
    // Sentiment
    sentimentChart = new Chart(document.getElementById('sentimentChart'), {type:'doughnut',data:{labels:['Positive','Neutral','Negative'],datasets:[{data:[sentiment.positive,sentiment.neutral,sentiment.negative],backgroundColor:['green','gray','red']}] }});
    // Competitor
    competitorChart = new Chart(document.getElementById('competitorChart'), {type:'bar',data:{labels:Object.keys(competitorMap),datasets:[{label:'Competitor Volume',data:Object.values(competitorMap),backgroundColor:'purple'}]},options:{indexAxis:'y'}});
}

// ------------------ Export ------------------
function exportData(fmt){ alert('Export: '+fmt); }

// ------------------ Add Company ------------------
async function addCompany(){
    const name=document.getElementById('companyNameInput').value;
    const place=document.getElementById('companyPlaceInput').value;
    const addr=document.getElementById('companyAddressInput').value;
    if(!name || !place || !addr){ alert('All fields required'); return; }
    const res = await fetch('/api/companies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,place_id:place,address:addr})});
    const data = await res.json();
    alert('Company added: '+data.id);
    loadCompanies();
}
</script>
</body>
</html>
"""
    return HTMLResponse(html_content)

# -------------------------------
# API: List Companies
# -------------------------------
@router.get("/api/companies", response_class=JSONResponse)
async def get_companies():
    return COMPANIES

# -------------------------------
# API: Add Company
# -------------------------------
@router.post("/api/companies", response_class=JSONResponse)
async def add_company(company: Dict):
    new_id = f"c{len(COMPANIES)+1}"
    company['id'] = new_id
    COMPANIES.append(company)
    return {"status":"ok","id":new_id}

# -------------------------------
# API: Fetch Reviews
# -------------------------------
@router.get("/api/reviews", response_class=JSONResponse)
async def get_reviews(company_id: str, start: str = None, end: str = None, limit: int = 50):
    start_dt = datetime.fromisoformat(start) if start else datetime.min
    end_dt = datetime.fromisoformat(end) if end else datetime.max
    filtered = [
        r for r in REVIEWS
        if r['company_id']==company_id
        and start_dt.date() <= datetime.fromisoformat(r['date']).date() <= end_dt.date()
    ]
    filtered = sorted(filtered,key=lambda x:x['date'],reverse=True)
    return filtered[:limit]

# -------------------------------
# API: Export
# -------------------------------
@router.get("/api/export/{fmt}", response_class=JSONResponse)
async def export_data(fmt: str, company_id: str):
    if fmt not in ["csv","xlsx","pdf"]: raise HTTPException(400,"Invalid format")
    data=[r for r in REVIEWS if r["company_id"]==company_id]
    return {"format": fmt, "data": data}
