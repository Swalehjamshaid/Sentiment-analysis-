<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ReviewSaaS — AI Intelligence Dashboard</title>

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  
  <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc&libraries=places"></script>

  <style>
    :root { --rs-primary: #6366f1; --rs-dark: #0f172a; --rs-bg: #f8fafc; }
    body { background-color: var(--rs-bg); font-family: 'Inter', sans-serif; color: #1e293b; }
    .card { border: none; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
    
    /* AI Branding */
    .ai-card { background: linear-gradient(135deg, #ffffff 0%, #f5f3ff 100%); border-left: 6px solid var(--rs-primary); }
    .health-badge { font-size: 2rem; font-weight: 800; color: var(--rs-primary); }
    .metric-label { font-size: 0.75rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
    
    /* Loader */
    .spinner-overlay { display: none; position: fixed; inset: 0; background: rgba(255,255,255,0.9); z-index: 9999; flex-direction: column; justify-content: center; align-items: center; }
    
    /* Emotion Badges */
    .emotion-tag { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; display: inline-block; margin: 2px; }
    .emotion-joy { background: #dcfce7; color: #15803d; }
    .emotion-anger { background: #fee2e2; color: #b91c1c; }
  </style>
</head>
<body>

<div class="spinner-overlay" id="globalLoader">
    <div class="spinner-border text-primary mb-3"></div>
    <span class="fw-bold" id="loaderText">Running Deep Sentiment Analysis...</span>
</div>

<nav class="navbar navbar-expand-lg navbar-dark bg-dark py-3">
  <div class="container-fluid px-4">
    <a class="navbar-brand fw-bold" href="#">ReviewSaaS AI</a>
    <div class="flex-grow-1 mx-5">
        <input id="placeSearch" type="text" class="form-control bg-light border-0 w-50" placeholder="🔍 Add business via Google Maps...">
    </div>
    <div class="d-flex gap-3">
      <a href="/companies" class="btn btn-outline-light btn-sm px-4">Portfolio</a>
      <a href="/logout" class="btn btn-danger btn-sm px-4">Exit</a>
    </div>
  </div>
</nav>

<div class="container py-4">
  
  <div class="row g-4 mb-4">
    <div class="col-lg-8">
      <div class="card ai-card p-4 h-100">
        <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
                <span class="badge bg-primary mb-2">EXECUTIVE INSIGHT</span>
                <h3 class="fw-bold" id="companyTitle">Business Overview</h3>
            </div>
            <div class="text-end">
                <span class="badge rounded-pill bg-dark px-3 py-2" id="aiConclusion">Awaiting Sync</span>
            </div>
        </div>
        <p class="lead text-secondary" id="aiSummaryText">Connect a company to analyze **Customer Satisfaction Index (CSI)** and **Net Sentiment Score (NSS)**.</p>
        <div id="aiRecommendations" class="mt-3 p-3 bg-white rounded-3 border">
            <h6 class="fw-bold"><i class="me-2">💡</i>AI Recommendations:</h6>
            <ul id="recList" class="small mb-0"><li>No recommendations yet.</li></ul>
        </div>
      </div>
    </div>
    
    <div class="col-lg-4">
      <div class="card p-4 h-100 text-center">
        <div class="metric-label mb-2">Business Health Score</div>
        <div class="health-badge mb-2" id="kpi-health">0%</div>
        <div class="progress" style="height: 10px;">
          <div id="healthBar" class="progress-bar bg-primary" role="progressbar" style="width: 0%"></div>
        </div>
        <div class="mt-4 row g-2">
            <div class="col-6">
                <div class="border rounded p-2">
                    <div class="metric-label">Churn Risk</div>
                    <div class="fw-bold text-danger" id="kpi-churn">0%</div>
                </div>
            </div>
            <div class="col-6">
                <div class="border rounded p-2">
                    <div class="metric-label">Fake Prob.</div>
                    <div class="fw-bold text-warning" id="kpi-fake">0%</div>
                </div>
            </div>
        </div>
      </div>
    </div>
  </div>

  <div class="card p-3 mb-4 shadow-sm">
    <div class="row g-3 align-items-end">
      <div class="col-md-3">
        <label class="metric-label">Company</label>
        <select class="form-select border-0 bg-light" id="companySelect" onchange="switchCompany(this.value)">
          <option value="">-- Select --</option>
          {% for c in companies %}
            <option value="{{c.id}}" {% if active_company_id == c.id %}selected{% endif %}>{{ c.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-5">
        <label class="metric-label">Analysis Period</label>
        <div class="input-group">
          <input type="date" class="form-control border-0 bg-light" id="startDate">
          <input type="date" class="form-control border-0 bg-light" id="endDate">
        </div>
      </div>
      <div class="col-md-2 d-grid">
        <button class="btn btn-primary fw-bold" onclick="fetchAll()">Update</button>
      </div>
      <div class="col-md-2 d-grid">
        <button class="btn btn-success fw-bold" onclick="triggerSync()">Sync Live</button>
      </div>
    </div>
  </div>

  <div class="row g-4 mb-4">
    <div class="col-md-3">
      <div class="card p-3 text-center">
        <div class="metric-label">Total Reviews</div>
        <h3 id="kpi-total" class="fw-bold mb-0">0</h3>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3 text-center">
        <div class="metric-label">Avg Rating</div>
        <h3 id="kpi-rating" class="fw-bold mb-0 text-success">0.0</h3>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3 h-100">
        <div class="metric-label mb-2">Emotion Heatmap (sentiment.py Engine)</div>
        <div id="emotionBox">
            <span class="text-muted small">No data detected.</span>
        </div>
      </div>
    </div>
  </div>

  <div class="row g-4">
    <div class="col-lg-8">
      <div class="card p-4 h-100"><canvas id="chartVolume"></canvas></div>
    </div>
    <div class="col-lg-4">
      <div class="card p-4 h-100"><canvas id="chartDist"></canvas></div>
    </div>
  </div>
</div>

<script>
let activeCompanyId = {{ active_company_id or 'null' }};
let charts = {};

// GOOGLE MAPS AUTOCOMPLETE
function initAutocomplete() {
    const input = document.getElementById('placeSearch');
    const autocomplete = new google.maps.places.Autocomplete(input);
    autocomplete.addListener('place_changed', async () => {
        const place = autocomplete.getPlace();
        if (!place.place_id) return;
        
        showLoader("Adding Business to ReviewSaaS Portfolio...");
        const response = await fetch('/api/companies/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: place.name, place_id: place.place_id, address: place.formatted_address })
        });
        if (response.ok) window.location.reload();
    });
}

// OUTSCRAPER SYNC
async function triggerSync() {
    if (!activeCompanyId) return alert("Select a company.");
    showLoader("Scraping Google Maps via Outscraper...");
    const response = await fetch(`/api/companies/${activeCompanyId}/sync`, { method: 'POST' });
    if (response.ok) {
        alert("Sync Started! Analysis will update shortly.");
        fetchAll();
    }
    hideLoader();
}

// DEEP ANALYSIS FETCH
async function fetchAll() {
    if (!activeCompanyId) return;
    showLoader("Engine: Analyzing Emotions & Calculating Churn Risk...");
    
    const s = document.getElementById('startDate').value;
    const e = document.getElementById('endDate').value;
    const params = `company_id=${activeCompanyId}&start=${s}&end=${e}`;

    try {
        const [kpi, summary, recs, vol, dist] = await Promise.all([
            fetch(`/api/kpis?${params}`).then(r => r.json()),
            fetch(`/api/v2/ai/executive-summary?${params}`).then(r => r.json()),
            fetch(`/api/v2/ai/recommendations?${params}`).then(r => r.json()),
            fetch(`/api/series/reviews?${params}`).then(r => r.json()),
            fetch(`/api/ratings/distribution?${params}`).then(r => r.json())
        ]);

        // KPI Update
        document.getElementById('kpi-total').innerText = kpi.total_reviews;
        document.getElementById('kpi-rating').innerText = kpi.avg_rating.toFixed(1);
        
        // AI Update (sentiment.py metrics)
        document.getElementById('aiSummaryText').innerText = summary.summary;
        document.getElementById('aiConclusion').innerText = summary.conclusion;
        
        // Health/Churn Calculation
        const health = Math.round(((kpi.avg_rating/5)*100));
        document.getElementById('kpi-health').innerText = health + '%';
        document.getElementById('healthBar').style.width = health + '%';
        
        // Populate Recommendations
        const recBox = document.getElementById('recList');
        recBox.innerHTML = recs.top_action_items.map(item => `<li>${item}</li>`).join('');

        renderLineChart('chartVolume', vol.series);
        renderBarChart('chartDist', dist.distribution);
    } catch (err) { console.error(err); }
    hideLoader();
}

function renderLineChart(id, data) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels: data.map(d => d.date), datasets: [{ label: 'Reviews', data: data.map(d => d.value), borderColor: '#6366f1', tension: 0.4 }] }
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

function showLoader(text) {
    document.getElementById('loaderText').innerText = text;
    document.getElementById('globalLoader').style.display = 'flex';
}
function hideLoader() { document.getElementById('globalLoader').style.display = 'none'; }
function switchCompany(id) { activeCompanyId = id; fetchAll(); }

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
