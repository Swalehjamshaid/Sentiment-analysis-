<!--
  FILE: review_saas/app/templates/dashbord.html
  Purpose: Unified Dashboard (Companies + Reviews) aligned with app/routes/companies.py and app/routes/reviews.py
  Includes:
    - Company directory (list/search/sort/pagination-lite) via /api/companies
    - Create company with Google Places Autocomplete (/api/companies/autocomplete) + enrichment (POST /api/companies)
    - Review intelligence for selected company: summary cards + trend/sentiment charts (/api/reviews/summary/{id})
    - Reviews table with filters (from /api/reviews/list/{id}) and quick company reviews view (/api/companies/{id}/reviews)
    - Google Places panel (autocomplete/text search/details/import) via /api/reviews/google/* and import
    - Diagnostics (/api/reviews/diagnostics)
    - Sync buttons: Quick (companies) & Deep (reviews) sync
    - Dark/Light theme toggle; persisted API token, company, filters, sessiontoken
-->
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ReviewSaaS | Unified Dashboard</title>
  <meta name="theme-color" content="#0b1220" />

  <!-- Bootstrap 5.3 -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

  <!-- Chart.js v4 -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>

  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
    body { font-family: 'Plus Jakarta Sans', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    .glass { background: rgba(15,23,42,.5); backdrop-filter: blur(10px); border: 1px solid rgba(148,163,184,.18); border-radius: 1rem; }
    [data-bs-theme="light"] .glass { background: rgba(255,255,255,.7); border-color: rgba(15,23,42,.12); }
    .chip { display:inline-flex; align-items:center; gap:.35rem; padding:.35rem .6rem; border-radius:999px; font-size:.7rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; border:1px solid transparent; }
    .chip-ok { background: rgba(16,185,129,.14); color:#10b981; border-color: rgba(16,185,129,.35); }
    .chip-bad{ background: rgba(239,68,68,.14); color:#ef4444; border-color: rgba(239,68,68,.35); }
    .chip-warn{ background: rgba(245,158,11,.14); color:#f59e0b; border-color: rgba(245,158,11,.35); }
    .btn-icon { display:inline-flex; align-items:center; justify-content:center; width:40px; height:38px; border-radius:.5rem; border:1px solid rgba(148,163,184,.18); background:transparent; }
    .btn-icon:hover{ background: rgba(148,163,184,.12); }
    .truncate-2 { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .table-fixed { table-layout: fixed; }
    .sidebar-card { position: sticky; top: 84px; }
  </style>
</head>
<body class="bg-body-tertiary">
  <!-- Header -->
  <header class="border-bottom sticky-top" style="backdrop-filter: blur(6px);">
    <nav class="navbar navbar-expand-lg container py-2">
      <a class="navbar-brand d-flex align-items-center gap-2" href="#">
        <span class="bg-primary-subtle rounded-3 p-2 d-inline-flex" style="box-shadow:0 6px 18px rgba(59,130,246,.25);">
          <i data-lucide="shield-check" class="text-primary" aria-hidden="true"></i>
        </span>
        <span class="fw-extrabold fs-4">Review<span class="text-primary">SaaS</span></span>
      </a>
      <div class="ms-auto d-flex align-items-center gap-2">
        <div class="input-group input-group-sm" style="width: 240px;">
          <span class="input-group-text bg-transparent">Company</span>
          <input type="number" min="1" id="companyId" class="form-control" placeholder="ID" aria-label="Company ID" />
        </div>
        <div class="input-group input-group-sm" style="width: 280px;">
          <span class="input-group-text bg-transparent">API Token</span>
          <input type="password" id="apiToken" class="form-control" placeholder="optional" aria-label="API Token" />
          <button id="saveToken" class="btn btn-outline-secondary">Save</button>
        </div>
        <button id="themeToggle" class="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" type="button" aria-label="Toggle theme">
          <i data-lucide="moon-star" class="me-1" aria-hidden="true"></i><span class="d-none d-md-inline">Theme</span>
        </button>
      </div>
    </nav>
  </header>

  <main class="container py-4 py-md-5">
    <div class="row g-4">
      <!-- Left: Companies Sidebar -->
      <aside class="col-lg-4">
        <!-- Companies directory -->
        <section class="glass p-3 p-md-4 sidebar-card mb-4">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <h6 class="mb-0">Companies</h6>
            <div class="input-group input-group-sm" style="max-width: 180px;">
              <span class="input-group-text bg-transparent"><i data-lucide="search"></i></span>
              <input id="coSearch" class="form-control" placeholder="Search"/>
            </div>
          </div>
          <div class="d-flex gap-2 mb-2">
            <select id="coSort" class="form-select form-select-sm" style="max-width: 180px;">
              <option value="created_at" selected>Sort: Created</option>
              <option value="name">Sort: Name</option>
              <option value="city">Sort: City</option>
              <option value="status">Sort: Status</option>
            </select>
            <select id="coOrder" class="form-select form-select-sm" style="max-width: 120px;">
              <option value="desc" selected>Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>
          <div class="d-flex gap-2 mb-2">
            <button id="coPrev" class="btn btn-outline-secondary btn-sm" disabled><i data-lucide="chevron-left"></i></button>
            <button id="coNext" class="btn btn-outline-secondary btn-sm">Next</button>
            <span id="coPageLbl" class="small text-secondary ms-auto">Page 1</span>
          </div>
          <div id="coList" class="list-group small" style="max-height: 360px; overflow:auto;"></div>
        </section>

        <!-- Create company with Google Autocomplete -->
        <section class="glass p-3 p-md-4 sidebar-card">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <h6 class="mb-0">Add Company</h6>
            <div class="input-group input-group-sm" style="max-width: 160px;">
              <span class="input-group-text bg-transparent">Lang</span>
              <input id="gLang" class="form-control" placeholder="en"/>
            </div>
          </div>
          <div class="mb-2">
            <label class="form-label small">Search (Places Autocomplete)</label>
            <input id="acInput" class="form-control form-control-sm" placeholder="Type business name..."/>
            <div id="acList" class="list-group mt-2"></div>
          </div>
          <div class="row g-2">
            <div class="col-12">
              <label class="form-label small">Place ID</label>
              <input id="placeId" class="form-control form-control-sm" placeholder="place_id"/>
            </div>
            <div class="col-12">
              <label class="form-label small">Name</label>
              <input id="coName" class="form-control form-control-sm" placeholder="Company Name"/>
            </div>
            <div class="col-12">
              <label class="form-label small">Email</label>
              <input id="coEmail" class="form-control form-control-sm" placeholder="Email (optional)"/>
            </div>
          </div>
          <div class="d-flex gap-2 mt-2">
            <button id="coCreate" class="btn btn-success btn-sm"><i data-lucide="plus"></i> Create</button>
            <button id="coDetails" class="btn btn-info btn-sm"><i data-lucide="info"></i> Preview Details</button>
          </div>
          <div id="coPreview" class="small mt-2 text-secondary"></div>
        </section>
      </aside>

      <!-- Right: Intelligence + Reviews -->
      <section class="col-lg-8">
        <!-- Diagnostics + Controls -->
        <div class="glass p-3 p-md-4 mb-3">
          <div class="d-flex flex-wrap align-items-center gap-2 justify-content-between">
            <div class="d-flex flex-wrap gap-2">
              <div class="input-group input-group-sm" style="width: 220px;">
                <span class="input-group-text bg-transparent">Start</span>
                <input type="date" id="startDate" class="form-control"/>
              </div>
              <div class="input-group input-group-sm" style="width: 220px;">
                <span class="input-group-text bg-transparent">End</span>
                <input type="date" id="endDate" class="form-control"/>
              </div>
              <div class="btn-group btn-group-sm" role="group">
                <button class="btn btn-outline-secondary" id="q90">90d</button>
                <button class="btn btn-outline-secondary" id="q30">30d</button>
                <button class="btn btn-outline-secondary" id="q7">7d</button>
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button id="btnSummary" class="btn btn-primary btn-sm"><i data-lucide="refresh-ccw"></i> Load Summary</button>
              <button id="btnSyncQuick" class="btn btn-warning btn-sm"><i data-lucide="list-plus"></i> Quick Sync (5)</button>
              <button id="btnSyncDeep" class="btn btn-outline-warning btn-sm"><i data-lucide="refresh-cw"></i> Deep Sync</button>
              <button id="btnDiag" class="btn btn-outline-secondary btn-sm"><i data-lucide="activity"></i> Diagnostics</button>
            </div>
          </div>
          <div id="diagChips" class="d-flex flex-wrap gap-2 mt-2"></div>
          <small id="diagMeta" class="text-secondary d-block"></small>
        </div>

        <!-- Metrics -->
        <div class="row g-3">
          <div class="col-md-3">
            <div class="glass p-3 h-100">
              <div class="small text-secondary">Total Volume</div>
              <div id="statTotal" class="display-6">0</div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="glass p-3 h-100">
              <div class="small text-secondary">Avg Rating</div>
              <div id="statAvg" class="display-6">0.0</div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="glass p-3 h-100">
              <div class="small text-secondary">Risk Score</div>
              <div id="statRisk" class="display-6">0</div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="glass p-3 h-100">
              <div class="small text-secondary">Signal</div>
              <div id="statSignal" class="display-6">—</div>
            </div>
          </div>
        </div>

        <!-- AI Narrative -->
        <div class="glass p-3 p-md-4 mt-3">
          <div class="d-flex align-items-center gap-2 mb-2">
            <span class="p-2 rounded bg-primary-subtle text-primary"><i data-lucide="sparkles"></i></span>
            <h6 class="mb-0">AI Narrative & Recommendations</h6>
          </div>
          <p id="aiContent" class="mb-0 fst-italic text-secondary">Select a company and load summary…</p>
        </div>

        <!-- Charts -->
        <div class="row g-3 mt-1 mt-md-3">
          <div class="col-lg-6">
            <div class="glass p-3 p-md-4 h-100">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <h6 class="mb-0">Performance Trend</h6>
                <button id="expTrend" class="btn btn-sm btn-outline-secondary"><i data-lucide="download"></i> PNG</button>
              </div>
              <div style="height: 280px"><canvas id="chartTrend"></canvas></div>
            </div>
          </div>
          <div class="col-lg-6">
            <div class="glass p-3 p-md-4 h-100">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <h6 class="mb-0">Sentiment Mix</h6>
                <button id="expSent" class="btn btn-sm btn-outline-secondary"><i data-lucide="download"></i> PNG</button>
              </div>
              <div style="height: 280px"><canvas id="chartSent"></canvas></div>
            </div>
          </div>
        </div>

        <!-- Reviews Table (from /api/reviews/list)  -->
        <div class="glass p-3 p-md-4 mt-3">
          <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
            <h6 class="mb-0">Reviews</h6>
            <div class="d-flex flex-wrap gap-2">
              <div class="input-group input-group-sm" style="width: 220px;">
                <span class="input-group-text bg-transparent"><i data-lucide="search"></i></span>
                <input id="revSearch" class="form-control" placeholder="Search…" />
              </div>
              <div class="input-group input-group-sm" style="width: 140px;">
                <span class="input-group-text bg-transparent">Rating</span>
                <select id="revRating" class="form-select">
                  <option value="">All</option>
                  <option>1</option><option>2</option><option>3</option><option>4</option><option>5</option>
                </select>
              </div>
              <div class="input-group input-group-sm" style="width: 160px;">
                <span class="input-group-text bg-transparent">Order</span>
                <select id="revOrder" class="form-select">
                  <option value="desc" selected>Newest</option>
                  <option value="asc">Oldest</option>
                </select>
              </div>
              <div class="input-group input-group-sm" style="width: 120px;">
                <span class="input-group-text bg-transparent">Page</span>
                <input id="revPage" type="number" min="1" class="form-control" value="1" />
              </div>
              <div class="input-group input-group-sm" style="width: 140px;">
                <span class="input-group-text bg-transparent">Limit</span>
                <select id="revLimit" class="form-select">
                  <option>25</option><option selected>50</option><option>100</option><option>200</option>
                </select>
              </div>
              <button id="revLoad" class="btn btn-sm btn-outline-primary"><i data-lucide="refresh-ccw"></i> Load</button>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table table-sm align-middle table-fixed">
              <thead class="table-dark">
                <tr>
                  <th style="width:38%">Text</th>
                  <th style="width:10%">Rating</th>
                  <th style="width:12%">Date</th>
                  <th style="width:14%">Category</th>
                  <th style="width:10%">Score</th>
                  <th style="width:16%">Lang</th>
                </tr>
              </thead>
              <tbody id="revBody"></tbody>
            </table>
          </div>
          <div id="revMeta" class="small text-secondary mt-1">—</div>
        </div>

        <!-- Company Reviews (quick view via /api/companies/{id}/reviews) -->
        <div class="glass p-3 p-md-4 mt-3">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <h6 class="mb-0">Company Reviews (Quick)</h6>
            <div class="input-group input-group-sm" style="max-width: 220px;">
              <span class="input-group-text bg-transparent">Limit</span>
              <input id="coRevLimit" type="number" class="form-control" value="25" min="1" max="200"/>
              <button id="coRevLoad" class="btn btn-outline-secondary">Load</button>
            </div>
          </div>
          <div id="coRevList" class="small"></div>
        </div>
      </section>
    </div>
  </main>

  <script>
    // Theme
    const themeKey = 'rs_theme';
    function applyTheme(theme){
      document.documentElement.setAttribute('data-bs-theme', theme);
      localStorage.setItem(themeKey, theme);
      const meta = document.querySelector('meta[name="theme-color"]');
      meta && meta.setAttribute('content', theme === 'dark' ? '#0b1220' : '#f8f9fa');
      // recolor charts
      Charts.renderAll();
      const icon = document.querySelector('#themeToggle i');
      icon && icon.setAttribute('data-lucide', theme === 'dark' ? 'moon-star' : 'sun');
      lucide.createIcons();
    }
    applyTheme(localStorage.getItem(themeKey) || 'dark');
    document.getElementById('themeToggle').addEventListener('click', ()=>{
      const next = (document.documentElement.getAttribute('data-bs-theme')==='dark')?'light':'dark';
      applyTheme(next);
    });

    // Persisted settings
    const tokenKey='rs_api_token', companyKey='rs_company_id', sessKey='rs_google_session', filtersKey='rs_filters';
    const apiTokenEl = document.getElementById('apiToken');
    const companyEl = document.getElementById('companyId');
    apiTokenEl.value = localStorage.getItem(tokenKey) || '';
    companyEl.value = localStorage.getItem(companyKey) || '';
    document.getElementById('saveToken').onclick = ()=>{
      localStorage.setItem(tokenKey, apiTokenEl.value.trim());
    };

    // Dates default → last 90 days
    const end = new Date(); const start = new Date(); start.setDate(end.getDate()-90);
    const startEl = document.getElementById('startDate');
    const endEl = document.getElementById('endDate');
    startEl.value = (localStorage.getItem(filtersKey+'-start') || start.toISOString().split('T')[0]);
    endEl.value   = (localStorage.getItem(filtersKey+'-end')   || end.toISOString().split('T')[0]);
    startEl.onchange = ()=> localStorage.setItem(filtersKey+'-start', startEl.value);
    endEl.onchange   = ()=> localStorage.setItem(filtersKey+'-end', endEl.value);
    document.getElementById('q90').onclick=()=>{const e=new Date(), s=new Date(); s.setDate(e.getDate()-90); startEl.value=s.toISOString().split('T')[0]; endEl.value=e.toISOString().split('T')[0]; startEl.onchange(); endEl.onchange();}
    document.getElementById('q30').onclick=()=>{const e=new Date(), s=new Date(); s.setDate(e.getDate()-30); startEl.value=s.toISOString().split('T')[0]; endEl.value=e.toISOString().split('T')[0]; startEl.onchange(); endEl.onchange();}
    document.getElementById('q7').onclick =()=>{const e=new Date(), s=new Date(); s.setDate(e.getDate()-7 ); startEl.value=s.toISOString().split('T')[0]; endEl.value=e.toISOString().split('T')[0]; startEl.onchange(); endEl.onchange();}

    // HTTP helpers
    function headers(){
      const h = { 'Content-Type':'application/json' };
      const t = localStorage.getItem(tokenKey);
      if(t){ h['Authorization'] = 'Bearer '+t; h['X-API-Key']=t; }
      return h;
    }
    async function apiGet(path){
      const r = await fetch(path, { headers: headers() });
      if(!r.ok){ throw new Error('GET '+path+' failed: '+r.status); }
      return r.json();
    }
    async function apiPost(path, body){
      const r = await fetch(path, { method:'POST', headers: headers(), body: body?JSON.stringify(body):undefined });
      if(!r.ok){ throw new Error('POST '+path+' failed: '+r.status); }
      return r.json();
    }

    // Diagnostics
    async function loadDiagnostics(){
      try{
        const d = await apiGet('/api/reviews/diagnostics');
        const chips = [];
        chips.push(`<span class="chip ${d.google_places_key_present?'chip-ok':'chip-bad'}">Places Key</span>`);
        chips.push(`<span class="chip ${d.google_maps_key_present?'chip-ok':'chip-bad'}">Maps Key</span>`);
        chips.push(`<span class="chip ${d.google_business_key_present?'chip-ok':'chip-bad'}">Business Key</span>`);
        chips.push(`<span class="chip ${d.api_token_configured?'chip-ok':'chip-warn'}">API Token</span>`);
        document.getElementById('diagChips').innerHTML = chips.join(' ');
        document.getElementById('diagMeta').textContent = `Env: ${d.environment} · Scan limit: ${d.reviews_scan_limit} · Python: ${d.python_version}`;
      }catch(e){
        document.getElementById('diagChips').innerHTML = '<span class="chip chip-bad">Diagnostics failed</span>';
        document.getElementById('diagMeta').textContent = e.message;
      }
    }
    document.getElementById('btnDiag').onclick = loadDiagnostics; loadDiagnostics();

    // Charts
    const Charts = {
      trend:null, sent:null, _last:null,
      palette(){
        const dark = document.documentElement.getAttribute('data-bs-theme')==='dark';
        return { grid: dark?'rgba(255,255,255,.08)':'rgba(0,0,0,.08)', label: dark?'#cbd5e1':'#334155', line: dark?'#3b82f6':'#2563eb', pos:'#10b981', neu:'#64748b', neg:'#ef4444' };
      },
      renderAll(){ if(this._last) this.render(this._last); },
      render(data){
        this._last = data;
        const p = this.palette();
        // Trend
        const tctx = document.getElementById('chartTrend').getContext('2d');
        this.trend && this.trend.destroy();
        this.trend = new Chart(tctx, {
          type:'line',
          data:{ labels: (data.trend&&data.trend.labels)||[], datasets:[{ label:'Rating', data:(data.trend&&data.trend.data)||[], borderColor:p.line, backgroundColor:p.line+'22', tension:.35, borderWidth:3, pointRadius:2, fill:true }]},
          options:{ plugins:{ legend:{display:false} }, scales:{ x:{ ticks:{color:p.label}}, y:{ ticks:{color:p.label}, grid:{color:p.grid}, min:0, max:5 } } }
        });
        // Sentiment
        const sctx = document.getElementById('chartSent').getContext('2d');
        this.sent && this.sent.destroy();
        const pos = (data.sentiment&&data.sentiment.Positive)||0; const neu=(data.sentiment&&data.sentiment.Neutral)||0; const neg=(data.sentiment&&data.sentiment.Negative)||0;
        this.sent = new Chart(sctx, { type:'doughnut', data:{ labels:['Positive','Neutral','Negative'], datasets:[{ data:[pos,neu,neg], backgroundColor:[p.pos,p.neu,p.neg], borderWidth:0 }] }, options:{ plugins:{ legend:{ position:'bottom', labels:{ color:p.label } } }, cutout:'72%' } });
      }
    };

    function setSummaryUI(data){
      try{
        document.getElementById('statTotal').textContent = (data.metrics&&data.metrics.total)||0;
        document.getElementById('statAvg').textContent = ((data.metrics&&data.metrics.avg_rating)||0).toFixed?((+data.metrics.avg_rating).toFixed(1)):(data.metrics&&data.metrics.avg_rating)||'0.0';
      }catch{ document.getElementById('statAvg').textContent='0.0'; }
      document.getElementById('statRisk').textContent = (data.metrics&&data.metrics.risk_score)||0;
      document.getElementById('statSignal').textContent = (data.trend&&data.trend.signal)||'—';
      document.getElementById('aiContent').textContent = (data.ai_recommendations&&data.ai_recommendations[0]&&data.ai_recommendations[0].action)||'—';
      Charts.render(data);
    }

    async function loadSummary(){
      const cid = (companyEl.value||'').trim(); if(!cid) return;
      localStorage.setItem(companyKey, cid);
      const start = startEl.value; const end = endEl.value;
      try{
        const data = await apiGet(`/api/reviews/summary/${cid}?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
        setSummaryUI(data);
      }catch(e){ console.error(e); alert('Failed to load summary'); }
    }
    document.getElementById('btnSummary').onclick = loadSummary;

    // Export charts
    function exportPNG(canvasId, filename){ const c=document.getElementById(canvasId); const a=document.createElement('a'); a.href=c.toDataURL('image/png'); a.download=filename; document.body.appendChild(a); a.click(); a.remove(); }
    document.getElementById('expTrend').onclick=()=>exportPNG('chartTrend','trend.png');
    document.getElementById('expSent').onclick =()=>exportPNG('chartSent','sentiment.png');

    // Sync actions
    document.getElementById('btnSyncQuick').onclick = async ()=>{
      const cid=(companyEl.value||'').trim(); if(!cid) return;
      try{ const res=await apiPost(`/api/companies/${cid}/reviews/sync`); alert(`Quick sync OK. Created: ${res.created}, Updated: ${res.updated}`); await loadSummary(); await loadReviews(); await loadCompanyReviews(); }
      catch(e){ console.error(e); alert('Quick sync failed'); }
    };
    document.getElementById('btnSyncDeep').onclick = async ()=>{
      const cid=(companyEl.value||'').trim(); if(!cid) return;
      try{ const res=await apiPost(`/api/reviews/sync/${cid}`); alert(`Deep sync OK. Added: ${res.added}`); await loadSummary(); await loadReviews(); await loadCompanyReviews(); }
      catch(e){ console.error(e); alert('Deep sync failed'); }
    };

    // Reviews list (reviews service)
    const rev = { page: 1, limit: 50, q:'', rating:'', order:'desc' };
    const revSearch = document.getElementById('revSearch');
    const revRating = document.getElementById('revRating');
    const revOrder  = document.getElementById('revOrder');
    const revPage   = document.getElementById('revPage');
    const revLimit  = document.getElementById('revLimit');

    async function loadReviews(){
      const cid=(companyEl.value||'').trim(); if(!cid) return;
      const start=startEl.value, end=endEl.value;
      rev.page = parseInt(revPage.value||'1',10)||1; rev.limit=parseInt(revLimit.value||'50',10)||50; rev.q=revSearch.value.trim(); rev.rating=revRating.value; rev.order=revOrder.value;
      const url = new URL(location.origin+`/api/reviews/list/${cid}`);
      url.searchParams.set('page', String(rev.page)); url.searchParams.set('limit', String(rev.limit));
      if(rev.q) url.searchParams.set('q', rev.q);
      if(rev.rating) url.searchParams.set('rating', rev.rating);
      url.searchParams.set('order', rev.order);
      url.searchParams.set('start', start); url.searchParams.set('end', end);
      try{
        const data = await apiGet(url.pathname + url.search);
        const body = document.getElementById('revBody'); body.innerHTML='';
        (data.items||[]).forEach(r=>{
          const tr=document.createElement('tr');
          const text=(r.text||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
          tr.innerHTML = `
            <td><div class="truncate-2" title="${text}">${text}</div></td>
            <td>${r.rating ?? ''}</td>
            <td><small>${(r.review_date||'').split('T')[0]}</small></td>
            <td><span class="badge ${r.sentiment_category==='positive'?'text-bg-success-subtle':r.sentiment_category==='negative'?'text-bg-danger-subtle':'text-bg-secondary-subtle'}">${r.sentiment_category ?? ''}</span></td>
            <td><code>${r.sentiment_score!=null ? Number(r.sentiment_score).toFixed(3) : ''}</code></td>
            <td>${r.language ?? ''}</td>
          `;
          body.appendChild(tr);
        });
        document.getElementById('revMeta').textContent = `Total ${data.total} • Page ${data.page} • Limit ${data.limit}`;
      }catch(e){ console.error(e); alert('Failed to load reviews'); }
    }
    document.getElementById('revLoad').onclick = loadReviews;

    // Company Reviews (quick view via companies route)
    async function loadCompanyReviews(){
      const cid=(companyEl.value||'').trim(); if(!cid) return;
      const lim = Math.max(1, Math.min(200, parseInt(document.getElementById('coRevLimit').value||'25',10)));
      try{
        const data = await apiGet(`/api/companies/${cid}/reviews?page=1&limit=${lim}`);
        const el = document.getElementById('coRevList');
        el.innerHTML = (data.data||[]).map(r=>{
          const txt=(r.text||'').replaceAll('&','&amp;').replaceAll('<','&lt;');
          return `<div class='border-bottom py-2'><div class='d-flex justify-content-between small'><strong>${r.reviewer_name||'—'}</strong><span>★${r.rating||'-'}</span></div><div class='small text-secondary'>${(r.review_date||'').split('T')[0]} · ${r.language||''}</div><div>${txt}</div></div>`
        }).join('');
      }catch(e){ console.error(e); }
    }
    document.getElementById('coRevLoad').onclick = loadCompanyReviews;

    // Companies directory
    const co = { page:1, limit:30, sort:'created_at', order:'desc', search:'' };
    const coList = document.getElementById('coList');
    const coSearch = document.getElementById('coSearch');
    const coSort = document.getElementById('coSort');
    const coOrder = document.getElementById('coOrder');
    const coPrev = document.getElementById('coPrev');
    const coNext = document.getElementById('coNext');
    const coPageLbl = document.getElementById('coPageLbl');

    async function loadCompanies(direction){
      if(direction==='next') co.page += 1; if(direction==='prev' && co.page>1) co.page -= 1;
      const url = new URL(location.origin + '/api/companies/');
      url.searchParams.set('page', String(co.page));
      url.searchParams.set('limit', String(co.limit));
      url.searchParams.set('sort', co.sort); url.searchParams.set('order', co.order);
      if(co.search) url.searchParams.set('search', co.search);
      try{
        const rows = await apiGet(url.pathname + url.search);
        coList.innerHTML = (rows||[]).map(c=>{
          const city = (c.city||'').replaceAll('<','&lt;');
          return `<button type='button' class='list-group-item list-group-item-action d-flex justify-content-between align-items-center' data-id='${c.id}'>
                    <div>
                      <div class='fw-bold'>${(c.name||'').replaceAll('<','&lt;')} <span class='badge rounded-pill text-bg-secondary-subtle ms-1'>#${c.id}</span></div>
                      <div class='small text-secondary'>${city}</div>
                    </div>
                    <i data-lucide='arrow-right'></i>
                  </button>`;
        }).join('');
        coList.querySelectorAll('button').forEach(b=> b.onclick = ()=>{ companyEl.value = b.getAttribute('data-id'); localStorage.setItem(companyKey, companyEl.value); loadSummary(); loadReviews(); loadCompanyReviews(); });
        coPrev.disabled = co.page<=1; coPageLbl.textContent = `Page ${co.page}`; lucide.createIcons();
        // Enable/disable next based on rows length
        coNext.disabled = !rows || rows.length < co.limit;
      }catch(e){ console.error(e); alert('Failed to load companies'); }
    }

    coPrev.onclick = ()=>loadCompanies('prev');
    coNext.onclick = ()=>loadCompanies('next');
    coSort.onchange = ()=>{ co.sort = coSort.value; co.page = 1; loadCompanies(); };
    coOrder.onchange= ()=>{ co.order= coOrder.value; co.page = 1; loadCompanies(); };
    let coDeb; coSearch.addEventListener('input', ()=>{ clearTimeout(coDeb); coDeb=setTimeout(()=>{ co.search = coSearch.value.trim(); co.page=1; loadCompanies(); }, 200); });

    // Google Places - Autocomplete via companies route
    function guid(){ return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2); }
    const sessionToken = localStorage.getItem(sessKey) || guid(); localStorage.setItem(sessKey, sessionToken);
    const gLang = document.getElementById('gLang'); gLang.value = (localStorage.getItem('rs_g_lang')||'en'); gLang.onchange=()=>localStorage.setItem('rs_g_lang', gLang.value);

    const acInput = document.getElementById('acInput'); const acList = document.getElementById('acList');
    let acDeb; acInput.addEventListener('input', ()=>{
      clearTimeout(acDeb); const q = acInput.value.trim(); if(!q){ acList.innerHTML=''; return; }
      acDeb = setTimeout(async()=>{
        try{
          const res = await apiGet(`/api/companies/autocomplete?q=${encodeURIComponent(q)}&language=${encodeURIComponent(gLang.value||'')}&sessiontoken=${encodeURIComponent(sessionToken)}`);
          acList.innerHTML = (res||[]).map(p=>`<button type='button' class='list-group-item list-group-item-action' data-pid='${p.place_id}'>${(p.description||'').replaceAll('<','&lt;')}</button>`).join('');
          acList.querySelectorAll('button').forEach(b=> b.onclick = ()=>{ document.getElementById('placeId').value = b.getAttribute('data-pid'); acList.innerHTML=''; } );
        }catch(e){ acList.innerHTML='<div class="list-group-item text-danger">Autocomplete failed</div>'; }
      }, 200);
    });

    // Preview details before create (via reviews details for richer set)
    document.getElementById('coDetails').onclick = async ()=>{
      const pid=(document.getElementById('placeId').value||'').trim(); if(!pid) return;
      const lang=gLang.value||'';
      try{
        const d = await apiGet(`/api/reviews/google/details?place_id=${encodeURIComponent(pid)}&language=${encodeURIComponent(lang)}&include_reviews=false`);
        const el=document.getElementById('coPreview');
        el.innerHTML = `<div><strong>${(d.name||'')}</strong></div><div class='text-secondary small'>${d.address||''}</div><div class='small'>Rating: ${d.rating ?? '-'} · Count: ${d.user_ratings_total ?? 0}</div>`;
        document.getElementById('coName').value = d.name || document.getElementById('coName').value;
      }catch(e){ alert('Preview failed'); }
    };

    // Create company
    document.getElementById('coCreate').onclick = async ()=>{
      const payload = {
        name: (document.getElementById('coName').value||'').trim() || 'Unnamed',
        place_id: (document.getElementById('placeId').value||'').trim() || null,
        email: (document.getElementById('coEmail').value||'').trim() || null,
        city: null, address: null, website: null, phone: null, lat: null, lng: null, description: null
      };
      try{
        const c = await apiPost(`/api/companies?language=${encodeURIComponent(gLang.value||'')}`, payload);
        alert(`Created company #${c.id}`);
        companyEl.value = c.id; localStorage.setItem(companyKey, c.id);
        await loadCompanies(); await loadSummary(); await loadReviews(); await loadCompanyReviews();
      }catch(e){ console.error(e); alert('Create failed'); }
    };

    // Initial boot
    (async function init(){
      lucide.createIcons();
      await loadCompanies();
      if(companyEl.value){ await loadSummary(); await loadReviews(); await loadCompanyReviews(); }
    })();
  </script>
</body>
</html>
