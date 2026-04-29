const csvFilename = "clientcellar-recipient-template.csv";

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
      const link = supplier.url
        ? `<p><a href="${escapeHtml(supplier.url)}" target="_blank" rel="noopener">Supplier link</a></p><p class="small-note">Some supplier links may be affiliate links.</p>`
        : "";
      return `
        <article class="supplier-card">
          <h3>${escapeHtml(supplier.name)}</h3>
          <p><strong>${escapeHtml(supplier.category)}</strong></p>
          <p>${escapeHtml(supplier.why)}</p>
          <p>${escapeHtml(supplier.budget_fit)}</p>
          ${link}
        </article>
      `;
    })
    .join("");
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
        <button class="button secondary" type="button" data-print-plan>Print / save plan</button>
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
      <div class="result-block">
        <h2>Disclaimer</h2>
        <p>${escapeHtml(plan.disclaimer)}</p>
      </div>
    </article>
  `;
}

async function submitPlan(form, type) {
  const target = document.getElementById(`${type}-results`);
  const endpoint = type === "gift" ? "/api/gift-plan" : "/api/event-plan";
  target.innerHTML = '<div class="loading">Building your plan...</div>';

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
    target.innerHTML = renderPlan(plan, type);
    target.dataset.csv = plan.recipient_csv_template || "";
  } catch (error) {
    target.innerHTML = '<div class="empty-state">Sorry, the plan could not be generated. Check the form and try again.</div>';
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

function bindPlannerForms() {
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
  });
}

function bindContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("contact-status");
    status.textContent = "Sending...";
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToJson(form)),
      });
      const data = await response.json();
      if (!response.ok) throw new Error("Contact request failed");
      status.textContent = data.message;
      form.reset();
    } catch (error) {
      status.textContent = "Sorry, your message could not be logged.";
    }
  });
}

bindPlannerForms();
bindResultActions();
bindContactForm();
