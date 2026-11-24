const pounds = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const maximumBudget = 10000000000n;

export function parseGiftMoney(value) {
  const text = String(value ?? "");
  if (!/^(?:\d{1,9}(?:\.\d{1,2})?|\.\d{1,2})$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  const pence = BigInt(whole || "0") * 100n + BigInt(fraction.padEnd(2, "0"));
  return pence <= maximumBudget ? pence : null;
}

export function formatGiftMoney(pence) {
  return pounds.format(Number(pence) / 100);
}

function count(value) {
  const text = String(value ?? "");
  return /^\d{1,5}$/.test(text) && Number(text) <= 10000 ? Number(text) : null;
}

export function calculateGiftBudget(input) {
  const cap = parseGiftMoney(input.all_in_budget);
  const policyCapPerRecipient = parseGiftMoney(input.gift_policy_cap_per_recipient);
  if (cap === null || cap === 0n) {
    return {
      cap: null, deliveryTotal: null, fees: null, remaining: null, perRecipient: null,
      policyCapPerRecipient, shortfall: null, overBudget: false, policyLimited: false, unknown: [],
    };
  }

  const recipients = count(input.recipient_count);
  const singleUkDelivery = recipients === 1 && input.uk_only !== false && !input.international_needed;
  const addresses = count(input.delivery_address_count) || (singleUkDelivery ? 1 : null);
  const delivery = parseGiftMoney(input.estimated_delivery_charge);
  const fees = parseGiftMoney(input.estimated_other_fees);
  const wholeOrder = input.estimated_delivery_basis === "order";
  let deliveryTotal = null;
  const unknown = [];

  if (delivery === null) {
    unknown.push("delivery");
  } else if (wholeOrder || delivery === 0n) {
    deliveryTotal = delivery;
  } else if (addresses && (!recipients || addresses <= recipients)) {
    deliveryTotal = delivery * BigInt(addresses);
  } else {
    unknown.push("addresses");
  }
  if (fees === null) unknown.push("fees");
  if (!recipients) unknown.push("recipients");

  const difference = cap - (deliveryTotal ?? 0n) - (fees ?? 0n);
  const overBudget = difference < 0n;
  const remaining = overBudget ? 0n : difference;
  const average = recipients ? remaining / BigInt(recipients) : null;
  const policyLimited = average !== null && policyCapPerRecipient !== null && policyCapPerRecipient < average;

  return {
    cap,
    deliveryTotal,
    fees,
    remaining,
    perRecipient: policyLimited ? policyCapPerRecipient : average,
    policyCapPerRecipient,
    shortfall: overBudget ? -difference : null,
    overBudget,
    policyLimited,
    unknown,
  };
}

export function giftQuoteParams(input) {
  const params = new URLSearchParams();
  const recipients = count(input.recipient_count);
  const addresses = count(input.delivery_address_count);
  const alcoholFree = count(input.alcohol_free_count);
  const budget = parseGiftMoney(input.all_in_budget);
  if (recipients) params.set("recipients", recipients);
  if (addresses && (!recipients || addresses <= recipients)) params.set("addresses", addresses);
  if (alcoholFree !== null && (!recipients || alcoholFree <= recipients)) params.set("alcohol_free", alcoholFree);
  if (budget !== null && budget > 0n) params.set("budget", String(input.all_in_budget));
  return params;
}
