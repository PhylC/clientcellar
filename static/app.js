const csvFilename = "clientcellar-recipient-template.csv";
const plannerState = {
  gift: null,
  event: null,
};
const accountState = {
  loading: true,
  authConfigured: false,
  userId: null,
  accessToken: null,
  loggedIn: false,
  email: null,
  plan: "free",
  subscriptionStatus: null,
  stripeCustomerId: null,
  stripeSubscriptionId: null,
  isPremium: false,
};
const authState = {
  configLoaded: false,
  configured: false,
  supabaseUrl: "",
  supabaseAnonKey: "",
};
const AUTH_SESSION_KEY = "clientcellar_auth_session";
const PREMIUM_TEST_KEYS = [
  "clientcellar_premium",
  "premium",
  "premiumMode",
  "isPremium",
  "upgraded",
  "pro",
  "clientcellar_plan",
];
const premiumAccountMessage = "Premium Brief Pack features require a completed one-off purchase.";

function looksLikeEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function clearLegacyPremiumTestState() {
  for (const key of PREMIUM_TEST_KEYS) {
    try {
      window.localStorage?.removeItem(key);
      window.sessionStorage?.removeItem(key);
    } catch (error) {
      // Storage can be unavailable in some private or restricted browser modes.
    }
  }
}

function accountBadgeClass() {
  return accountState.isPremium ? "account-badge account-badge-premium" : "account-badge account-badge-free";
}

function accountBadgeLabel() {
  return accountState.isPremium ? "Premium Brief Pack purchased" : "No Premium Brief Pack purchase linked";
}

function accountDisplayLabel() {
  if (!accountState.loggedIn) return "Not signed in";
  return accountState.email || "Signed in";
}

function mobileAccountActionLinks() {
  if (accountState.loading) {
    return [];
  }
  if (!accountState.loggedIn) {
    return [
      { label: "Sign in", href: "/sign-in" },
      { label: "View pricing", href: "/pricing" },
    ];
  }
  if (accountState.isPremium) {
    return [
      { label: "Account", href: "/account" },
      { label: "Logout", href: "/logout", action: "sign-out" },
    ];
  }
  return [
    { label: "View pricing", href: "/pricing" },
    { label: "Account", href: "/account" },
    { label: "Logout", href: "/logout", action: "sign-out" },
  ];
}

function accountLinkHtml(link, className = "account-link") {
  const action = link.action ? ` data-auth-action="${escapeHtml(link.action)}"` : "";
  return `<a class="${className}" href="${link.href}"${action}>${escapeHtml(link.label)}</a>`;
}

function accountInitials() {
  const value = accountState.email || "Account";
  const name = value.split("@")[0].replace(/[._-]+/g, " ").trim();
  const parts = name.split(/\s+/).filter(Boolean);
  if (!parts.length) return "A";
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function desktopAccountHtml(badge) {
  if (!accountState.loggedIn) {
    return `
      ${badge}
      <a class="account-link account-signin-link" href="/sign-in">Sign in</a>
    `;
  }
  const upgrade = accountState.isPremium
    ? ""
    : '<a class="account-dropdown-action primary" href="/gift-planner">Create free plan first</a>';
  return `
    ${badge}
    <details class="account-dropdown">
      <summary aria-label="Open account menu">
        <span class="account-avatar" aria-hidden="true">${escapeHtml(accountInitials())}</span>
        <span>Account</span>
        <span class="account-caret" aria-hidden="true">▾</span>
      </summary>
      <div class="account-dropdown-panel">
        <p class="account-dropdown-kicker">Signed in as</p>
        <p class="account-dropdown-email">${escapeHtml(accountState.email || "Signed in")}</p>
        <div class="account-dropdown-plan">
          <span>Premium Brief Pack</span>
          ${badge}
        </div>
        <div class="account-dropdown-actions">
          ${upgrade}
          <a class="account-dropdown-action" href="/account">Account</a>
          <a class="account-dropdown-action" href="/logout" data-auth-action="sign-out">Logout</a>
        </div>
      </div>
    </details>
  `;
}

function renderAccountStatus() {
  // The public header does not render account status for the one-off product flow.
  if (accountState.loading) {
    for (const target of document.querySelectorAll("[data-desktop-account-status], [data-mobile-account-panel], [data-mobile-account-badge]")) {
      target.hidden = true;
      target.innerHTML = "";
    }
    return;
  }

  const badge = `<span class="${accountBadgeClass()}">${accountBadgeLabel()}</span>`;
  for (const target of document.querySelectorAll("[data-desktop-account-status]")) {
    target.hidden = false;
    target.innerHTML = desktopAccountHtml(badge);
  }
  for (const target of document.querySelectorAll("[data-mobile-account-panel]")) {
    target.hidden = false;
    target.innerHTML = `
      <div class="mobile-account-status">
        <span class="account-label">${escapeHtml(accountDisplayLabel())}</span>
        ${badge}
      </div>
      <div class="account-links">
        ${mobileAccountActionLinks().map((link) => accountLinkHtml(link)).join("")}
      </div>
    `;
  }
  for (const target of document.querySelectorAll("[data-mobile-account-badge]")) {
    target.hidden = false;
    target.innerHTML = badge;
  }
}

async function loadAuthConfig() {
  if (authState.configLoaded) return authState;
  try {
    const response = await fetch("/api/auth-config", { headers: { "Accept": "application/json" } });
    const data = response.ok ? await response.json() : {};
    authState.configured = Boolean(data.configured && data.supabaseUrl && data.supabaseAnonKey);
    authState.supabaseUrl = data.supabaseUrl || "";
    authState.supabaseAnonKey = data.supabaseAnonKey || "";
  } catch (error) {
    authState.configured = false;
  }
  authState.configLoaded = true;
  accountState.authConfigured = authState.configured;
  return authState;
}

function getAuthSession() {
  try {
    const raw = window.localStorage?.getItem(AUTH_SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (!session?.access_token) return null;
    if (session.expires_at && Date.now() >= Number(session.expires_at) * 1000) {
      clearAuthSession();
      return null;
    }
    return session;
  } catch (error) {
    return null;
  }
}

function saveAuthSession(data) {
  if (!data?.access_token) return null;
  const expiresIn = Number(data.expires_in || 3600);
  const session = {
    access_token: data.access_token,
    refresh_token: data.refresh_token || null,
    expires_at: data.expires_at || Math.floor(Date.now() / 1000) + expiresIn,
    user: data.user || null,
  };
  try {
    window.localStorage?.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
  } catch (error) {
    // A signed-in session may not persist if browser storage is blocked.
  }
  return session;
}

function clearAuthSession() {
  try {
    window.localStorage?.removeItem(AUTH_SESSION_KEY);
  } catch (error) {
    // Ignore restricted storage.
  }
}

async function supabaseAuthRequest(path, options = {}, accessToken = null) {
  await loadAuthConfig();
  if (!authState.configured) {
    throw new Error("Account login is not configured yet.");
  }
  const headers = {
    "apikey": authState.supabaseAnonKey,
    "Content-Type": "application/json",
    "Accept": "application/json",
    ...(options.headers || {}),
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const response = await fetch(`${authState.supabaseUrl}${path}`, {
    ...options,
    headers,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error_description || data.msg || data.message || "Account request failed.");
  }
  return data;
}

async function signInWithPassword(email, password) {
  const data = await supabaseAuthRequest("/auth/v1/token?grant_type=password", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return saveAuthSession(data);
}

async function signUpWithPassword(email, password) {
  const data = await supabaseAuthRequest("/auth/v1/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (data.access_token) {
    return saveAuthSession(data);
  }
  return null;
}

async function signOut() {
  const session = getAuthSession();
  if (session?.access_token && authState.configured) {
    try {
      await supabaseAuthRequest("/auth/v1/logout", { method: "POST", body: "{}" }, session.access_token);
    } catch (error) {
      // The local session still needs clearing even if Supabase logout is unavailable.
    }
  }
  clearAuthSession();
  accountState.loading = false;
  accountState.loggedIn = false;
  accountState.userId = null;
  accountState.accessToken = null;
  accountState.email = null;
  accountState.plan = "free";
  accountState.subscriptionStatus = null;
  accountState.stripeCustomerId = null;
  accountState.stripeSubscriptionId = null;
  accountState.isPremium = false;
  renderAccountStatus();
}

async function checkAccountStatus() {
  renderAccountStatus();
  await loadAuthConfig();
  const session = getAuthSession();
  if (!authState.configured || !session?.access_token) {
    accountState.loading = false;
    accountState.loggedIn = false;
    accountState.userId = null;
    accountState.accessToken = null;
    accountState.email = null;
    accountState.plan = "free";
    accountState.subscriptionStatus = null;
    accountState.stripeCustomerId = null;
    accountState.stripeSubscriptionId = null;
    accountState.isPremium = false;
    renderAccountStatus();
    renderAccountPage();
    return;
  }
  try {
    const response = await fetch("/api/premium-status", {
      headers: {
        "Accept": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
    });
    const data = response.ok ? await response.json() : {};
    accountState.loading = false;
    accountState.loggedIn = Boolean(data.loggedIn || data.authenticated);
    accountState.userId = data.userId || session.user?.id || null;
    accountState.accessToken = accountState.loggedIn ? session.access_token : null;
    accountState.email = data.email || null;
    accountState.plan = typeof data.plan === "string" ? data.plan : "free";
    accountState.subscriptionStatus = data.subscription_status || null;
    accountState.stripeCustomerId = data.stripe_customer_id || null;
    accountState.stripeSubscriptionId = data.stripe_subscription_id || null;
    accountState.isPremium = Boolean(
      accountState.loggedIn
      && (accountState.plan === "premium" || ["active", "trialing", "paid_one_off"].includes(accountState.subscriptionStatus) || data.subscription_active)
      && (data.isPremium || data.premium || data.subscription_active)
    );
    if (!accountState.loggedIn) clearAuthSession();
  } catch (error) {
    clearAuthSession();
    accountState.loading = false;
    accountState.loggedIn = false;
    accountState.userId = null;
    accountState.accessToken = null;
    accountState.email = null;
    accountState.plan = "free";
    accountState.subscriptionStatus = null;
    accountState.stripeCustomerId = null;
    accountState.stripeSubscriptionId = null;
    accountState.isPremium = false;
  }
  renderAccountStatus();
  renderSignedInAuthCard();
  renderAccountPage();
}

function formToJson(form) {
  const data = new FormData(form);
  const payload = {};
  for (const [key, value] of data.entries()) {
    payload[key] = value;
  }

  for (const checkbox of form.querySelectorAll('input[type="checkbox"]')) {
    payload[checkbox.name] = checkbox.checked;
  }

  for (const number of form.querySelectorAll('input[type="number"]')) {
    payload[number.name] = Number(number.value);
  }

  for (const [key, value] of Object.entries(payload)) {
    if (value === "") {
      delete payload[key];
    }
  }

  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function list(items) {
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function fallbackSupplierData(type) {
  if (type === "event") {
    return [
      {
        name: "Virtual tasting host",
        category: "Tasting events",
        why: "Useful for remote teams or client sessions where tasting packs need to be sent to each attendee.",
        budget_fit: "Usually priced per attendee plus delivery. Confirm format, kit contents and host availability.",
      },
      {
        name: "Wine tasting event provider",
        category: "Event supplier",
        why: "Useful for hosted in-person events, client entertainment or team sessions with a structured tasting.",
        budget_fit: "Confirm host fee, venue needs, glassware, VAT, food pairing and any minimum guest numbers.",
      },
      {
        name: "Wine merchant events team",
        category: "Wine merchant",
        why: "Useful when you want wine advice, bottle supply and event support from the same buying route.",
        budget_fit: "Ask for package options by headcount and confirm delivery, substitutions and lead times.",
      },
    ];
  }

  return [
    {
      name: "Premium wine merchant",
      category: "Wine merchant",
      why: "Useful for client gifts, mixed cases and advice-led recommendations by budget and occasion.",
      budget_fit: "Often suitable from around £25-£150 per recipient. Confirm current pricing directly.",
    },
    {
      name: "Corporate hamper supplier",
      category: "Hamper supplier",
      why: "Useful when recipient tastes vary or you want food, alcohol-free options and presentation handled together.",
      budget_fit: "Often useful from around £40+ per recipient. Confirm contents, substitutions and delivery fees.",
    },
    {
      name: "Corporate gifting supplier",
      category: "Corporate gifting",
      why: "Useful for larger recipient lists, message inserts, fulfilment support and multi-address delivery.",
      budget_fit: "Ask about minimum order quantities, VAT, delivery costs and personalisation charges.",
    },
  ];
}

function supplierRecommendationsFromPlan(plan = {}) {
  const candidates = [
    plan.suppliers,
    plan.supplier_recommendations,
    plan.suggested_suppliers,
    plan.supplier_shortlist,
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length) return candidate;
  }
  return [];
}

function supplierUrlHtml(supplier) {
  const url = supplier.tracked_url || supplier.url || supplier.affiliate_url || supplier.website_url || "";
  if (!url) {
    return '<p><a class="button secondary" href="/suppliers">View supplier directory</a></p><p class="small-note">Use this as a supplier type rather than a direct supplier link.</p>';
  }
  const isExternal = /^https?:\/\//i.test(url);
  const target = isExternal ? ' target="_blank"' : "";
  const rel = isExternal ? ' rel="sponsored noopener"' : "";
  return `<p><a class="button secondary" href="${escapeHtml(url)}"${target}${rel}>View supplier</a></p>`;
}

function renderSuppliers(suppliers = [], type = "gift") {
  const supplierList = Array.isArray(suppliers) && suppliers.length ? suppliers : fallbackSupplierData(type);
  return supplierList
    .map((supplier) => {
      const category = supplier.category || supplier.best_for || supplier.supplier_type || "Supplier route";
      const fitReason = supplier.fit_reason || supplier.why || supplier.reason || "Potentially useful for this brief.";
      const budgetNote = supplier.budget_note || supplier.budget_fit || supplier.price_note || "Confirm live pricing, delivery charges and availability directly.";
      const bestFor = supplier.best_for && supplier.best_for !== category ? `<p><strong>Best for:</strong> ${escapeHtml(supplier.best_for)}</p>` : "";
      return `
        <article class="supplier-card">
          <h3>${escapeHtml(supplier.name)}</h3>
          <p><strong>${escapeHtml(category)}</strong></p>
          ${bestFor}
          ${supplier.relationship_label ? `<p><strong>${escapeHtml(supplier.relationship_label)}</strong></p>` : ""}
          <p>${escapeHtml(fitReason)}</p>
          <p>${escapeHtml(budgetNote)}</p>
          ${supplierUrlHtml(supplier)}
          <p class="small-note">${escapeHtml(supplier.disclosure_note || "Some supplier links may be affiliate or tracked links.")} <a href="/affiliate-disclosure">See Affiliate Disclosure.</a></p>
        </article>
      `;
    })
    .join("");
}

function renderBudgetRows(rows) {
  return `
    <div class="comparison-table">
      ${rows
        .map(
          (row) => `
            <div>
              <strong>${escapeHtml(row.label)}</strong>
              <span>${escapeHtml(row.amount)}</span>
              <p>${escapeHtml(row.note)}</p>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderPremiumComparison(items) {
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.supplier || item.supplier_type || "Supplier")}</td>
          <td>${escapeHtml(item.product_package || item.best_for || item.fit || "To quote")}</td>
          <td>${escapeHtml(item.unit_price || "To quote")}</td>
          <td>${escapeHtml(item.delivery_cost || "To quote")}</td>
          <td>${escapeHtml(item.personalisation || "Confirm")}</td>
          <td>${escapeHtml(item.lead_time || "Confirm")}</td>
          <td>${escapeHtml(item.pros || item.strengths || "")}</td>
          <td>${escapeHtml(item.risks || item.watchouts || "")}</td>
          <td>${escapeHtml(item.decision || "To decide")}</td>
        </tr>
      `
    )
    .join("");
  return `
    <div class="table-scroll">
      <table class="pack-table">
        <thead><tr><th>Supplier</th><th>Product / package</th><th>Unit price</th><th>Delivery cost</th><th>Personalisation</th><th>Lead time</th><th>Pros</th><th>Risks / watchouts</th><th>Decision</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderKeyValueTable(data) {
  return `
    <div class="table-scroll">
      <table class="pack-table">
        <tbody>
          ${Object.entries(data || {})
            .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(value)}</td></tr>`)
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderScorecard(rows) {
  return `
    <div class="table-scroll">
      <table class="pack-table">
        <thead><tr><th>Criteria</th><th>Score</th><th>Notes</th></tr></thead>
        <tbody>
          ${rows
            .map((row) => `<tr><td>${escapeHtml(row.criterion)}</td><td>${escapeHtml(row.score)}</td><td>${escapeHtml(row.notes)}</td></tr>`)
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPremiumPreview(preview, type) {
  const email = `${preview.supplier_enquiry_email.subject}\n\n${preview.supplier_enquiry_email.body}`;
  const packLabel = type === "gift" ? "Gift Premium Brief Pack" : "Event Premium Brief Pack";
  const csvButton =
    type === "gift"
      ? `<button class="button secondary" type="button" data-download-preview-csv>Download recipient CSV</button>`
      : "";
  const infoTemplate = preview.recipient_csv_template || preview.attendee_info_template || "";
  return `
    <div class="premium-preview premium-doc">
      <header class="premium-doc-header">
        <div>
          <p class="eyebrow">ClientCellar Premium Brief Pack</p>
          <h2>${escapeHtml(packLabel)}</h2>
          <p>Copy-ready business documents for suppliers, finance/procurement and internal stakeholders.</p>
        </div>
        <div class="premium-doc-actions">
          <button class="button secondary" type="button" data-print-plan>Print / save as PDF</button>
          <button class="button secondary" type="button" data-copy-preview-email>Copy enquiry email</button>
          ${csvButton}
        </div>
      </header>
      <section class="result-block">
        <h3>1. Executive summary</h3>
        <p>${escapeHtml(preview.executive_summary)}</p>
      </section>
      <section class="result-block">
        <h3>2. Decision recommendation</h3>
        ${renderKeyValueTable(preview.decision_recommendation)}
      </section>
      <section class="result-block">
        <h3>3. Supplier quote comparison table</h3>
        ${renderPremiumComparison(preview.supplier_comparison)}
      </section>
      <section class="result-block">
        <h3>4. Budget breakdown</h3>
        ${renderBudgetRows(preview.budget_breakdown)}
      </section>
      <section class="result-block">
        <h3>5. Supplier brief data</h3>
        <button class="button secondary small" type="button" data-copy-target="[data-supplier-ready-brief]">Copy brief</button>
        <div data-supplier-ready-brief>
          ${renderKeyValueTable(preview.supplier_brief)}
        </div>
      </section>
      <section class="result-block">
        <h3>6. Supplier enquiry email</h3>
        <button class="button secondary small" type="button" data-copy-target="[data-preview-email]">Copy email</button>
        <pre class="email-preview" data-preview-email>${escapeHtml(email)}</pre>
      </section>
      <section class="result-block">
        <h3>7. Internal approval note</h3>
        <button class="button secondary small" type="button" data-copy-target="[data-approval-note]">Copy approval note</button>
        <p data-approval-note>${escapeHtml(preview.internal_approval_note)}</p>
      </section>
      <section class="result-block">
        <h3>8. Next steps checklist</h3>
        ${list(preview.timeline_action_plan)}
      </section>
      <section class="result-block">
        <h3>Supplier questions checklist</h3>
        ${list(preview.supplier_questions_checklist)}
      </section>
      ${type === "event" && preview.event_run_of_show ? `<section class="result-block"><h3>Event run-of-show</h3>${list(preview.event_run_of_show)}</section>` : ""}
      ${type === "event" && preview.internal_invite_copy ? `<section class="result-block"><h3>Internal invite copy</h3><button class="button secondary small" type="button" data-copy-target="[data-internal-invite-copy]">Copy invite</button><pre class="email-preview" data-internal-invite-copy>${escapeHtml(preview.internal_invite_copy)}</pre></section>` : ""}
      <section class="result-block">
        <h3>${type === "gift" ? "Gift message bank" : "Message variants"}</h3>
        ${preview.message_variants
          .map((variant, index) => `<div class="message-row"><p><strong>${escapeHtml(variant.tone)}:</strong> ${escapeHtml(variant.message)}</p><button class="button secondary small" type="button" data-copy-literal="${escapeHtml(variant.message)}">Copy</button></div>`)
          .join("")}
      </section>
      <section class="result-block">
        <h3>${type === "gift" ? "Recipient CSV template" : "Attendee info template"}</h3>
        <button class="button secondary small" type="button" data-download-preview-csv>Download CSV</button>
        <pre data-preview-csv>${escapeHtml(infoTemplate)}</pre>
      </section>
      <section class="result-block">
        <h3>Risk and suitability checklist</h3>
        ${list(preview.risk_checklist)}
        ${preview.alcohol_free_options_note ? `<p class="small-note">${escapeHtml(preview.alcohol_free_options_note)}</p>` : ""}
      </section>
      <section class="result-block">
        <h3>Internal Slack / Teams update</h3>
        <button class="button secondary small" type="button" data-copy-target="[data-internal-update]">Copy update</button>
        <p data-internal-update>${escapeHtml(preview.internal_update)}</p>
      </section>
      <section class="result-block">
        <h3>Decision scorecard</h3>
        ${renderScorecard(preview.decision_scorecard)}
      </section>
      <section class="result-block">
        <h3>Prepared by ClientCellar</h3>
        <p>This document is a planning aid for supplier conversations and internal approval. It does not verify supplier pricing, stock, availability, delivery or suitability.</p>
      </section>
      <section class="result-block disclaimer-block">
        <h3>Disclaimer</h3>
        <p>${escapeHtml(preview.disclaimer)}</p>
        <p class="small-note">Some supplier links may be affiliate or tracked links. Confirm availability, pricing and delivery directly. <a href="/affiliate-disclosure">Affiliate Disclosure</a>.</p>
      </section>
      ${renderLeadForm("premium_pack", "premium-pack-preview", type)}
    </div>
  `;
}

function renderLeadForm(interestedIn, sourcePage, contextType = "") {
  return `
    <form class="lead-capture-form planner-form" data-lead-form data-interested-in="${interestedIn}" data-source-page="${sourcePage}" data-context-type="${contextType}">
      <h2>Want help turning this into working documents?</h2>
      <p>Leave your details if you want support with a Premium Brief Pack, supplier shortlist or corporate gifting brief.</p>
      <div class="form-row">
        <label>Name
          <input name="name" required>
        </label>
        <label>Work email
          <input name="email" type="email" required>
        </label>
      </div>
      <label>Company
        <input name="company">
      </label>
      <label>Deadline optional
        <input name="deadline" placeholder="e.g. 12 December">
      </label>
      <label>Message optional
        <textarea name="message" maxlength="3000" placeholder="Anything useful about the brief, suppliers or timing"></textarea>
      </label>
      <label class="consent-line">
        <input type="checkbox" name="consent_to_contact" required>
        <span>I agree that ClientCellar can contact me about this enquiry. I understand this is planning guidance and supplier availability must be confirmed directly.</span>
      </label>
      <button class="button primary full" type="submit">Send enquiry</button>
      <p class="form-status" role="status"></p>
    </form>
  `;
}

function renderPlan(plan, type) {
  const eventExtras =
    type === "event"
      ? `
        <div class="result-block">
          <h2>Event structure direction</h2>
          ${list(plan.event_structure)}
        </div>
      `
      : `
        <div class="result-block">
          <h2>Recommended gift types</h2>
          ${list(plan.recommended_gift_types)}
        </div>
      `;

  return `
    <article class="plan-result">
      <p class="eyebrow">Generated plan</p>
      <h2>${escapeHtml(plan.headline)}</h2>
      <p class="result-meta">${escapeHtml(plan.summary)}</p>
      <div class="result-block">
        <h2>1. Recommended direction</h2>
        <p>${escapeHtml(plan.recommended_direction || plan.recommended_strategy || plan.recommended_format)}</p>
      </div>
      <div class="result-block">
        <h2>2. Budget guidance</h2>
        <p><strong>Estimated budget:</strong> ${escapeHtml(plan.estimated_total_budget)}</p>
        ${list(plan.budget_guidance || [])}
      </div>
      <div class="result-block">
        <h2>3. Supplier category to approach</h2>
        <p>${escapeHtml(plan.supplier_category || "Corporate wine supplier")}</p>
      </div>
      <div class="result-block supplier-suggestions">
        <h2>Suggested suppliers to check</h2>
        <p>These suppliers may fit your brief. Confirm live pricing, stock, delivery dates and suitability directly.</p>
        <div class="supplier-card-grid">
          ${renderSuppliers(supplierRecommendationsFromPlan(plan), type)}
        </div>
      </div>
      ${eventExtras}
      <div class="result-block">
        <h2>4. Suitability notes</h2>
        ${list(plan.what_to_avoid)}
      </div>
      <div class="result-block">
        <h2>5. Simple next steps</h2>
        ${list((plan.next_steps || []).slice(0, 4))}
      </div>
      <div class="premium-cta-card">
        <p class="eyebrow">Premium Brief Pack</p>
        <h2>Want the documents to actually send?</h2>
        <p>Your free plan gives you supplier suggestions and direction. Premium creates the working pack: supplier enquiry email, quote comparison table, budget breakdown, approval summary and risk checklist.</p>
        <ul class="feature-list">
          <li>Copy-ready supplier email</li>
          <li>Quote comparison table</li>
          <li>Internal approval summary</li>
          <li>Budget breakdown</li>
          <li>Saved download link</li>
        </ul>
        <div class="result-actions">
          <button class="button primary" type="button" data-pack-checkout data-pack-type="${type}">Upgrade this plan to Premium Brief Pack</button>
          <a class="button secondary" href="${type === "gift" ? "/gift-planner" : "/event-planner"}">Continue with free plan</a>
        </div>
        <details class="premium-detail">
          <summary>Other next steps</summary>
          <div class="button-row">
            <a class="button secondary small" href="/contact?interest=${type === "gift" ? "gift-planning" : "event-planning"}">Send enquiry / request help</a>
            <a class="button secondary small" href="/suppliers">${type === "gift" ? "View supplier directory" : "View tasting suppliers"}</a>
          </div>
        </details>
        <div data-premium-preview></div>
      </div>
      ${renderLeadForm(type === "gift" ? "gifts" : "events", `${type}-planner-results`, type)}
      <div class="result-block">
        <h2>Disclaimer</h2>
        <p>${escapeHtml(plan.disclaimer)}</p>
      </div>
    </article>
  `;
}
function leadPayloadFromForm(form) {
  const payload = formToJson(form);
  payload.interested_in = form.dataset.interestedIn || payload.interested_in || "other";
  payload.source_page = form.dataset.sourcePage || window.location.pathname;
  payload.consent_to_contact = Boolean(payload.consent_to_contact);

  const type = form.dataset.contextType || (payload.interested_in === "events" ? "event" : "gift");
  const state = plannerState[type];
  if (state && !payload.planner_input && form.closest(".results-panel")) {
    payload.planner_input = state.input;
    payload.planner_output = state.output;
    if (state.input.recipient_count) payload.recipient_count = state.input.recipient_count;
    if (state.input.attendee_count) payload.recipient_count = state.input.attendee_count;
    if (state.input.budget_per_recipient) payload.budget_per_recipient = state.input.budget_per_recipient;
    if (state.input.budget_per_person) payload.budget_per_recipient = state.input.budget_per_person;
    if (state.input.occasion) payload.occasion = state.input.occasion;
    if (state.input.delivery_deadline) payload.deadline = payload.deadline || state.input.delivery_deadline;
    if (state.input.date) payload.deadline = payload.deadline || state.input.date;
  }

  return payload;
}

function errorMessageFromResponse(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail) && data.detail.length) {
    return data.detail.map((item) => item.msg).join(" ");
  }
  return data.message || "Sorry, your enquiry could not be saved.";
}

async function submitLeadForm(form) {
  const status = form.querySelector(".form-status") || document.getElementById("contact-status");
  status.textContent = "Sending...";
  try {
    const response = await fetch("/api/lead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(leadPayloadFromForm(form)),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(errorMessageFromResponse(data));
    }
    status.textContent = "Thanks — your enquiry has been saved. We’ll use the details you shared to understand the request.";
    form.reset();
  } catch (error) {
    status.textContent = error.message;
  }
}

async function submitPlan(form, type) {
  const target = document.getElementById(`${type}-results`);
  const endpoint = type === "gift" ? "/api/gift-plan" : "/api/event-plan";
  const submitButton = form.querySelector('button[type="submit"]');
  const originalLabel = submitButton?.dataset.submitLabel || submitButton?.textContent || "Create plan";
  if (!form.reportValidity()) return;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = submitButton.dataset.loadingLabel || "Creating your plan...";
  }
  target.innerHTML = '<div class="loading">Creating your plan...</div>';

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formToJson(form)),
    });
    if (!response.ok) {
      throw new Error("Planner request failed");
    }
    const plan = await response.json();
    plannerState[type] = { input: formToJson(form), output: plan };
    target.innerHTML = renderPlan(plan, type);
    target.dataset.csv = plan.recipient_csv_template || "";
  } catch (error) {
    target.innerHTML = '<div class="empty-state">Sorry, the plan could not be generated. Check the form and try again. If the issue continues, refresh the page.</div>';
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  }
}

async function createCheckoutSession(packType, button) {
  const original = button.textContent;
  button.textContent = "Starting checkout...";
  button.disabled = true;
  const state = plannerState[packType];
  const messageTarget = button.closest(".premium-cta-card")?.querySelector("[data-premium-preview]");
  const plannerUrl = packType === "event" ? "/event-planner?message=create-plan-first" : "/gift-planner?message=create-plan-first";
  if (!state?.input || !state?.output) {
    if (messageTarget) {
      messageTarget.innerHTML = `<p class="small-note">Create a free plan first, then you can upgrade it to a Premium Brief Pack.</p>`;
    }
    button.textContent = original;
    button.disabled = false;
    window.location.href = plannerUrl;
    return;
  }
  if (accountState.loading) {
    await checkAccountStatus();
  }
  const session = getAuthSession();
  const accessToken = session?.access_token || accountState.accessToken;
  let checkoutEmail = accountState.email || "";
  if (!checkoutEmail) {
    checkoutEmail = window.prompt("Enter the email address we should use to save your Premium Brief Pack link.") || "";
  }
  checkoutEmail = checkoutEmail.trim();
  if (!looksLikeEmail(checkoutEmail)) {
    if (messageTarget) {
      messageTarget.innerHTML = `<p class="small-note">Please enter a valid email so we can save your Premium Brief Pack link.</p>`;
    }
    button.textContent = original;
    button.disabled = false;
    return;
  }
  try {
    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const response = await fetch("/api/stripe/create-checkout-session", {
      method: "POST",
      headers,
      body: JSON.stringify({
        pack_type: packType,
        email: checkoutEmail,
        auth_user_id: accountState.userId,
        planner_input: state?.input || null,
        planner_output: state?.output || null,
      }),
    });
    const data = await response.json();
    if (response.status === 400 && data.redirect_url) {
      window.location.href = data.redirect_url;
      return;
    }
    if (response.status === 400 && data.requires_email) {
      if (messageTarget) {
        messageTarget.innerHTML = `<p class="small-note">${escapeHtml(data.detail || "Please enter an email before checkout.")}</p>`;
      }
      return;
    }
    if (data.enabled && (data.url || data.checkout_url)) {
      window.location.href = data.url || data.checkout_url;
      return;
    }
    if (response.status === 401) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/sign-in?message=upgrade&next=${next}`;
      return;
    }
    if (messageTarget) {
      messageTarget.innerHTML = `<p class="small-note">${escapeHtml(data.message || data.detail || "Checkout could not be started. Your generated plan is still available on this page.")}</p>`;
    }
  } catch (error) {
    if (messageTarget) {
      messageTarget.innerHTML = `<p class="small-note">Checkout could not be started. Your generated plan is still available on this page.</p>`;
    }
  } finally {
    button.textContent = original;
    button.disabled = false;
  }
}

function copyText(text, button) {
  navigator.clipboard.writeText(text).then(() => {
    const original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => {
      button.textContent = original;
    }, 1400);
  });
}

function downloadCsv(text) {
  const blob = new Blob([`${text}\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = csvFilename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function recordPackDownload(packToken) {
  if (!packToken) return;
  try {
    await fetch(`/api/premium-pack/${encodeURIComponent(packToken)}/download`, { method: "POST" });
  } catch (error) {
    // Download tracking is best-effort and should never block the user's file.
  }
}

function bindPremiumPackDownloads() {
  const documentEl = document.querySelector("[data-premium-pack-document]");
  if (!documentEl) return;
  const packToken = documentEl.dataset.packToken || "";
  const title = documentEl.dataset.packTitle || "ClientCellar Premium Brief Pack";
  const button = document.querySelector("[data-download-pack-text]");
  if (!button) return;
  button.addEventListener("click", async () => {
    const text = documentEl.innerText.trim();
    const blob = new Blob([`${text}\n`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "clientcellar-premium-brief-pack"}.txt`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    await recordPackDownload(packToken);
  });
}

function bindPackAccessForm() {
  const form = document.querySelector("[data-pack-access-form]");
  if (!form) return;
  const status = form.querySelector("[data-pack-access-status]");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const original = button?.textContent || "Send access link";
    if (button) {
      button.disabled = true;
      button.textContent = "Sending...";
    }
    if (status) status.textContent = "";
    try {
      const response = await fetch("/api/premium-packs/request-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToJson(form)),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessageFromResponse(data));
      if (status) {
        status.textContent = "Check your email. If that address has saved Premium Brief Packs, we’ll send secure access links shortly.";
      }
      form.reset();
    } catch (error) {
      if (status) status.textContent = "Please check the email address and try again.";
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original;
      }
    }
  });
}

function bindPlannerForms() {
  const message = new URLSearchParams(window.location.search).get("message");
  if (message === "create-plan-first") {
    const hero = document.querySelector(".planner-hero");
    if (hero) {
      const notice = document.createElement("div");
      notice.className = "notice compact-notice";
      notice.textContent = "Create a free plan first, then you can upgrade it to a Premium Brief Pack.";
      hero.append(notice);
    }
  }

  for (const form of document.querySelectorAll("[data-plan-form]")) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitPlan(form, form.dataset.planForm);
    });
  }
}

function renderAccountPage(message = "") {
  const target = document.querySelector("[data-account-page]");
  if (!target) return;
  if (!authState.configured) {
    target.innerHTML = `
      <div class="empty-state">
        <h2>Sign in is not configured yet</h2>
        <p>Add Supabase environment variables to enable sign in. The Free Planner and one-off checkout flow can still be used where configured.</p>
        <p><a class="button secondary" href="/pricing">View pricing</a></p>
      </div>
    `;
    return;
  }
  if (accountState.loading) {
    target.innerHTML = `
      <div class="empty-state">
        <h2>Loading sign-in details</h2>
        <p>We are checking whether this browser is signed in.</p>
      </div>
    `;
    return;
  }
  if (!accountState.loggedIn) {
    target.innerHTML = `
      <div class="account-summary">
        <h2>Not signed in</h2>
        <p>${escapeHtml(message || "You can use the Free Planner without signing in. Sign in is only needed where checkout needs to link details to your email.")}</p>
        <div class="button-row">
          <a class="button primary" href="/sign-in">Sign in</a>
          <a class="button secondary" href="/pricing">View pricing</a>
        </div>
      </div>
    `;
    return;
  }
  const purchaseText = accountState.isPremium ? "Premium Brief Pack purchased" : "No Premium Brief Pack purchase linked";
  const buyLink = accountState.isPremium ? "" : '<a class="button primary" href="/gift-planner">Create free plan first</a>';
  target.innerHTML = `
    <div class="account-summary">
      <h2>${escapeHtml(accountState.email || "Signed in")}</h2>
      <div class="account-summary-row"><strong>Email</strong><span>${escapeHtml(accountState.email || "Signed in")}</span></div>
      <div class="account-summary-row"><strong>Premium Brief Pack</strong><span>${escapeHtml(purchaseText)}</span></div>
      <div class="account-summary-row"><strong>Checkout record</strong><span>${escapeHtml(accountState.subscriptionStatus || "No completed one-off checkout linked here")}</span></div>
      <div class="button-row">
        ${buyLink}
        <a class="button secondary" href="/logout" data-auth-action="sign-out">Sign out</a>
      </div>
    </div>
  `;
}

function authMessageFromQuery() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("message") === "upgrade") {
    return "Create an account first if you want checkout details linked to your email.";
  }
  if (params.get("signed_out") === "1") {
    return "You are now signed out.";
  }
  return "";
}

function bindAuthForms() {
  const card = document.querySelector("[data-auth-card]");
  if (!card) return;
  const form = card.querySelector("[data-auth-form]");
  const submit = card.querySelector("[data-auth-submit]");
  const status = card.querySelector("[data-auth-status]");
  let mode = "signin";

  const setStatus = (message, isError = false) => {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("error", isError);
  };

  const setMode = (nextMode) => {
    mode = nextMode;
    for (const tab of card.querySelectorAll("[data-auth-mode]")) {
      tab.classList.toggle("active", tab.dataset.authMode === mode);
    }
    if (submit) submit.textContent = mode === "signin" ? "Sign in" : "Create account";
    const password = form?.querySelector('[name="password"]');
    if (password) password.autocomplete = mode === "signin" ? "current-password" : "new-password";
    setStatus("");
  };

  loadAuthConfig().then(() => {
    if (!authState.configured) {
      setStatus("Sign in is not configured yet.", true);
      for (const field of form?.querySelectorAll("input, button") || []) field.disabled = true;
    } else {
      setStatus(authMessageFromQuery());
    }
  });

  for (const tab of card.querySelectorAll("[data-auth-mode]")) {
    tab.addEventListener("click", () => setMode(tab.dataset.authMode));
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = form.querySelector('[name="email"]').value.trim();
    const password = form.querySelector('[name="password"]').value;
    if (!email || !password) {
      setStatus("Please enter an email and password.", true);
      return;
    }
    if (password.length < 6) {
      setStatus("Password must be at least 6 characters.", true);
      return;
    }
    submit.disabled = true;
    submit.textContent = mode === "signin" ? "Signing in..." : "Creating account...";
    try {
      const session = mode === "signin"
        ? await signInWithPassword(email, password)
        : await signUpWithPassword(email, password);
      if (session) {
        await checkAccountStatus();
        const next = new URLSearchParams(window.location.search).get("next") || "/";
        window.location.href = next;
      } else {
        setStatus("Check your email to confirm your account.");
      }
    } catch (error) {
      setStatus(mode === "signin" ? "Could not sign in. Check your email and password." : "Could not create account. Try again.", true);
    } finally {
      submit.disabled = false;
      submit.textContent = mode === "signin" ? "Sign in" : "Create account";
    }
  });
}

function renderSignedInAuthCard() {
  const card = document.querySelector("[data-auth-card]");
  if (!card || accountState.loading || !accountState.loggedIn) return;
  const purchaseText = accountState.isPremium ? "Premium Brief Pack purchased" : "No Premium Brief Pack purchase linked";
  const buyLink = accountState.isPremium ? "" : '<a class="button primary" href="/gift-planner">Create free plan first</a>';
  card.innerHTML = `
    <div class="account-summary">
      <h2>Your sign-in details</h2>
      <p>${escapeHtml(accountState.email || "Signed in")}</p>
      <div class="account-summary-row"><strong>Premium Brief Pack</strong><span>${escapeHtml(purchaseText)}</span></div>
      <div class="account-summary-row"><strong>Checkout record</strong><span>${escapeHtml(accountState.subscriptionStatus || "No completed one-off checkout linked here")}</span></div>
      <div class="button-row">
        ${buyLink}
        <a class="button secondary" href="/account">Sign-in details</a>
        <a class="button secondary" href="/logout" data-auth-action="sign-out">Sign out</a>
      </div>
    </div>
  `;
}

function bindAccountPage() {
  const page = document.querySelector("[data-account-page]");
  if (!page) return;
  loadAuthConfig().then(async () => {
    if (page.dataset.signOutOnLoad === "true") {
      await signOut();
      renderAccountPage("You are now signed out.");
      window.history.replaceState({}, "", "/sign-in?signed_out=1");
      window.location.href = "/sign-in?signed_out=1";
      return;
    }
    renderAccountPage();
  });
}

function bindResultActions() {
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".account-dropdown")) {
      for (const dropdown of document.querySelectorAll(".account-dropdown[open]")) {
        dropdown.removeAttribute("open");
      }
    }

    const authAction = event.target.closest("[data-auth-action]");
    if (authAction?.dataset.authAction === "sign-out") {
      event.preventDefault();
      signOut().then(() => {
        window.location.href = "/sign-in?signed_out=1";
      });
      return;
    }

    const button = event.target.closest("button");
    if (!button) return;

    const panel = button.closest(".results-panel");
    if (button.matches("[data-copy-email]")) {
      copyText(panel.querySelector("[data-email]").textContent, button);
    }
    if (button.matches("[data-copy-invite]")) {
      copyText(panel.querySelector("[data-invite]").textContent, button);
    }
    if (button.matches("[data-download-csv]")) {
      downloadCsv(panel.dataset.csv);
    }
    if (button.matches("[data-print-plan]")) {
      window.print();
    }
    if (button.matches("[data-preview-premium]")) {
      const panel = button.closest(".premium-cta-card");
      const target = panel?.querySelector("[data-premium-preview]");
      if (target) target.innerHTML = `<p class="small-note">${premiumAccountMessage}</p>`;
    }
    if (button.matches("[data-copy-preview-email]")) {
      const preview = button.closest(".premium-preview");
      if (preview) copyText(preview.querySelector("[data-preview-email]").textContent, button);
    }
    if (button.matches("[data-copy-target]")) {
      const root = button.closest(".premium-preview") || document;
      const target = root.querySelector(button.dataset.copyTarget);
      if (target) copyText(target.textContent, button);
    }
    if (button.matches("[data-copy-literal]")) {
      copyText(button.dataset.copyLiteral, button);
    }
    if (button.matches("[data-download-preview-csv]")) {
      const preview = button.closest(".premium-preview");
      if (preview) downloadCsv(preview.querySelector("[data-preview-csv]").textContent);
    }
    if (button.matches("[data-pack-checkout]")) {
      createCheckoutSession(button.dataset.packType || "gift", button);
    }
  });
}

function bindMobileMenu() {
  const header = document.querySelector(".site-header");
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.getElementById("main-nav");
  if (!header || !toggle) return;

  const closeMenu = () => {
    header.classList.remove("menu-open");
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.addEventListener("click", () => {
    const isOpen = header.classList.toggle("menu-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  nav?.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });
}

function bindContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) return;

  const interest = new URLSearchParams(window.location.search).get("interest");
  const select = form.querySelector('[name="interested_in"]');
  const note = document.getElementById("contact-note");
  const interestMap = {
    "premium-pack": "premium_pack",
    "premium-pack-support": "premium_pack",
    supplier: "supplier_intro",
    "supplier_intro": "supplier_intro",
    "gift-planning": "gifts",
    "event-planning": "events",
  };
  if (interestMap[interest] && select) {
    select.value = interestMap[interest];
  }
  if (interest === "premium-pack-support" && note) {
    note.textContent = "Need help with payment or Premium Brief Pack access? Please include the email used at checkout.";
    note.hidden = false;
  }
  if (interest === "premium-pack" && note) {
    note.textContent = "Premium Brief Pack enquiries are handled as support requests here. To buy, create a free plan first and upgrade from the generated result.";
    note.hidden = false;
  }
  if (interest === "supplier" && note) {
    note.textContent = "Suppliers can share regions covered, fulfilment capabilities and corporate ordering options.";
    note.hidden = false;
  }
  if ((interest === "gift-planning" || interest === "event-planning") && note) {
    note.textContent = "Include recipient or attendee count, budget, deadline and any workplace suitability notes.";
    note.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submitLeadForm(form);
  });
}

function bindSupplierApplicationForm() {
  const form = document.getElementById("supplier-application-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("supplier-application-status");
    status.textContent = "Sending...";
    try {
      const response = await fetch("/api/supplier-application", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToJson(form)),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessageFromResponse(data));
      status.textContent = data.message || "Thanks — your supplier application has been saved.";
      form.reset();
    } catch (error) {
      status.textContent = error.message || "Sorry, your supplier application could not be saved.";
    }
  });
}

function bindLeadForms() {
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-lead-form]");
    if (!form || form.id === "contact-form") return;
    event.preventDefault();
    submitLeadForm(form);
  });
}

clearLegacyPremiumTestState();
checkAccountStatus();
bindMobileMenu();
bindPlannerForms();
bindResultActions();
bindAuthForms();
bindAccountPage();
bindContactForm();
bindSupplierApplicationForm();
bindLeadForms();
bindPremiumPackDownloads();
bindPackAccessForm();
