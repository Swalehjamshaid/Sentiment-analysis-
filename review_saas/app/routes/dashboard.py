<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ReviewSaaS Intelligence Dashboard</title>

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  
  <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc&libraries=places"></script>

  <style>
    :root { --rs-primary: #0d6efd; --rs-dark: #1e293b; --rs-bg: #f8fafc; }
    body { background-color: var(--rs-bg); font-family: 'Inter', sans-serif; color: #334155; }
    .card { border: none; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
    .ai-badge { background: linear-gradient(45deg, #6366f1, #a855f7); color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
    .spinner-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.8); z-index: 9999; justify-content: center; align-items: center; flex-direction: column; }
    .star-rating { color: #facc15; }
  </style>
</head>
<body>

<div class="spinner-overlay" id="globalLoader">
    <div class="spinner-border text-primary mb-3"></div>
    <span class="fw-bold" id="loaderText">Processing Intelligence Engine...</span>
</div>

<nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm py-3">
  <div class="container-fluid px-4">
    <a class="navbar-brand fw-bold" href="/dashboard">ReviewSaaS</a>
    
    <div class="flex-grow-1 mx-lg-5">
        <input id="placeSearch" type="text" class="form-control bg-light border-0 w-75" placeholder="🔍 Search and Add New Company from Google Maps...">
    </div>

    <div class="d-flex gap-2">
      <a href="/companies" class="btn btn-outline-light btn-sm">Manage List</a>
      <a href="/logout" class="btn btn-danger btn-sm">Logout</a>
    </div>
  </div>
</nav>

<div class="container py-4">
  
  <div class="row mb-4">
    <div class="col-12">
      <div class="card p-4 border-start border-primary border-5 shadow-sm">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="ai-badge">AI EXECUTIVE SUMMARY</span>
            <span class="badge bg-primary px-3" id="aiConclusion">Awaiting Data</span>
        </div>
        <p class="mb-0 fw-medium" id="aiSummaryText">Select a company and click "Sync Live Data" to fetch reviews via Outscraper.</p>
      </div>
    </div>
  </div>

  <div class="card p-4 mb-4 shadow-sm">
    <div class="row g-3 align-items-end">
      <div class="col-lg-3">
        <label class="form-label fw-bold small text-muted">ACTIVE COMPANY</label>
        <select class="form-select border-0 bg-light" id="companySelect" onchange="switchCompany(this.value)">
          <option value="">-- Choose Company --</option>
          {% for c in companies %}
            <option value="{{c.id}}" {% if active_company_id == c.id %}selected{% endif %}>{{ c.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="col-lg-4">
        <label class="form-label fw-bold small text-muted">DATE RANGE</label>
        <div class="input-group">
          <input type="date" class="form-control border-0 bg-light" id="startDate">
          <input type="date" class="form-control border-0 bg-light" id="endDate">
        </div>
      </div>
      <div class="col-lg-2 d-grid">
        <button class="btn btn-primary fw-bold" onclick="fetchAll()">Update</button>
      </div>
      <div class="col-lg-3 d-grid">
        <button class="btn btn-success fw-bold" id="syncBtn" onclick="triggerSync()">Sync Live Data</button>
      </div>
    </div>
  </div>

  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <div class="card p-3 text-center shadow-sm">
        <div class="text-muted small fw-bold text-uppercase">Total Reviews</div>
        <h3 id="kpi-total" class="fw-bold mb-0">0</h3>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3 text-center shadow-sm">
        <div class="text-muted small fw-bold text-uppercase">Avg Rating</div>
        <h3 id="kpi-rating" class="fw-bold mb-0 text-success">0.0</h3>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3 text-center shadow-sm">
        <div class="text-muted small fw-bold text-uppercase">Sentiment</div>
        <h3 id="kpi-sent" class="fw-bold mb-0 text-info">0.000</h3>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3 text-center shadow-sm bg-dark text-white">
        <div class="text-white-50 small fw-bold text-uppercase">Business Health</div>
        <h3 id="kpi-health" class="fw-bold mb-0">0%</h3>
      </div>
    </div>
  </div>

  <div class="row g-4 mb-4">
    <div class="col-lg-8">
      <div class="card p-4 h-100 shadow-sm">
        <h6 class="fw-bold text-muted mb-3">Review Volume Trend</h6>
        <canvas id="chartVolume"></canvas>
      </div>
    </div>
    <div class="col-lg-4">
      <div class="card p-4 h-100 shadow-sm">
        <h6 class="fw-bold text-muted mb-3">Rating Distribution</h6>
        <canvas id="chartDist"></canvas>
      </div>
    </div>
  </div>

  <div class="card p-4 shadow-sm mb-5">
    <h6 class="fw-bold text-muted mb-3">Recent Review Feed</h6>
    <div id="reviewsList">
        <p class="text-center text-muted py-4">No data to display. Please click Sync.</p>
    </div>
  </div>
</div>

<script>
let activeCompanyId = {{ active_company_id or 'null' }};
let charts = {};

// 1. ADD NEW COMPANY (Links to Search API)
function initAutocomplete() {
    const input = document.getElementById('placeSearch');
    const autocomplete = new google.maps.places.Autocomplete(input);
    autocomplete.addListener('place_changed', async () => {
        const place = autocomplete.getPlace();
        if (!place.place_id) return;
        
        showLoader("Saving Company to Database...");
        const response = await fetch('/api/companies/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: place.name, place_id: place.place_id, address: place.formatted_address })
        });
        if (response.ok) window.location.reload();
    });
}

// 2. TRIGGER SYNC (Links to your Python ingest_company_reviews logic)
async function triggerSync() {
    if (!activeCompanyId) { alert("Please select a company from the dropdown."); return; }
    showLoader("Syncing Reviews from Outscraper... Please wait.");
    
    // Calls the endpoint in your routes/companies.py
    const response = await fetch(`/api/companies/${activeCompanyId}/sync`, { method: 'POST' });
    if (response.ok) {
        alert("Review synchronization started in background!");
        setTimeout(fetchAll, 2000); // Delay slightly to allow DB writes
    } else {
        alert("Failed to start sync.");
    }
    hideLoader();
}

// 3. FETCH DASHBOARD DATA
async function fetchAll() {
    if (!activeCompanyId) return;
    showLoader("Analyzing Sentiment & Trends...");
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    const params = `company_id=${activeCompanyId}&start=${start}&end=${end}`;

    try {
        const [kpi, summary, vol, dist, reviews] = await Promise.all([
            fetch(`/api/kpis?${params}`).then(r => r.json()),
            fetch(`/api/v2/ai/executive-summary?${params}`).then(r => r.json()),
            fetch(`/api/series/reviews?${params}`).then(r => r.json()),
            fetch(`/api/ratings/distribution?${params}`).then(r => r.json()),
            fetch(`/api/reviews/list?${params}`).then(r => r.json())
        ]);

        // Updates
        document.getElementById('kpi-total').innerText = kpi.total_reviews;
        document.getElementById('kpi-rating').innerText = kpi.avg_rating.toFixed(1);
        document.getElementById('kpi-sent').innerText = kpi.avg_sentiment.toFixed(3);
        document.getElementById('aiSummaryText').innerText = summary.summary;
        document.getElementById('aiConclusion').innerText = summary.conclusion;
        
        // Calculate health from your sentiment engine logic
        const health = ((kpi.avg_rating/5)*50) + (((kpi.avg_sentiment+1)/2)*50);
        document.getElementById('kpi-health').innerText = Math.round(health) + '%';

        renderLineChart('chartVolume', vol.series);
        renderBarChart('chartDist', dist.distribution);
        renderFeed(reviews.items);
    } catch (e) { console.error("Fetch Error:", e); }
    hideLoader();
}

function renderLineChart(id, data) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels: data.map(d => d.date), datasets: [{ label: 'Reviews/Day', data: data.map(d => d.value), borderColor: '#0d6efd', fill: true, backgroundColor: 'rgba(13, 110, 253, 0.1)', tension: 0.3 }] }
    });
}

function renderBarChart(id, dist) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
        type: 'bar',
        data: { labels: ['1★','2★','3★','4★','5★'], datasets: [{ data: Object.values(dist), backgroundColor: ['#ef4444','#f97316','#facc15','#3b82f6','#22c55e'] }] },
        options: { plugins: { legend: { display: false } } }
    });
}

function renderFeed(items) {
    const box = document.getElementById('reviewsList');
    if (!items.length) { box.innerHTML = '<p class="text-center text-muted py-4">No reviews found.</p>'; return; }
    box.innerHTML = items.map(r => `
        <div class="border-bottom py-3">
            <div class="d-flex justify-content-between small text-muted mb-1">
                <span class="fw-bold text-dark">${r.author_name}</span>
                <span>${r.review_time}</span>
            </div>
            <div class="star-rating mb-1">${'★'.repeat(Math.round(r.rating))}${'☆'.repeat(5-Math.round(r.rating))}</div>
            <p class="small mb-0 text-secondary">${r.text}</p>
        </div>
    `).join('');
}

function showLoader(text) {
    document.getElementById('loaderText').innerText = text;
    document.getElementById('globalLoader').style.display = 'flex';
}
function hideLoader() { document.getElementById('globalLoader').style.display = 'none'; }
function switchCompany(id) { 
    if(!id) return;
    const url = new URL(window.location);
    url.searchParams.set('company_id', id);
    window.location.href = url.href; 
}

window.onload = () => {
    initAutocomplete();
    const now = new Date().toISOString().split('T')[0];
    document.getElementById('endDate').value = now;
    document.getElementById('startDate').value = new Date(Date.now() - 30*86400000).toISOString().split('T')[0];
    if (activeCompanyId) fetchAll();
};
</script>
</body>
</html>
