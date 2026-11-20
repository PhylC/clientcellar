const pounds = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const absent = "—";

function countValue(value) {
  if (!/^\d{1,5}$/.test(value) || Number(value) > 10000) return null;
  return Number(value);
}

function pennies(value) {
  if (!value || !/^\d{0,6}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole || "0") * 100n + BigInt(fraction.padEnd(2, "0"));
}

function money(amount) {
  return pounds.format(Number(amount) / 100);
}

function roundRatio(numerator, denominator) {
  return (numerator + denominator / 2n) / denominator;
}

export function readOrder(values) {
  const recipients = countValue(values.recipients);
  const addresses = countValue(values.addresses);
  const alcoholFree = countValue(values.alcohol_free);

  if (!recipients || !addresses || alcoholFree === null) {
    return { message: "Enter the recipient and delivery-address counts and the number of alcohol-free gifts. Use 0 if none are needed." };
  }
  if (addresses > recipients || alcoholFree > recipients) {
    return { message: "Delivery addresses and alcohol-free gifts must each be within the recipient count." };
  }
  return { recipients, addresses, alcoholFree, standard: recipients - alcoholFree };
}

export function calculateQuote(quote, order) {
  if (!order.recipients) return { total: null, missing: [] };

  const standard = order.standard ? pennies(quote.standard) : 0n;
  const alcoholFree = order.alcoholFree ? pennies(quote.alcohol_free_price) : 0n;
  const delivery = pennies(quote.delivery);
  const fees = pennies(quote.fees);
  const base = quote.vat_basis;
  const vatInput = pennies(base === "rate" ? quote.vat_rate : quote.vat_amount);

  const missing = [];
  if (standard === null) missing.push("Price per standard gift");
  if (alcoholFree === null) missing.push("Price per alcohol-free gift");
  if (delivery === null) missing.push("Delivery charge");
  if (fees === null) missing.push("Other fees or confirmation there are none");
  if (!["included", "none", "amount", "rate"].includes(base)) missing.push("Whether the prices include VAT");
  if (base === "amount" && vatInput === null) missing.push("Total VAT amount from the quote");
  if (base === "rate" && (vatInput === null || vatInput > 10000n)) missing.push("VAT rate that applies to all charges (0–100%)");

  if (missing.length) return { total: null, missing };

  const deliveryMultiplier = quote.delivery_basis === "order" ? 1n : BigInt(order.addresses);
  const subtotal = standard * BigInt(order.standard)
    + alcoholFree * BigInt(order.alcoholFree)
    + delivery * deliveryMultiplier
    + fees;
  let vat = 0n;
  if (base === "rate") vat = roundRatio(subtotal * vatInput, 10000n);
  if (base === "amount") vat = vatInput;
  const total = subtotal + vat;

  return {
    total,
    perRecipient: roundRatio(total, BigInt(order.recipients)),
    vatSummary: {
      included: "VAT is included in the entered prices.",
      none: "Supplier confirms no VAT is charged.",
      amount: "Quoted VAT added: " + money(vat) + ".",
      rate: "VAT added at the entered rate: " + money(vat) + ".",
    }[base],
    missing,
  };
}

function controlsWithin(element) {
  return Object.fromEntries(Array.from(element.querySelectorAll("[name]"), field => [field.name, field]));
}

function controlValues(controls) {
  return Object.fromEntries(Object.entries(controls).map(([name, control]) => [name, control.value]));
}

function showField(panel, key, visible) {
  const label = panel.querySelector("[data-quote-" + key + "]");
  label.hidden = !visible;
  label.querySelector("input").disabled = !visible;
}

function renderQuote(panel, controls, order) {
  const quote = controlValues(controls);
  const name = quote.supplier.trim() || panel.querySelector("legend").textContent;
  const result = calculateQuote(quote, order);
  const operational = [];
  showField(panel, "standard", order.standard !== 0);
  showField(panel, "alcohol-free", order.alcoholFree !== 0);
  showField(panel, "vat-amount", quote.vat_basis === "amount");
  showField(panel, "vat-rate", quote.vat_basis === "rate");

  if (!controls.delivery_confirmed.checked) operational.push("Delivery date and address coverage");
  if (!controls.substitutions_confirmed.checked) operational.push("Substitution terms");
  const notes = order.recipients ? [...result.missing, ...operational] : [];
  const list = panel.querySelector("[data-quote-missing]");
  list.replaceChildren(...notes.map(note => {
    const row = document.createElement("li");
    row.textContent = note;
    return row;
  }));
  panel.querySelector("[data-quote-notes]").hidden = notes.length === 0;
  const vatSummary = panel.querySelector("[data-quote-vat-summary]");
  vatSummary.textContent = result.vatSummary || "";
  vatSummary.hidden = result.total === null;
  panel.querySelector("[data-quote-total]").textContent = result.total === null ? absent : money(result.total);
  panel.querySelector("[data-quote-per-recipient]").textContent = result.total === null ? absent : money(result.perRecipient);
  return { name, total: result.total };
}

function comparisonMessage(first, second) {
  if (first.total === null || second.total === null) {
    return "Complete the costs for both quotes to compare them.";
  }
  if (first.total === second.total) return "Both quotes have the same total delivered cost.";
  const [lower, higher] = first.total < second.total ? [first, second] : [second, first];
  return `${lower.name} costs ${money(higher.total - lower.total)} less for this order, based on the entered prices.`;
}

function bindComparison(root) {
  const orderControls = controlsWithin(root.querySelector(".quote-brief"));
  const panels = Array.from(root.querySelectorAll("[data-quote-panel]"), panel => [panel, controlsWithin(panel)]);
  const counts = root.querySelector("[data-quote-count-status]");
  const verdict = root.querySelector("[data-quote-verdict]");
  const query = new URLSearchParams(location.search);
  for (const [key, field] of Object.entries(orderControls)) {
    const value = query.get(key);
    if (value !== null && countValue(value) !== null) field.value = value;
  }

  function update() {
    const order = readOrder(controlValues(orderControls));
    counts.textContent = order.message ||
      `${order.standard} standard gifts and ${order.alcoholFree} alcohol-free gifts across ${order.addresses} addresses.`;
    const [first, second] = panels.map(([panel, controls]) => renderQuote(panel, controls, order));
    const message = order.message
      ? "Enter the same order details and both quotes to see the difference."
      : comparisonMessage(first, second);
    if (verdict.textContent !== message) verdict.textContent = message;
  }

  root.addEventListener("input", update);
  root.addEventListener("change", update);
  const page = root.closest(".quote-comparison");
  page.querySelector("[data-quote-example]").addEventListener("click", () => {
    orderControls.recipients.value = "30";
    orderControls.addresses.value = "30";
    orderControls.alcohol_free.value = "5";
    const sampleQuotes = [
      { supplier: "Sample A", standard: "32", alcohol_free_price: "25", delivery: "5.95", vat_basis: "included" },
      { supplier: "Sample B", standard: "28", alcohol_free_price: "21", delivery: "4.50", vat_basis: "rate", vat_rate: "20" },
    ];
    panels.forEach(([, controls], index) => {
      for (const [key, value] of Object.entries({
        delivery_basis: "per-address", fees: "0", vat_amount: "", vat_rate: "", ...sampleQuotes[index],
      })) controls[key].value = value;
      controls.delivery_confirmed.checked = false;
      controls.substitutions_confirmed.checked = false;
    });
    page.querySelector("[data-quote-example-note]").hidden = false;
    update();
  });
  update();
}

if (typeof document !== "undefined") {
  const comparison = document.querySelector("[data-gift-quote-comparison]");
  if (comparison) bindComparison(comparison);
}
