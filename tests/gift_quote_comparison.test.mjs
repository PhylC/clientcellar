import assert from "node:assert/strict";
import { test } from "node:test";
import { calculateQuote, readOrder } from "../static/gift-quote-comparison.mjs";

const order = readOrder({ recipients: "30", addresses: "30", alcohol_free: "5" });
const quote = {
  standard: "32",
  alcohol_free_price: "25",
  delivery: "5.95",
  delivery_basis: "per-address",
  fees: "0",
  vat_basis: "included",
};

test("prices a mixed order using delivery per address and included VAT", () => {
  const result = calculateQuote(quote, order);
  assert.deepEqual(order, { recipients: 30, addresses: 30, alcoholFree: 5, standard: 25 });
  assert.equal(result.total, 110350n);
  assert.equal(result.perRecipient, 3678n);
});

test("adds VAT at the quoted common rate or as a quoted amount", () => {
  const beforeVat = { ...quote, standard: "28", alcohol_free_price: "21", delivery: "4.50" };
  assert.equal(calculateQuote({ ...beforeVat, vat_basis: "rate", vat_rate: "20" }, order).total, 112800n);
  assert.equal(calculateQuote({ ...beforeVat, vat_basis: "amount", vat_amount: "188" }, order).total, 112800n);
  assert.equal(calculateQuote({ ...beforeVat, vat_basis: "none" }, order).total, 94000n);
});

test("counts whole-order delivery once and rounds VAT and per-recipient costs to pennies", () => {
  const result = calculateQuote(
    { ...quote, delivery_basis: "order", delivery: "9.99", standard: "0.01", alcohol_free_price: "0.01",
      fees: "0.01", vat_basis: "rate", vat_rate: "12.50" },
    order,
  );
  assert.equal(result.total, 1159n);
  assert.equal(result.perRecipient, 39n);
});

test("keeps a quote incomplete when delivery, fees, or VAT are missing", () => {
  const result = calculateQuote({ ...quote, delivery: "", fees: "", vat_basis: "" }, order);
  assert.equal(result.total, null);
  assert.deepEqual(result.missing, [
    "Delivery charge", "Other fees or confirmation there are none", "Whether the prices include VAT",
  ]);
  assert.equal(calculateQuote({ ...quote, vat_basis: "rate", vat_rate: "101" }, order).total, null);
  assert.equal(calculateQuote({ ...quote, vat_basis: "amount" }, order).total, null);
});

test("needs only relevant gift prices and rejects impossible counts", () => {
  const standardOnly = readOrder({ recipients: "30", addresses: "1", alcohol_free: "0" });
  const alcoholFreeOnly = readOrder({ recipients: "30", addresses: "1", alcohol_free: "30" });
  assert.equal(calculateQuote({ ...quote, alcohol_free_price: "", delivery: "0" }, standardOnly).total, 96000n);
  assert.equal(calculateQuote({ ...quote, standard: "", delivery: "0" }, alcoholFreeOnly).total, 75000n);
  assert.match(readOrder({ recipients: "1", addresses: "2", alcohol_free: "0" }).message, /within the recipient count/);
  assert.match(readOrder({ recipients: "30", addresses: "1", alcohol_free: "" }).message, /number of alcohol-free gifts/);
});
