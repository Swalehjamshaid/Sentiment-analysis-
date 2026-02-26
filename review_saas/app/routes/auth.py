<!-- filename: review_saas/app/templates/base.html -->
<!doctype html>
<html lang="en" data-bs-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="ReviewSaaS - AI-powered sentiment analytics." />
  <title>{% block title %}ReviewSaaS{% endblock %}</title>

  <!-- Bootstrap -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">

  <style>
    :root {
      --glass-bg: rgba(255,255,255,0.72);
      --glass-border: rgba(255,255,255,0.28);
      --card-radius: 16px;
      --shadow: 0 10px 30px rgba(0,0,0,0.06);
    }

    body {
      min-height: 100vh;
      background:
       linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(16,185,129,0.06) 100%),
       radial-gradient(900px 350px at 0% 0%, rgba(99,102,241,0.18), transparent),
       radial-gradient(900px 350px at 100% 100%, rgba(20,184,166,0.18), transparent);
      backdrop-filter: saturate(1.2);
    }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 2000;
      height: 64px;
      background: var(--glass-bg);
      border-bottom: 1px solid var(--glass-border);
      backdrop-filter: blur(12px);
    }

    .brand-badge {
      background: linear-gradient(135deg, #6366f1, #14b8a6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      font-weight: 800;
      font-size: 1.25rem;
    }

    .card-glass {
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: var(--card-radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }

    footer {
      background: var(--glass-bg);
      border-top: 1px solid var(--glass-border);
      backdrop-filter: blur(10px);
    }
  </style>

  {% block head_extra %}{% endblock %}
</head>

<body>

<!-- 🔝 NAVBAR -->
<nav class="topbar navbar navbar-expand-lg px-3">
  <div class="container-fluid">

    <!-- Logo -->
    <a class="navbar-brand fw-bold d-flex align-items-center gap-2" href="/">
      <i class="bi bi-speedometer2"></i>
      <span class="brand-badge">ReviewSaaS</span>
    </a>

    <div class="d-flex align-items-center gap-2 ms-auto">

      {% if current_user %}
        <span class="small text-secondary d-none d-md-inline">
          Hi, {{ current_user.full_name or current_user.email }}
        </span>

        <a href="/logout" class="btn btn-outline-secondary rounded-pill px-3">
          <i class="bi bi-box-arrow-right me-2"></i>Logout
        </a>

      {% else %}

        <button class="btn btn-outline-secondary rounded-pill px-3"
                data-bs-toggle="modal" data-bs-target="#loginModal">
          <i class="bi bi-person me-2"></i>Login
        </button>

        <button class="btn btn-primary rounded-pill px-3"
                data-bs-toggle="modal" data-bs-target="#registerModal">
          <i class="bi bi-person-plus me-2"></i>Register
        </button>

      {% endif %}

      <button class="btn btn-info rounded-pill px-3"
              data-bs-toggle="modal" data-bs-target="#aboutModal">
        <i class="bi bi-info-circle me-2"></i>About
      </button>

    </div>
  </div>
</nav>

<!-- MAIN CONTENT -->
<main class="container my-4">

  <!-- Flash Messages -->
  {% if flash_error %}
  <div class="alert alert-danger alert-dismissible fade show" role="alert">
    {{ flash_error }}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% endif %}

  {% if flash_success %}
  <div class="alert alert-success alert-dismissible fade show" role="alert">
    {{ flash_success }}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% endif %}

  {% block content %}
  <!-- Default Landing Hero -->
  <section class="card-glass p-4 p-md-5">
    <div class="row align-items-center gy-4">

      <div class="col-lg-7">
        <h1 class="display-6 fw-bold mb-3">
          AI-Powered <span class="brand-badge">Sentiment Analysis</span> for Reviews
        </h1>
        <p class="lead text-secondary mb-4">
          ReviewSaaS helps businesses understand customer emotions through NLP-powered insights.
          Register to begin — login next time and jump straight to your Dashboard.
        </p>

        <div class="d-flex gap-2">
          <button class="btn btn-primary btn-lg rounded-pill px-4"
                  data-bs-toggle="modal" data-bs-target="#registerModal">
            <i class="bi bi-person-plus me-2"></i>Create Account
          </button>

          <button class="btn btn-outline-secondary btn-lg rounded-pill px-4"
                  data-bs-toggle="modal" data-bs-target="#loginModal">
            <i class="bi bi-box-arrow-in-right me-2"></i>Login
          </button>

          <button class="btn btn-info btn-lg rounded-pill px-4"
                  data-bs-toggle="modal" data-bs-target="#aboutModal">
            <i class="bi bi-info-circle me-2"></i>About
          </button>
        </div>
      </div>

      <div class="col-lg-5">
        <div class="p-4 bg-body-tertiary rounded-4 border">
          <h5 class="mb-3">What is Sentiment Analysis?</h5>
          <p class="text-secondary">
            Sentiment Analysis classifies feedback into positive, negative, or neutral.
            ReviewSaaS uses NLP to detect themes, emotions, and satisfaction levels.
          </p>
        </div>
      </div>

    </div>
  </section>
  {% endblock %}

</main>

<!-- FOOTER -->
<footer class="py-3 text-center small text-muted">
  © {{ now().year if now else "2026" }} ReviewSaaS — All rights reserved.
</footer>


<!-- ========================================================= -->
<!-- LOGIN MODAL -->
<div class="modal fade" id="loginModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <form method="post" action="/login" class="modal-content">

      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-person me-2"></i>Login</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>

      <div class="modal-body">
        {{ csrf_token() }}
        <div class="mb-3">
          <label class="form-label">Email</label>
          <input name="email" type="email" class="form-control" placeholder="you@example.com" required>
        </div>
        <div>
          <label class="form-label">Password</label>
          <input name="password" type="password" class="form-control" placeholder="••••••••" required>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-primary px-4 rounded-pill" type="submit">Login</button>
      </div>

    </form>
  </div>
</div>

<!-- REGISTER MODAL -->
<div class="modal fade" id="registerModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <form method="post" action="/register" class="modal-content">

      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-person-plus me-2"></i>Register</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>

      <div class="modal-body">
        {{ csrf_token() }}
        <div class="mb-3">
          <label class="form-label">Full Name</label>
          <input name="name" type="text" class="form-control" required>
        </div>

        <div class="mb-3">
          <label class="form-label">Email</label>
          <input name="email" type="email" class="form-control" required>
        </div>

        <div>
          <label class="form-label">Password</label>
          <input name="password" type="password" class="form-control" minlength="6" required>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-success px-4 rounded-pill" type="submit">
          Create Account
        </button>
      </div>

    </form>
  </div>
</div>

<!-- ABOUT MODAL -->
<div class="modal fade" id="aboutModal" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-centered">
    <div class="modal-content p-3">
      <div class="modal-header border-0">
        <h4 class="modal-title"><i class="bi bi-info-circle me-2"></i>About ReviewSaaS</h4>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>

      <div class="modal-body pt-0">
        <p>
          ReviewSaaS uses advanced Natural Language Processing (NLP)
          to classify customer feedback into positive, negative, and neutral sentiment.
        </p>
        <ul>
          <li>Track sentiment trends</li>
          <li>Identify key customer pain points</li>
          <li>Monitor satisfaction over time</li>
          <li>Generate insights using AI</li>
        </ul>
      </div>
    </div>
  </div>
</div>

<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

<!-- Auto-open modals when ?show=login/register/about -->
<script>
  (function() {
    const params = new URLSearchParams(window.location.search);
    const show = params.get('show');
    if (!show) return;

    let modalId = null;
    if (show === "login") modalId = "loginModal";
    if (show === "register") modalId = "registerModal";
    if (show === "about") modalId = "aboutModal";

    if (modalId) {
      new bootstrap.Modal(document.getElementById(modalId)).show();
    }
  })();
</script>

{% block scripts_extra %}{% endblock %}

</body>
</html>
