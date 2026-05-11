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
    throw new Error("Account login is not enabled on this deployment.");
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
  const url = supplier.tracked_url || supplier.url || supplier.website_url || supplier.affiliate_url || "";
  if (!url) {
    const search = supplier.search_suggestion || supplier.searchSuggestion || "corporate hamper supplier UK";
    return `<p class="small-note"><strong>Search suggestion:</strong> ${escapeHtml(search)}</p>`;
  }
  const isExternal = /^https?:\/\//i.test(url);
  const target = isExternal ? ' target="_blank"' : "";
  const rel = isExternal ? ' rel="noopener noreferrer sponsored"' : "";
  const label = supplier.link_label || (supplier.is_affiliate ? "Visit supplier" : "Visit supplier");
  return `<p><a class="button secondary" href="${escapeHtml(url)}"${target}${rel}>${escapeHtml(label)}</a></p>`;
}

function renderSupplierRouteCards(routes = [], type = "gift") {
  if ((!Array.isArray(routes) || !routes.length) && type !== "gift") return "";
  const routeList = Array.isArray(routes) ? routes : [];
  if (type === "gift") {
    const rows = giftSupplierDiscoveryRows(routeList);
    return `
      <div class="table-scroll free-route-table-wrap">
        <table class="free-route-table gift-recommendation-table">
          <thead><tr><th>Route</th><th>Best when</th><th>Recommended first choice</th><th>Why</th><th>Supplier links</th></tr></thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr>
                    <td><strong>${escapeHtml(row.route)}</strong></td>
                    <td>${escapeHtml(row.bestWhen)}</td>
                    <td><strong>${escapeHtml(row.firstChoice)}</strong></td>
                    <td>${escapeHtml(row.why)}</td>
                    <td>${row.supplierLinks}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <div class="free-route-cards">
        ${rows
          .map(
            (row) => `
              <article class="free-route-card">
                <h3>${escapeHtml(row.route)}</h3>
                <dl>
                  <div><dt>Best when</dt><dd>${escapeHtml(row.bestWhen)}</dd></div>
                  <div><dt>Recommended first choice</dt><dd>${escapeHtml(row.firstChoice)}</dd></div>
                  <div><dt>Why</dt><dd>${escapeHtml(row.why)}</dd></div>
                  <div><dt>Supplier links</dt><dd>${row.supplierLinks}</dd></div>
                </dl>
              </article>
            `
          )
          .join("")}
      </div>
      <p class="small-note free-route-note">We suggest a first-choice route to save time, but include alternatives where budget, brand fit or recipient preferences may point elsewhere.</p>
      <div class="free-route-upgrade">
        <h3>Need help choosing the best route?</h3>
        <p>Premium gives you a ranked shortlist, indicative spend ranges, ease scores, hidden watchouts and a downloadable supplier matrix.</p>
        <a class="button secondary small" href="/example-premium-brief-pack">See premium example</a>
      </div>
    `;
  }
  const rows = routeList.map((route) => supplierRouteComparisonRow(route));
  return `
    <div class="table-scroll free-route-table-wrap">
      <table class="free-route-table">
        <thead><tr><th>Route</th><th>Best for</th><th>Example suppliers</th><th>Check before using</th></tr></thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td><strong>${escapeHtml(row.route)}</strong></td>
                  <td>${escapeHtml(row.bestFor)}</td>
                  <td>${escapeHtml(row.examples)}</td>
                  <td>${escapeHtml(row.whatToCheck)}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
    <div class="free-route-cards">
      ${rows
        .map(
          (row) => `
            <article class="free-route-card">
              <h3>${escapeHtml(row.route)}</h3>
              <dl>
                <div><dt>Best for</dt><dd>${escapeHtml(row.bestFor)}</dd></div>
                <div><dt>Example suppliers</dt><dd>${escapeHtml(row.examples)}</dd></div>
                <div><dt>Check before using</dt><dd>${escapeHtml(row.whatToCheck)}</dd></div>
              </dl>
            </article>
          `
        )
        .join("")}
    </div>
    <div class="free-route-upgrade">
      <h3>Need help choosing the best route?</h3>
      <p>Premium gives you a ranked shortlist, indicative spend ranges, ease scores, hidden watchouts and a downloadable supplier matrix.</p>
      <a class="button secondary small" href="/example-premium-brief-pack">See premium example</a>
    </div>
  `;
}

function giftSupplierDiscoveryRows(routes = []) {
  return [
    {
      route: "Corporate wine gifting",
      bestWhen: "Client lists, repeat orders or wine-friendly recipients",
      firstChoice: "Majestic",
      why: "Best practical option for larger wine orders, recognisable range and business-friendly buying.",
      supplierLinks: supplierButtonGroup([
        { id: "majestic", label: "Majestic" },
        { id: "laithwaites", label: "Laithwaites" },
        { id: "virgin-wines", label: "Virgin Wines" },
      ]),
    },
    {
      route: "Hampers",
      bestWhen: "Mixed tastes or unknown preferences",
      firstChoice: "M&S",
      why: "Safest mainstream choice for mixed tastes, simple gifting and broad recipient appeal.",
      supplierLinks: supplierButtonGroup([
        { id: "marks-spencer-corporate", label: "M&S" },
        { id: "john-lewis-hampers", label: "John Lewis" },
        { id: "fortnum-mason", label: "Fortnum & Mason" },
      ]),
    },
    {
      route: "Premium retailer",
      bestWhen: "Presentation and perceived value matter more than price",
      firstChoice: "Fortnum & Mason",
      why: "Strongest premium signal when presentation and perceived value matter more than price.",
      supplierLinks: supplierButtonGroup([
        { id: "fortnum-mason", label: "Fortnum & Mason" },
        { id: "selfridges-hampers", label: "Selfridges" },
        { id: "harvey-nichols-hampers", label: "Harvey Nichols" },
      ]),
    },
    {
      route: "Local wine merchant",
      bestWhen: "VIP clients, smaller lists or more personal recommendations",
      firstChoice: "Local merchant",
      why: "Best for VIP clients where advice, personalisation or regional relevance matters.",
      supplierLinks: `<span class="supplier-search-suggestion">Search: independent wine merchant near me</span>`,
    },
  ];
}

function supplierLinkUrl(supplierId) {
  return window.CLIENTCELLAR_SUPPLIER_LINKS?.[supplierId] || "";
}

function supplierButtonGroup(suppliers = []) {
  const links = suppliers
    .map((supplier) => {
      const url = supplierLinkUrl(supplier.id);
      if (!url) return "";
      return `<a class="button secondary small free-route-button supplier-pill-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer sponsored">${escapeHtml(supplier.label)}</a>`;
    })
    .filter(Boolean);
  if (!links.length) {
    return `<a class="button secondary small free-route-button supplier-pill-link" href="/suppliers">View supplier directory</a>`;
  }
  return `<div class="supplier-link-pills">${links.join("")}</div>`;
}

function supplierCompareLink(routes = [], patterns = [], label = "Compare options", fallback = "/suppliers", directFallback = "") {
  const supplier = routes
    .flatMap((route) => Array.isArray(route.example_suppliers) ? route.example_suppliers : [])
    .find((candidate) => {
      const haystack = `${candidate.name || ""} ${candidate.id || ""}`.toLowerCase();
      return patterns.some((pattern) => haystack.includes(pattern));
    });
  if (!supplier) return routeCompareLink({}, label, fallback, directFallback);
  return routeCompareLink({ example_suppliers: [supplier], is_affiliate: supplier.is_affiliate }, label, fallback, directFallback);
}

function routeCompareLink(route = {}, label = "Compare options", fallback = "/suppliers", directFallback = "") {
  const supplierWithLink = Array.isArray(route.example_suppliers)
    ? route.example_suppliers.find((supplier) => supplier.tracked_url || supplier.url || supplier.website_url || supplier.affiliate_url)
    : null;
  const trackedUrl = route.tracked_url
    || supplierWithLink?.tracked_url
    || supplierWithLink?.affiliate_url
    || route.affiliate_url
    || route.affiliateUrl
    || "";
  const directUrl = supplierWithLink?.url
    || supplierWithLink?.website_url
    || route.url
    || route.website_url
    || directFallback
    || "";
  const url = trackedUrl || directUrl || fallback;
  const isExternal = /^https?:\/\//i.test(url);
  const target = isExternal ? ' target="_blank"' : "";
  const rel = isExternal ? ' rel="noopener noreferrer sponsored"' : "";
  return `<a class="button secondary small free-route-button" href="${escapeHtml(url)}"${target}${rel}>${escapeHtml(label)}</a>`;
}

function supplierRouteComparisonRow(route = {}) {
  const routeName = route.route_name || route.route || "Supplier route";
  const examples = Array.isArray(route.example_suppliers) && route.example_suppliers.length
    ? route.example_suppliers.map((supplier) => supplier.name).filter(Boolean)
    : route.examples || [];
  const lower = routeName.toLowerCase();
  const defaults = {
    displayRoute: routeName,
    bestFor: route.why_it_fits || route.why || "Useful route to check for this brief.",
    whatToCheck: route.what_to_ask || route.ask || "Stock, delivery, VAT and suitability",
  };
  if (lower.includes("corporate wine")) {
    defaults.displayRoute = "Corporate wine gifting supplier";
    defaults.bestFor = "Client lists or repeat wine orders";
    defaults.whatToCheck = "Bulk orders, gift notes, tracking, substitutions";
    examples.splice(0, examples.length, "Majestic", "Laithwaites", "Virgin Wines");
  } else if (lower.includes("hamper")) {
    defaults.displayRoute = "Hamper supplier";
    defaults.bestFor = "Mixed tastes or unknown preferences";
    defaults.whatToCheck = "Dietary options, alcohol-free options, delivery dates";
    examples.splice(0, examples.length, "M&S", "John Lewis", "Fortnum & Mason");
  } else if (lower.includes("local independent")) {
    defaults.displayRoute = "Local independent wine merchant";
    defaults.bestFor = "VIP clients or smaller lists";
    defaults.whatToCheck = "Delivery area, invoice support, gift wrapping";
    examples.splice(0, examples.length, "Local wine merchant");
  } else if (lower.includes("supermarket") || lower.includes("mainstream")) {
    defaults.displayRoute = "Mainstream retailer";
    defaults.bestFor = "Lower budgets or fast turnaround";
    defaults.whatToCheck = "Stock, delivery slots, substitutions";
    examples.splice(0, examples.length, "Waitrose", "Tesco", "M&S");
  } else if (lower.includes("non-alcohol")) {
    defaults.displayRoute = "Non-alcoholic gifting supplier";
    defaults.bestFor = "Mixed groups or uncertain alcohol suitability";
    defaults.whatToCheck = "Gift presentation, delivery dates, alcohol-free range";
  } else if (lower.includes("premium")) {
    defaults.displayRoute = "Premium wine merchant";
    defaults.bestFor = "Senior clients or more formal gifting";
    defaults.whatToCheck = "Presentation, bottle suitability, delivery timing";
  }
  return {
    route: defaults.displayRoute,
    bestFor: defaults.bestFor,
    examples: examples.length ? examples.join(", ") : "Supplier type to search",
    whatToCheck: defaults.whatToCheck,
    compareOptions: routeCompareLink(route, "Compare options", "/suppliers"),
  };
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
          <p class="small-note">${escapeHtml(supplier.disclosure_note || "Use this as a supplier route to check. Some supplier links may be affiliate or tracked links where available.")} <a href="/affiliate-disclosure">See Affiliate Disclosure.</a></p>
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

function contactRouteHtml(item = {}) {
  const mailtoUrl = item.mailto_url || item.mailtoUrl || "";
  if (mailtoUrl) {
    return `<a href="${escapeHtml(mailtoUrl)}">Email supplier</a>`;
  }
  const contactUrl = item.contact_url || item.contactUrl || "";
  if (contactUrl) {
    const typeLabels = {
      contact_form: "Contact form",
      corporate_page: "Corporate gifting",
      supplier_page: "Supplier page",
    };
    const label = item.contact_label || item.contactLabel || typeLabels[item.contact_type || item.contactType] || "Contact supplier";
    return `<a href="${escapeHtml(contactUrl)}" target="_blank" rel="noopener noreferrer sponsored">${escapeHtml(label)}</a>`;
  }
  const search = item.search_suggestion || item.searchSuggestion || "corporate wine gift supplier UK";
  return `<span>Search/contact directly</span><br><span class="small-note">Search: ${escapeHtml(search)}</span>`;
}

function renderAdvisoryItems(items = []) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="advisory-panel">
      <h3>Executive recommendation</h3>
      <dl class="advisory-list">
        ${items.map((item) => `<div><dt>${escapeHtml(item.label || "")}</dt><dd>${escapeHtml(item.value || "")}</dd></div>`).join("")}
      </dl>
    </div>
  `;
}

function renderWhatWeWouldDo(items = []) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="advisory-panel">
      <h3>What we would do</h3>
      <ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
    </div>
  `;
}

function supplierNameHtml(item = {}) {
  return `<strong>${escapeHtml(item.supplier || item.supplier_type || "Supplier route")}</strong><div class="supplier-contact-inline">${contactRouteHtml(item)}</div>`;
}

function tagRowHtml(tags = []) {
  if (!Array.isArray(tags) || !tags.length) return "";
  return `<div class="tag-row">${tags.map((tag) => `<span class="route-tag">${escapeHtml(tag)}</span>`).join("")}</div>`;
}

const supplierMatrixHeaders = [
  "Supplier",
  "Best for",
  "Typical spend",
  "Minimum order",
  "Branding / personalisation",
  "Turnaround",
  "Multi-address delivery",
  "Contact route",
  "Ease score",
  "Hidden watchouts",
  "Recommendation",
  "Extra notes",
];

function plainContactRoute(item = {}) {
  if (item.contact_email || item.contactEmail) return `Email supplier: ${item.contact_email || item.contactEmail}`;
  if (item.contact_url || item.contactUrl) {
    const label = item.contact_label || item.contactLabel || "Contact supplier";
    return `${label}: ${item.contact_url || item.contactUrl}`;
  }
  if (item.search_suggestion || item.searchSuggestion) return `Search/contact directly: ${item.search_suggestion || item.searchSuggestion}`;
  return "Search/contact directly";
}

function supplierMatrixCsv(items = []) {
  const rows = [supplierMatrixHeaders];
  items.forEach((item) => {
    rows.push([
      item.supplier || item.supplier_type || "Supplier route",
      item.best_for || "",
      item.typical_spend || "",
      item.minimum_order || "",
      item.branding_personalisation || "",
      item.turnaround || "",
      item.multi_address_delivery || "",
      plainContactRoute(item),
      item.ease_score || "",
      item.hidden_watchouts || "",
      item.recommendation || "",
      item.extra_notes || item.questions_to_ask || item.watchouts || "",
    ]);
  });
  return rows
    .map((row) => row.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\n");
}

function renderPremiumComparison(preview = {}) {
  const items = preview.supplier_comparison || [];
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${supplierNameHtml(item)}</td>
          <td>${tagRowHtml(item.best_for_tags)}${escapeHtml(item.best_for || "")}</td>
          <td>${escapeHtml(item.typical_spend || "")}</td>
          <td><span class="score-pill">${escapeHtml(item.ease_score || "6/10")}</span></td>
          <td>${escapeHtml(item.hidden_watchouts || "")}</td>
          <td>${escapeHtml(item.recommendation || "")}</td>
        </tr>
      `
    )
    .join("");
  const cards = items
    .map(
      (item) => `
        <article class="supplier-comparison-card">
          <div class="comparison-card-header">
            <h3>${escapeHtml(item.supplier || item.supplier_type || "Supplier route")}</h3>
            <span class="score-pill">${escapeHtml(item.ease_score || "6/10")}</span>
          </div>
          ${tagRowHtml(item.best_for_tags)}
          <p class="supplier-contact-inline">${contactRouteHtml(item)}</p>
          <dl class="comparison-card-list">
            <div><dt>Best for</dt><dd>${escapeHtml(item.best_for || "")}</dd></div>
            <div><dt>Typical spend</dt><dd>${escapeHtml(item.typical_spend || "")}</dd></div>
            <div><dt>Key watchout</dt><dd>${escapeHtml(item.hidden_watchouts || "")}</dd></div>
            <div><dt>Recommendation</dt><dd>${escapeHtml(item.recommendation || "")}</dd></div>
          </dl>
        </article>
      `
    )
    .join("");
  const shortlist = Array.isArray(preview.recommended_shortlist) && preview.recommended_shortlist.length
    ? `
      <div class="advisory-panel">
        <h3>Recommended shortlist</h3>
        <div class="shortlist-grid">
          ${preview.recommended_shortlist
            .map((item) => `<div><span class="route-tag">${escapeHtml(item.rank || "")}</span><h4>${escapeHtml(item.supplier || "")}</h4><p>${escapeHtml(item.reason || "")}</p></div>`)
            .join("")}
        </div>
      </div>
    `
    : "";
  return `
    ${renderAdvisoryItems(preview.supplier_executive_recommendation)}
    ${renderWhatWeWouldDo(preview.what_we_would_do)}
    <p class="small-note">Indicative planning guidance only. Supplier pricing, stock, availability, delivery and order terms must be confirmed directly.</p>
    <div class="matrix-action-row">
      <button class="button secondary small" type="button" data-download-supplier-matrix>Download full supplier matrix</button>
      <script type="application/json" data-supplier-matrix-data>${JSON.stringify(items).replace(/</g, "\\u003c")}</script>
    </div>
    <div class="table-scroll supplier-comparison-desktop">
      <table class="pack-table supplier-comparison-table">
        <thead><tr><th>Supplier</th><th>Best for</th><th>Typical spend</th><th>Ease</th><th>Key watchout</th><th>Recommendation</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="supplier-comparison-cards">${cards}</div>
    ${shortlist}
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
          <p class="small-note">Supplier-ready means formatted for enquiry and internal approval; it does not mean supplier availability or pricing has been confirmed.</p>
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
        ${renderPremiumComparison(preview)}
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
        <p class="small-note">Some supplier links may be affiliate or tracked links where available. Confirm availability, pricing and delivery directly. <a href="/affiliate-disclosure">Affiliate Disclosure</a>.</p>
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
  const routeList = plan.supplier_routes_to_check || [plan.supplier_category].filter(Boolean);
  const questions =
    plan.questions_to_ask_suppliers ||
    plan.questions_to_ask_event_wine_suppliers ||
    plan.supplier_questions ||
    [];
  const risks = plan.risks_and_checks || plan.what_to_avoid || [];
  const eventExtras =
    type === "event"
      ? `
        <div class="result-block">
          <h2>Guest count and serving assumptions</h2>
          ${list(plan.guest_count_and_serving_assumptions || plan.serving_assumptions || [])}
        </div>
        <div class="result-block">
          <h2>Wine quantity estimate</h2>
          ${list(plan.wine_quantity_estimate || [])}
        </div>
        <div class="result-block">
          <h2>Recommended wine mix</h2>
          <p>${escapeHtml(plan.recommended_wine_mix || plan.recommended_direction || plan.recommended_format || "")}</p>
          ${list(plan.event_structure || [])}
        </div>
      `
      : `
        <div class="result-block">
          <h2>Recipient and occasion fit</h2>
          ${list(plan.recipient_occasion_fit || [])}
        </div>
        <div class="result-block">
          <h2>Suggested gift direction</h2>
          <p>${escapeHtml(plan.suggested_gift_direction || plan.recommended_direction || plan.recommended_strategy || "")}</p>
          ${list(plan.recommended_gift_types || [])}
        </div>
      `;

  return `
    <article class="plan-result">
      <p class="eyebrow">Generated plan</p>
      <h2>${escapeHtml(plan.headline)}</h2>
      <p class="result-meta">${escapeHtml(plan.summary)}</p>
      <p class="small-note">This is planning guidance, not a confirmed quote. Check stock, pricing, delivery, age restrictions and suitability directly with your chosen supplier.</p>
      <div class="result-block">
        <h2>${type === "event" ? "Event summary" : "Summary"}</h2>
        <p>${escapeHtml(plan.event_summary || plan.summary || "")}</p>
      </div>
      ${eventExtras}
      <div class="result-block">
        <h2>Budget estimate</h2>
        <p><strong>Estimated budget:</strong> ${escapeHtml(plan.estimated_total_budget)}</p>
        ${list(plan.budget_guidance || [])}
      </div>
      <div class="result-block">
        <h2>${type === "gift" ? "Recommended supplier route" : "Supplier routes to check"}</h2>
        ${renderSupplierRouteCards(plan.supplier_route_cards, type)}
        ${type !== "gift" && !plan.supplier_route_cards?.length ? list(routeList) : ""}
        <p class="small-note">${escapeHtml(plan.supplier_links_note || "Supplier links are not required to use this plan. You can use the supplier route guidance to contact retailers or merchants directly.")}</p>
      </div>
      <div class="result-block">
        <h2>Questions to ask ${type === "event" ? "event wine suppliers" : "suppliers"}</h2>
        ${list(questions)}
      </div>
      <div class="result-block">
        <h2>Risks and checks</h2>
        ${list(risks)}
      </div>
      <div class="result-block">
        <h2>Next steps</h2>
        ${list(plan.next_steps || [])}
      </div>
      <div class="premium-cta-card">
        <p class="eyebrow">Premium Brief Pack</p>
        <h2>Want the documents to actually send?</h2>
        <p>Your free plan gives you a useful planning route. Premium creates the working pack: supplier-ready buying brief, copy-and-send supplier enquiry email, budget and quantity breakdown, internal approval summary and next steps checklist.</p>
        <ul class="feature-list">
          <li>Supplier-ready buying brief</li>
          <li>Copy-ready supplier email</li>
          <li>Supplier shortlist guidance</li>
          <li>Internal approval summary</li>
          <li>Budget and quantity breakdown</li>
          <li>Saved download link</li>
        </ul>
        <p class="small-note">Supplier-ready means formatted for enquiry and approval; it does not mean supplier availability, pricing or quotes have been confirmed.</p>
        <div class="result-actions">
          <button class="button primary" type="button" data-pack-checkout data-pack-type="${type}">Upgrade this plan to Premium Brief Pack</button>
          <a class="button secondary" href="${type === "gift" ? "/gift-planner" : "/event-planner"}">Continue with free plan</a>
        </div>
        <details class="premium-detail">
          <summary>Other next steps</summary>
          <div class="button-row">
            <a class="button secondary small" href="/contact?interest=${type === "gift" ? "gift-planning" : "event-planning"}">Send enquiry / request help</a>
            <a class="button secondary small" href="/suppliers">See more supplier routes</a>
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

function downloadCsv(text, filename = csvFilename) {
  const blob = new Blob([`${text}\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function downloadSupplierMatrix(button) {
  const root = button.closest(".premium-doc") || document;
  const dataNode = root.querySelector("[data-supplier-matrix-data]");
  if (!dataNode) return;
  let items = [];
  try {
    items = JSON.parse(dataNode.textContent || "[]");
  } catch (error) {
    items = [];
  }
  if (!Array.isArray(items) || !items.length) return;
  downloadCsv(supplierMatrixCsv(items), "clientcellar-supplier-matrix.csv");
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
        <h2>Account login is not enabled</h2>
        <p>The Free Planner and one-off Premium Brief Pack flow can still be used where checkout is available.</p>
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
      setStatus("Account login is not enabled on this deployment.", true);
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
    if (button.matches("[data-download-supplier-matrix]")) {
      downloadSupplierMatrix(button);
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
    const payload = formToJson(form);
    const mailBody = encodeURIComponent(
      Object.entries(payload)
        .map(([key, value]) => `${key}: ${value === true ? "yes" : value === false ? "no" : value || ""}`)
        .join("\n")
    );
    const mailto = `mailto:partners@clientcellar.co.uk?subject=${encodeURIComponent("Supplier application")}&body=${mailBody}`;
    status.textContent = "Sending...";
    try {
      const response = await fetch("/api/supplier-application", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessageFromResponse(data));
      status.textContent = data.message || "Thanks — your supplier application has been saved.";
      form.reset();
    } catch (error) {
      status.innerHTML = `Sorry, your supplier application could not be saved here. <a href="${mailto}">Email partners@clientcellar.co.uk with these details</a>.`;
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
