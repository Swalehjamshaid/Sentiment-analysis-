<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Company Reviews Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- Bootstrap 5 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">

  <style>
    body { padding: 20px; }
    .review-positive { background-color: #d4edda; }
    .review-negative { background-color: #f8d7da; }
    .review-neutral { background-color: #fff3cd; }
    .cursor-pointer { cursor: pointer; }
    .spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid #ccc; border-top-color: #333; border-radius: 50%; animation: spin 0.7s linear infinite; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>

<div class="container">
  <h1 class="mb-4">Company Reviews Dashboard</h1>

  <!-- Company Search / Autocomplete -->
  <div class="mb-4">
    <label for="companySearch" class="form-label">Search Company</label>
    <input type="text" id="companySearch" class="form-control" placeholder="Type company name or address..." autocomplete="off">
    <div id="autocompleteList" class="list-group position-absolute w-50"></div>
  </div>

  <!-- Company Details -->
  <div id="companyDetails" class="mb-4" style="display:none;">
    <h3 id="companyName"></h3>
    <p id="companyAddress"></p>
    <p><strong>City:</strong> <span id="companyCity"></span></p>
    <p><strong>Website:</strong> <a id="companyWebsite" href="#" target="_blank"></a></p>
    <p><strong>Phone:</strong> <span id="companyPhone"></span></p>

    <button class="btn btn-primary me-2" id="syncReviewsBtn">Sync Reviews</button>
    <button class="btn btn-secondary" id="importReviewsBtn">Import Google Reviews</button>
    <div id="actionSpinner" style="display:none;" class="spinner"></div>
  </div>

  <!-- Dashboard Summary -->
  <div id="reviewsSummary" class="mb-4" style="display:none;">
    <h4>Reviews Summary</h4>
    <div id="summaryContent"></div>
  </div>

  <!-- Reviews Table -->
  <div id="reviewsSection" style="display:none;">
    <h4>Reviews</h4>
    <table class="table table-bordered table-hover">
      <thead>
        <tr>
          <th>Date</th>
          <th>Rating</th>
          <th>Reviewer</th>
          <th>Text</th>
          <th>Sentiment</th>
        </tr>
      </thead>
      <tbody id="reviewsTable"></tbody>
    </table>

    <nav>
      <ul class="pagination" id="reviewsPagination"></ul>
    </nav>
  </div>
</div>

<!-- Bootstrap 5 JS Bundle -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>

<script>
  const apiBase = "/api";  // adjust if needed
  let selectedCompanyId = null;
  let currentPage = 1;
  const reviewsPerPage = 10;

  // Autocomplete
  const searchInput = document.getElementById("companySearch");
  const autocompleteList = document.getElementById("autocompleteList");

  searchInput.addEventListener("input", async (e) => {
    const q = e.target.value;
    autocompleteList.innerHTML = "";
    if (q.length < 2) return;
    try {
      const res = await fetch(`${apiBase}/companies/autocomplete?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      data.forEach(item => {
        const el = document.createElement("a");
        el.classList.add("list-group-item", "list-group-item-action", "cursor-pointer");
        el.textContent = item.description;
        el.onclick = () => selectCompany(item.place_id);
        autocompleteList.appendChild(el);
      });
    } catch (err) { console.error(err); }
  });

  async function selectCompany(placeId) {
    autocompleteList.innerHTML = "";
    const res = await fetch(`${apiBase}/reviews/google/details?place_id=${placeId}`);
    const data = await res.json();
    selectedCompanyId = placeId;

    // Display company details
    document.getElementById("companyDetails").style.display = "block";
    document.getElementById("companyName").textContent = data.name || "";
    document.getElementById("companyAddress").textContent = data.address || "";
    document.getElementById("companyCity").textContent = data.city || "";
    const websiteEl = document.getElementById("companyWebsite");
    websiteEl.textContent = data.website || "";
    websiteEl.href = data.website || "#";
    document.getElementById("companyPhone").textContent = data.phone || "";

    // Load dashboard summary and reviews
    loadSummary();
    loadReviews();
  }

  async function loadSummary() {
    try {
      const res = await fetch(`${apiBase}/reviews/summary/${selectedCompanyId}`);
      const summary = await res.json();
      const content = document.getElementById("summaryContent");
      content.innerHTML = JSON.stringify(summary, null, 2);
      document.getElementById("reviewsSummary").style.display = "block";
    } catch (err) { console.error(err); }
  }

  async function loadReviews(page = 1) {
    currentPage = page;
    try {
      const res = await fetch(`${apiBase}/reviews/list/${selectedCompanyId}?page=${page}&limit=${reviewsPerPage}`);
      const data = await res.json();
      const tbody = document.getElementById("reviewsTable");
      tbody.innerHTML = "";
      data.items.forEach(r => {
        const tr = document.createElement("tr");
        tr.classList.add(r.sentiment_category === "Positive" ? "review-positive" :
                        r.sentiment_category === "Negative" ? "review-negative" : "review-neutral");
        tr.innerHTML = `
          <td>${r.review_date}</td>
          <td>${r.rating}</td>
          <td>${r.reviewer_name || ""}</td>
          <td>${r.text || ""}</td>
          <td>${r.sentiment_category || ""}</td>
        `;
        tbody.appendChild(tr);
      });

      // Pagination
      const pagination = document.getElementById("reviewsPagination");
      pagination.innerHTML = "";
      const totalPages = Math.ceil(data.total / reviewsPerPage);
      for (let i = 1; i <= totalPages; i++) {
        const li = document.createElement("li");
        li.className = `page-item ${i === page ? "active" : ""}`;
        const a = document.createElement("a");
        a.className = "page-link";
        a.textContent = i;
        a.onclick = () => loadReviews(i);
        li.appendChild(a);
        pagination.appendChild(li);
      }

      document.getElementById("reviewsSection").style.display = "block";
    } catch (err) { console.error(err); }
  }

  // Sync Reviews
  document.getElementById("syncReviewsBtn").addEventListener("click", async () => {
    const spinner = document.getElementById("actionSpinner");
    spinner.style.display = "inline-block";
    try {
      const res = await fetch(`${apiBase}/reviews/sync/${selectedCompanyId}`, { method: "POST" });
      const result = await res.json();
      alert(`Reviews synced. Added: ${result.added || 0}`);
      loadSummary();
      loadReviews();
    } catch (err) { console.error(err); alert("Sync failed"); }
    spinner.style.display = "none";
  });

  // Import Google Reviews
  document.getElementById("importReviewsBtn").addEventListener("click", async () => {
    const spinner = document.getElementById("actionSpinner");
    spinner.style.display = "inline-block";
    try {
      const res = await fetch(`${apiBase}/reviews/google/import/${selectedCompanyId}?place_id=${selectedCompanyId}`, { method: "POST" });
      const result = await res.json();
      alert(`Google reviews imported: ${result.imported || 0}`);
      loadSummary();
      loadReviews();
    } catch (err) { console.error(err); alert("Import failed"); }
    spinner.style.display = "none";
  });

</script>
</body>
</html>
