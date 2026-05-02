const csvFilename = "clientcellar-recipient-template.csv";
const plannerState = {
  gift: null,
  event: null,
};

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

function renderSuppliers(suppliers) {
  return suppliers
    .map((supplier) => {
      const link = supplier.tracked_url
        ? `<p><a class="button secondary" href="${escapeHtml(supplier.tracked_url)}" target="_blank" rel="noopener">Visit supplier</a></p>`
        : '<p class="small-note">Use this as a supplier type rather than a direct supplier link.</p>';
      return `
        <article class="supplier-card">
          <h3>${escapeHtml(supplier.name)}</h3>
          <p><strong>${escapeHtml(supplier.category)}</strong></p>
          <p><strong>${escapeHtml(supplier.relationship_label || "Listed supplier")}</strong></p>
          <p>${escapeHtml(supplier.why)}</p>
          <p>${escapeHtml(supplier.budget_fit)}</p>
          ${link}
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
  return items
    .map(
      (item) => `
        <article class="supplier-card">
          <h3>${escapeHtml(item.supplier)}</h3>
          <p>${escapeHtml(item.fit)}</p>
          <p><strong>Pros</strong></p>
          ${list(item.pros)}
          <p><strong>Watchouts</strong></p>
          ${list(item.watchouts)}
        </article>
      `
    )
    .join("");
}

function renderPremiumPreview(preview, type) {
  const email = `${preview.supplier_enquiry_email.subject}\n\n${preview.supplier_enquiry_email.body}`;
  const packLabel = type === "gift" ? "Gift Planning Pack" : "Event Planning Pack";
  const csvButton =
    type === "gift"
      ? `<button class="button secondary" type="button" data-download-preview-csv>Download recipient CSV</button>`
      : "";
  return `
    <div class="premium-preview premium-doc">
      <header class="premium-doc-header">
        <div>
          <p class="eyebrow">ClientCellar Premium Pack</p>
          <h2>${escapeHtml(packLabel)}</h2>
        </div>
        <div class="premium-doc-actions">
          <button class="button secondary" type="button" data-print-plan>Print / save as PDF</button>
          <button class="button secondary" type="button" data-copy-preview-email>Copy enquiry email</button>
          ${csvButton}
        </div>
      </header>
      <section class="result-block">
        <h3>Executive summary</h3>
        <p>${escapeHtml(preview.executive_summary)}</p>
      </section>
      <section class="result-block">
        <h3>Budget breakdown</h3>
        ${renderBudgetRows(preview.budget_breakdown)}
      </section>
      <section class="result-block">
        <h3>Supplier comparison</h3>
        ${renderPremiumComparison(preview.supplier_comparison)}
      </section>
      <section class="result-block">
        <h3>Recommended next steps</h3>
        <ul>
          <li>Confirm supplier pricing and availability.</li>
          <li>Share the brief internally for approval.</li>
          <li>Prepare recipient or attendee details.</li>
          <li>Request final quotes and delivery terms.</li>
        </ul>
      </section>
      <section class="result-block">
        <h3>Supplier enquiry email</h3>
        <pre class="email-preview" data-preview-email>${escapeHtml(email)}</pre>
      </section>
      <section class="result-block">
        <h3>Message variants</h3>
        ${preview.message_variants
          .map((variant) => `<p><strong>${escapeHtml(variant.tone)}:</strong> ${escapeHtml(variant.message)}</p>`)
          .join("")}
      </section>
      ${type === "gift" ? `<section class="result-block"><h3>Recipient CSV template</h3><pre data-preview-csv>${escapeHtml(preview.recipient_csv_template)}</pre></section>` : ""}
      <section class="result-block">
        <h3>Internal approval note</h3>
        <p>${escapeHtml(preview.internal_approval_note)}</p>
      </section>
      <section class="result-block">
        <h3>Risk and suitability checklist</h3>
        ${list(preview.risk_checklist)}
      </section>
      <section class="result-block disclaimer-block">
        <h3>Responsible drinking & workplace policy reminder</h3>
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
      <h2>Want help turning this into a supplier-ready brief?</h2>
      <p>Leave your details and we’ll use your plan to help prepare a clearer gifting or event brief.</p>
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
  const email = `${plan.supplier_enquiry_email.subject}\n\n${plan.supplier_enquiry_email.body}`;
  const eventExtras =
    type === "event"
      ? `
        <div class="result-block">
          <h2>Recommended format</h2>
          <p>${escapeHtml(plan.recommended_format)}</p>
        </div>
        <div class="result-block">
          <h2>Event structure</h2>
          ${list(plan.event_structure)}
        </div>
        <div class="result-block">
          <h2>Internal invite</h2>
          <div class="invite-preview" data-invite>${escapeHtml(plan.internal_invite_copy)}</div>
        </div>
      `
      : `
        <div class="result-block">
          <h2>Recommended strategy</h2>
          <p>${escapeHtml(plan.recommended_strategy)}</p>
        </div>
        <div class="result-block">
          <h2>Recommended gift types</h2>
          ${list(plan.recommended_gift_types)}
        </div>
        <div class="result-block">
          <h2>Message templates</h2>
          ${list(plan.message_templates)}
        </div>
      `;

  const csvButton =
    type === "gift"
      ? '<button class="button secondary" type="button" data-download-csv>Download recipient CSV template</button>'
      : "";
  const inviteButton =
    type === "event"
      ? '<button class="button secondary" type="button" data-copy-invite>Copy internal invite</button>'
      : "";

  return `
    <article class="plan-result">
      <p class="eyebrow">Generated plan</p>
      <h2>${escapeHtml(plan.headline)}</h2>
      <p class="result-meta">${escapeHtml(plan.summary)}</p>
      <p><strong>Estimated budget:</strong> ${escapeHtml(plan.estimated_total_budget)}</p>
      <div class="result-actions">
        <button class="button primary" type="button" data-copy-email>Copy supplier enquiry email</button>
        ${csvButton}
        ${inviteButton}
        <button class="button secondary" type="button" data-print-plan>Print / save as PDF</button>
      </div>
      ${eventExtras}
      <div class="result-block">
        <h2>Supplier shortlist</h2>
        ${renderSuppliers(plan.supplier_shortlist)}
      </div>
      <div class="result-block">
        <h2>What to avoid</h2>
        ${list(plan.what_to_avoid)}
      </div>
      <div class="result-block">
        <h2>Supplier enquiry email</h2>
        <div class="email-preview" data-email>${escapeHtml(email)}</div>
      </div>
      <div class="result-block">
        <h2>Next steps</h2>
        ${list(plan.next_steps)}
      </div>
      <div class="premium-cta-card">
        <p class="eyebrow">Premium Pack</p>
        <h2>Need a supplier-ready pack?</h2>
        <p>Generate a polished planning pack with budget notes, supplier comparison, recipient CSV, message options and a ready-to-send enquiry email.</p>
        <div class="result-actions">
          <button class="button primary" type="button" data-preview-premium data-pack-type="${type}">Preview premium pack</button>
          <a class="button secondary" href="/premium-pack">View premium pack</a>
          <a class="button secondary" href="/contact?interest=premium-pack">Register interest</a>
        </div>
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
    if (isPaidMode()) {
      const premiumButton = target.querySelector("[data-preview-premium]");
      if (premiumButton) premiumButton.textContent = "Create premium pack";
    }
  } catch (error) {
    target.innerHTML = '<div class="empty-state">Sorry, the plan could not be generated. Check the form and try again. If the issue continues, refresh the page.</div>';
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  }
}

async function previewPremiumPack(type, button) {
  const state = plannerState[type];
  const panel = button.closest(".premium-cta-card");
  const target = panel.querySelector("[data-premium-preview]");
  if (!state) {
    target.innerHTML = '<p class="small-note">Generate a plan first, then preview the premium pack.</p>';
    return;
  }

  button.disabled = true;
  target.innerHTML = '<div class="loading compact">Building premium preview...</div>';
  try {
    const response = await fetch("/api/premium-pack-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_type: type,
        planner_input: state.input,
        planner_output: state.output,
      }),
    });
    if (!response.ok) throw new Error("Preview failed");
    const preview = await response.json();
    target.innerHTML = renderPremiumPreview(preview, type);
  } catch (error) {
    target.innerHTML = '<p class="small-note">Sorry, the premium preview could not be generated.</p>';
  } finally {
    button.disabled = false;
  }
}

async function createCheckoutSession(packType, button) {
  const original = button.textContent;
  button.textContent = "Checking...";
  button.disabled = true;
  try {
    const response = await fetch("/api/create-checkout-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pack_type: packType }),
    });
    const data = await response.json();
    if (data.enabled && data.checkout_url) {
      window.location.href = data.checkout_url;
      return;
    }
    window.location.href = "/contact?interest=premium-pack";
  } catch (error) {
    window.location.href = "/contact?interest=premium-pack";
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

function isPaidMode() {
  return new URLSearchParams(window.location.search).get("paid") === "true";
}

function showPaidBanner() {
  const banner = document.getElementById("paid-banner");
  if (banner && isPaidMode()) {
    banner.hidden = false;
  }
}

function bindPlannerForms() {
  showPaidBanner();
  for (const form of document.querySelectorAll("[data-plan-form]")) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitPlan(form, form.dataset.planForm);
    });
  }
}

function bindResultActions() {
  document.addEventListener("click", (event) => {
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
      previewPremiumPack(button.dataset.packType, button);
    }
    if (button.matches("[data-copy-preview-email]")) {
      const preview = button.closest(".premium-preview");
      if (preview) copyText(preview.querySelector("[data-preview-email]").textContent, button);
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

function bindContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) return;

  const interest = new URLSearchParams(window.location.search).get("interest");
  const select = form.querySelector('[name="interested_in"]');
  const note = document.getElementById("contact-note");
  if ((interest === "premium-pack" || interest === "premium-pack-support") && select) {
    select.value = "premium_pack";
  }
  if (interest === "premium-pack-support" && note) {
    note.textContent = "Need help with payment or premium pack access? Please include the email used at checkout.";
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

bindPlannerForms();
bindResultActions();
bindContactForm();
bindSupplierApplicationForm();
bindLeadForms();
