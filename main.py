import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field

load_dotenv()

PRODUCT_NAME = "ClientCellar"
BASE_DIR = Path(__file__).resolve().parent
OPENAI_ENABLED = bool(os.getenv("OPENAI_API_KEY"))
CSV_TEMPLATE = (
    "recipient_name,email,company,address_line_1,address_line_2,city,postcode,"
    "country,gift_message,notes"
)
DISCLAIMER = (
    "Drink responsibly. ClientCellar provides planning guidance only and does not "
    "verify live stock, pricing, delivery, suitability or supplier availability. "
    "Alcohol gifting, licensing, customs and delivery rules should be confirmed "
    "directly with the supplier."
)

app = FastAPI(title=PRODUCT_NAME)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


SUPPLIERS = [
    {
        "id": "majestic",
        "name": "Majestic",
        "category": "wine_merchant",
        "typical_budget_min": 10,
        "typical_budget_max": 150,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK"],
        "website_url": "https://www.majestic.co.uk/",
        "affiliate_url": None,
        "enquiry_url": "https://www.majestic.co.uk/services/corporate",
        "notes": "Well-known UK wine merchant suitable for practical bottle and case options.",
        "best_for": ["staff gifts", "mixed cases", "budget guidance", "larger UK orders"],
    },
    {
        "id": "laithwaites",
        "name": "Laithwaites",
        "category": "wine_merchant",
        "typical_budget_min": 25,
        "typical_budget_max": 200,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.laithwaites.co.uk/",
        "affiliate_url": None,
        "enquiry_url": "https://www.laithwaites.co.uk/",
        "notes": "Established mail-order wine merchant; confirm corporate options directly.",
        "best_for": ["mixed cases", "staff gifts", "client-safe classics"],
    },
    {
        "id": "virgin-wines",
        "name": "Virgin Wines",
        "category": "wine_merchant",
        "typical_budget_min": 25,
        "typical_budget_max": 180,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.virginwines.co.uk/",
        "affiliate_url": None,
        "enquiry_url": "https://www.virginwines.co.uk/",
        "notes": "Online wine merchant; useful for cases and gift-led selections.",
        "best_for": ["employee gifts", "virtual tasting packs", "mixed cases"],
    },
    {
        "id": "wine-society",
        "name": "The Wine Society",
        "category": "wine_merchant",
        "typical_budget_min": 20,
        "typical_budget_max": 250,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK"],
        "website_url": "https://www.thewinesociety.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.thewinesociety.com/",
        "notes": "Member-owned wine merchant; confirm membership and corporate order details.",
        "best_for": ["quality-led gifts", "classic styles", "tastings"],
    },
    {
        "id": "berry-bros-rudd",
        "name": "Berry Bros. & Rudd",
        "category": "wine_merchant",
        "typical_budget_min": 50,
        "typical_budget_max": 1000,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK", "London", "International"],
        "website_url": "https://www.bbr.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.bbr.com/corporate",
        "notes": "Fine wine merchant with corporate gifting and event routes to confirm.",
        "best_for": ["premium clients", "fine wine", "private tastings"],
    },
    {
        "id": "fortnum-mason",
        "name": "Fortnum & Mason",
        "category": "hamper_company",
        "typical_budget_min": 45,
        "typical_budget_max": 500,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK", "International"],
        "website_url": "https://www.fortnumandmason.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.fortnumandmason.com/corporate-gifting",
        "notes": "Premium hamper and gifting option; confirm alcohol delivery rules by destination.",
        "best_for": ["premium hampers", "board-level gifts", "branded corporate gifting"],
    },
    {
        "id": "harvey-nichols-hampers",
        "name": "Harvey Nichols hampers",
        "category": "hamper_company",
        "typical_budget_min": 40,
        "typical_budget_max": 350,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.harveynichols.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.harveynichols.com/",
        "notes": "Retailer hamper route for polished food and drink gifts.",
        "best_for": ["stylish hampers", "client gifts", "premium employee gifts"],
    },
    {
        "id": "selfridges-hampers",
        "name": "Selfridges hampers",
        "category": "hamper_company",
        "typical_budget_min": 45,
        "typical_budget_max": 500,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.selfridges.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.selfridges.com/",
        "notes": "Department store gifting option; check corporate ordering and lead times.",
        "best_for": ["premium hampers", "recognisable retailer gifts"],
    },
    {
        "id": "marks-spencer-corporate",
        "name": "M&S corporate gifts",
        "category": "corporate_gifting",
        "typical_budget_min": 15,
        "typical_budget_max": 150,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.marksandspencer.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.marksandspencer.com/corporate-gifts",
        "notes": "Accessible UK retailer for practical staff and corporate gifts.",
        "best_for": ["budget staff gifts", "broad appeal", "simple logistics"],
    },
    {
        "id": "waitrose-cellar",
        "name": "Waitrose Cellar",
        "category": "wine_merchant",
        "typical_budget_min": 10,
        "typical_budget_max": 120,
        "bulk_orders": False,
        "corporate_gifting": False,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": "https://www.waitrosecellar.com/",
        "affiliate_url": None,
        "enquiry_url": "https://www.waitrosecellar.com/",
        "notes": "Practical consumer wine route; confirm suitability for bulk corporate ordering.",
        "best_for": ["low-risk bottle ideas", "small orders", "classic styles"],
    },
    {
        "id": "english-sparkling-producers",
        "name": "English sparkling wine producers category",
        "category": "english_sparkling",
        "typical_budget_min": 30,
        "typical_budget_max": 120,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK", "England"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Use this category to shortlist suitable English sparkling producers for celebratory gifting.",
        "best_for": ["sparkling gifts", "UK-focused clients", "premium alternatives to Champagne"],
    },
    {
        "id": "champagne-gifting",
        "name": "Champagne gifting category",
        "category": "champagne_sparkling",
        "typical_budget_min": 40,
        "typical_budget_max": 250,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK", "International"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Category placeholder for Champagne-led suppliers and merchants.",
        "best_for": ["celebrations", "premium clients", "safe impressive gifts"],
    },
    {
        "id": "independent-merchant",
        "name": "Independent wine merchant category",
        "category": "wine_merchant",
        "typical_budget_min": 20,
        "typical_budget_max": 200,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": False,
        "in_person_event_available": True,
        "regions": ["UK", "Local"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Use a reputable local merchant when advice, flexibility or delivery coordination matters.",
        "best_for": ["local delivery", "bespoke picks", "regional events"],
    },
    {
        "id": "local-tasting-host",
        "name": "Local wine tasting host category",
        "category": "wine_tasting",
        "typical_budget_min": 35,
        "typical_budget_max": 120,
        "bulk_orders": False,
        "corporate_gifting": False,
        "personalisation": True,
        "branding": False,
        "uk_delivery": False,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": False,
        "in_person_event_available": True,
        "regions": ["UK", "Local"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Good for in-person team socials or client entertainment; venue and licensing need confirmation.",
        "best_for": ["in-person tastings", "team socials", "client entertainment"],
    },
    {
        "id": "virtual-tasting-provider",
        "name": "Virtual wine tasting provider category",
        "category": "virtual_tasting",
        "typical_budget_min": 25,
        "typical_budget_max": 90,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": False,
        "regions": ["UK", "Remote"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Category for hosted online tastings with participant packs.",
        "best_for": ["remote teams", "hybrid teams", "lightweight planning"],
    },
    {
        "id": "corporate-hamper-supplier",
        "name": "Corporate hamper supplier category",
        "category": "corporate_gifting",
        "typical_budget_min": 25,
        "typical_budget_max": 250,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK", "International"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Useful when branded packaging, recipient lists and bulk fulfilment are priorities.",
        "best_for": ["branded gifts", "large recipient lists", "procurement-friendly fulfilment"],
    },
    {
        "id": "premium-client-gift",
        "name": "Premium client gift supplier category",
        "category": "corporate_gifting",
        "typical_budget_min": 75,
        "typical_budget_max": 500,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK", "International"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Category for higher-touch gifts where presentation and service matter.",
        "best_for": ["VIP clients", "board gifts", "high-value accounts"],
    },
    {
        "id": "budget-staff-gift",
        "name": "Budget staff gift supplier category",
        "category": "corporate_gifting",
        "typical_budget_min": 10,
        "typical_budget_max": 35,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": False,
        "virtual_event_available": False,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Use for broad employee gifting where cost control and simple fulfilment matter.",
        "best_for": ["staff gifts", "large teams", "lower budgets"],
    },
    {
        "id": "wine-cheese-hamper",
        "name": "Wine and cheese hamper category",
        "category": "hamper_company",
        "typical_budget_min": 35,
        "typical_budget_max": 150,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": False,
        "regions": ["UK"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Hamper format can feel safer than a single bottle when tastes are unknown.",
        "best_for": ["unknown tastes", "warm thank-yous", "virtual tasting add-ons"],
    },
    {
        "id": "team-building-event",
        "name": "Team-building wine event provider category",
        "category": "experience_provider",
        "typical_budget_min": 40,
        "typical_budget_max": 150,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": False,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK", "Remote"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Category for hosted, structured wine activities rather than heavy drinking sessions.",
        "best_for": ["team building", "away days", "sales kick-offs"],
    },
    {
        "id": "alcohol-free-gifting",
        "name": "Alcohol-free corporate gifting category",
        "category": "corporate_gifting",
        "typical_budget_min": 15,
        "typical_budget_max": 100,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": True,
        "branding": True,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK", "International"],
        "website_url": None,
        "affiliate_url": None,
        "enquiry_url": None,
        "notes": "Important alternative for inclusivity, HR sensitivity and non-drinkers.",
        "best_for": ["employee gifts", "inclusive options", "mixed preferences"],
    },
]


class GiftPlanRequest(BaseModel):
    recipient_type: Literal["clients", "employees", "suppliers", "prospects", "partners", "mixed"]
    recipient_count: int = Field(gt=0, le=10000)
    budget_per_recipient: float = Field(gt=0, le=10000)
    occasion: str = Field(min_length=1, max_length=160)
    gift_style: Literal["wine", "wine_hamper", "sparkling", "mixed_case", "not_sure"]
    tone: Literal["safe", "premium", "impressive", "warm", "low_risk"]
    uk_only: bool = True
    international_needed: bool = False
    personal_message_needed: bool = False
    branding_needed: bool = False
    delivery_deadline: str | None = None
    known_preferences: str | None = None
    avoid: str | None = None


class EventPlanRequest(BaseModel):
    event_type: Literal[
        "team_social",
        "client_entertainment",
        "christmas_party",
        "sales_kickoff",
        "away_day",
        "virtual_event",
        "not_sure",
    ]
    attendee_count: int = Field(gt=0, le=10000)
    budget_per_person: float = Field(gt=0, le=10000)
    format: Literal["virtual", "in_person", "hybrid", "not_sure"]
    location: str | None = None
    tone: Literal["fun", "premium", "educational", "client_safe", "informal"]
    date: str | None = None
    wine_knowledge_level: Literal["beginner", "mixed", "enthusiast"]
    food_pairing_needed: bool = False
    known_preferences: str | None = None


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=160)
    message: str = Field(min_length=1, max_length=2000)


def money(value: float) -> str:
    return f"£{value:,.0f}"


def readable(value: str) -> str:
    return value.replace("_", " ")


def supplier_url(supplier: dict) -> str | None:
    return supplier.get("enquiry_url") or supplier.get("website_url")


def budget_label(value: float, per: str = "recipient") -> str:
    if per == "recipient":
        if value < 20:
            return "tight"
        if value <= 40:
            return "practical"
        if value <= 75:
            return "strong"
        return "premium"
    if value < 25:
        return "lean"
    if value <= 60:
        return "solid"
    if value <= 120:
        return "premium"
    return "very premium"


def rank_gift_supplier(supplier: dict, req: GiftPlanRequest) -> int:
    score = 0
    budget = req.budget_per_recipient
    if supplier["typical_budget_min"] <= budget <= supplier["typical_budget_max"]:
        score += 5
    elif budget >= supplier["typical_budget_min"] * 0.75:
        score += 2
    if req.branding_needed and supplier["branding"]:
        score += 5
    if req.personal_message_needed and supplier["personalisation"]:
        score += 3
    if req.international_needed and supplier["international_delivery"]:
        score += 4
    if req.uk_only and supplier["uk_delivery"]:
        score += 2
    if req.recipient_count > 20 and supplier["bulk_orders"]:
        score += 3
    if req.gift_style == "wine_hamper" and supplier["category"] in {"hamper_company", "corporate_gifting"}:
        score += 5
    if req.gift_style == "sparkling" and supplier["category"] in {"champagne_sparkling", "english_sparkling"}:
        score += 5
    if req.gift_style == "mixed_case" and supplier["category"] == "wine_merchant":
        score += 4
    if req.recipient_type in {"clients", "prospects", "partners"} and supplier["corporate_gifting"]:
        score += 3
    if req.recipient_type == "employees" and "staff gifts" in supplier["best_for"]:
        score += 4
    return score


def rank_event_supplier(supplier: dict, req: EventPlanRequest) -> int:
    score = 0
    budget = req.budget_per_person
    if not supplier["event_available"]:
        return -10
    if supplier["typical_budget_min"] <= budget <= supplier["typical_budget_max"]:
        score += 5
    if req.format == "virtual" and supplier["virtual_event_available"]:
        score += 6
    if req.format == "in_person" and supplier["in_person_event_available"]:
        score += 6
    if req.format == "hybrid" and supplier["virtual_event_available"] and supplier["in_person_event_available"]:
        score += 5
    if req.event_type == "client_entertainment" and supplier["corporate_gifting"]:
        score += 3
    if req.food_pairing_needed and supplier["category"] in {"hamper_company", "experience_provider", "wine_tasting"}:
        score += 3
    if req.attendee_count > 20 and supplier["bulk_orders"]:
        score += 2
    return score


def gift_types(req: GiftPlanRequest) -> list[str]:
    budget = req.budget_per_recipient
    if budget < 20:
        options = [
            "Simple staff gift or single modest bottle where appropriate",
            "Small sparkling alternative or alcohol-free option",
            "Gift card or non-wine alternative if delivery makes wine too tight",
        ]
    elif budget <= 40:
        options = [
            "Good single bottle with broad appeal",
            "Small wine and food hamper",
            "Sparkling wine alternative for celebration moments",
        ]
    elif budget <= 75:
        options = [
            "Wine hamper with one strong bottle and useful extras",
            "Classic Rioja Reserva, Ribera-style red, white Burgundy-style alternative or mixed red/white gift",
            "English sparkling or Champagne alternative",
        ]
    else:
        options = [
            "Premium Champagne, English sparkling or fine wine merchant gift",
            "Luxury hamper with personal message",
            "Bespoke client gift via corporate gifting supplier",
        ]
    if req.gift_style == "wine_hamper":
        options.insert(0, "Wine hamper to reduce taste risk and improve presentation")
    if req.gift_style == "sparkling":
        options.insert(0, "Sparkling-led gift for a safer celebratory feel")
    if req.gift_style == "not_sure":
        options.insert(0, "Low-risk mixed red/white, sparkling, or hamper route")
    return list(dict.fromkeys(options))


def build_supplier_shortlist(items: list[dict], why_prefix: str, budget: float) -> list[dict]:
    shortlist = []
    for supplier in items[:5]:
        shortlist.append(
            {
                "name": supplier["name"],
                "category": readable(supplier["category"]),
                "why": f"{why_prefix} {supplier['notes']}",
                "budget_fit": f"Typical planning range {money(supplier['typical_budget_min'])}-{money(supplier['typical_budget_max'])}. Confirm current pricing directly.",
                "url": supplier_url(supplier),
                "affiliate_url": supplier["affiliate_url"],
            }
        )
    return shortlist


def maybe_improve_plan(plan: dict, plan_type: str) -> dict:
    if not OPENAI_ENABLED:
        return plan
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "Rewrite only the customer-facing wording in this JSON for clarity and UK business tone. "
            "Do not add suppliers, capabilities, prices, claims, live availability, links, or facts. "
            "Keep the JSON keys and data structure exactly equivalent.\n\n"
            f"Plan type: {plan_type}\nJSON:\n{json.dumps(plan, ensure_ascii=False)}"
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        improved = json.loads(response.choices[0].message.content or "{}")
        if set(improved.keys()) == set(plan.keys()):
            return improved
    except Exception:
        return plan
    return plan


def make_gift_plan(req: GiftPlanRequest) -> dict:
    total = req.recipient_count * req.budget_per_recipient
    label = budget_label(req.budget_per_recipient)
    ranked = sorted(SUPPLIERS, key=lambda supplier: rank_gift_supplier(supplier, req), reverse=True)
    shortlist = build_supplier_shortlist(ranked, "Good fit for this brief.", req.budget_per_recipient)

    strategy = {
        "tight": "Keep the brief simple: prioritise fulfilment, inclusive alternatives and a recognisable option over impressive packaging.",
        "practical": "Choose a broad-appeal bottle, small hamper or sparkling alternative, with clear delivery data and a short gift note.",
        "strong": "Use a wine hamper, English sparkling, Champagne alternative or mixed case to balance polish with low taste risk.",
        "premium": "Use a fine wine merchant or premium corporate gifting supplier, and spend effort on presentation, message quality and delivery control.",
    }[label]

    avoid = [
        "Avoid obscure or divisive bottles for clients, prospects and mixed groups.",
        "Avoid assuming every recipient drinks alcohol; include an alcohol-free route.",
        "Avoid promising delivery dates, stock or personalised packaging until the supplier confirms in writing.",
    ]
    if req.international_needed:
        avoid.append("Avoid sending alcohol internationally without checking customs, tax, age verification and courier rules by country.")
    if req.avoid:
        avoid.append(f"Respect the stated avoid list: {req.avoid}.")

    templates_out = [
        f"Thank you for your support. We hope you enjoy this {req.occasion.lower()} gift from the team.",
        "With thanks from all of us. Wishing you a restful break and a successful year ahead.",
        "A small thank-you for working with us. We appreciate the partnership.",
    ]
    if req.recipient_type == "employees":
        templates_out.append("Thank you for your work and energy this year. Please choose the option that suits you best.")

    subject = f"Corporate wine gift enquiry for {req.recipient_count} recipients"
    body = (
        f"Hello,\n\nWe are planning {req.occasion} gifts for {req.recipient_count} {readable(req.recipient_type)}. "
        f"Our planning budget is {money(req.budget_per_recipient)} per recipient, excluding any delivery or fulfilment charges unless you advise otherwise.\n\n"
        f"Preferred style: {readable(req.gift_style)}\nTone: {readable(req.tone)}\n"
        f"Personal messages needed: {'yes' if req.personal_message_needed else 'no'}\n"
        f"Branding needed: {'yes' if req.branding_needed else 'no'}\n"
        f"UK-only delivery: {'yes' if req.uk_only else 'no'}\n"
        f"International delivery needed: {'yes' if req.international_needed else 'no'}\n"
        f"Delivery deadline: {req.delivery_deadline or 'to be confirmed'}\n"
        f"Known preferences: {req.known_preferences or 'not known'}\n"
        f"Avoid: {req.avoid or 'none stated'}\n\n"
        "Could you confirm suitable options, current pricing, lead times, delivery coverage, minimum order quantities and any recipient data format you require?\n\n"
        "Kind regards"
    )

    next_steps = [
        "Confirm recipient count, addresses and any alcohol-free requirements.",
        "Ask two or three suppliers for current pricing, delivery cut-offs and data requirements.",
        "Prepare the recipient CSV and gift message before approving the order.",
        "Keep procurement, tax and HR approval notes with the supplier quote.",
    ]
    if req.branding_needed:
        next_steps.insert(1, "Confirm branding artwork specs, proofing time and minimum order quantity.")

    plan = {
        "headline": f"{PRODUCT_NAME} gift plan: {label} {readable(req.recipient_type)} gifting",
        "summary": f"Plan {req.recipient_count} {readable(req.recipient_type)} gifts for {req.occasion} at around {money(req.budget_per_recipient)} each.",
        "estimated_total_budget": f"{money(total)} before confirmed delivery, VAT, packaging or fulfilment extras.",
        "recommended_strategy": strategy,
        "recommended_gift_types": gift_types(req),
        "supplier_shortlist": shortlist,
        "what_to_avoid": avoid,
        "message_templates": templates_out,
        "supplier_enquiry_email": {"subject": subject, "body": body},
        "recipient_csv_template": CSV_TEMPLATE,
        "next_steps": next_steps,
        "disclaimer": DISCLAIMER,
    }
    return maybe_improve_plan(plan, "gift")


def event_structure(req: EventPlanRequest) -> list[str]:
    budget = req.budget_per_person
    if budget < 25:
        structure = [
            "45-minute informal tasting with two accessible wines or alcohol-free alternatives",
            "Simple introduction, guided tasting notes and relaxed discussion",
            "Use supermarket or merchant packs if a hosted provider is out of range",
        ]
    elif budget <= 60:
        structure = [
            "60-75 minute hosted tasting with three wines and optional snack pairing",
            "Beginner-friendly host, light structure and clear joining instructions",
            "Ship packs at least a week before the event where virtual or hybrid",
        ]
    elif budget <= 120:
        structure = [
            "90-minute hosted event with premium wines and a polished client-safe format",
            "Optional food pairing, private room or structured team activity",
            "Keep pours modest and include alcohol-free alternatives",
        ]
    else:
        structure = [
            "Premium private tasting with fine wine, food pairing and a dedicated host",
            "Confirm venue, licensing, service, dietary requirements and transport plan",
            "Use a concierge-style supplier and agree a clear run sheet",
        ]
    if req.tone == "client_safe" or req.event_type == "client_entertainment":
        structure.append("Keep the tone polished, not too boozy, with a clear finish time.")
    if req.food_pairing_needed:
        structure.append("Add food pairing early, as it changes venue, delivery and dietary planning.")
    return structure


def make_event_plan(req: EventPlanRequest) -> dict:
    total = req.attendee_count * req.budget_per_person
    label = budget_label(req.budget_per_person, "attendee")
    ranked = sorted(SUPPLIERS, key=lambda supplier: rank_event_supplier(supplier, req), reverse=True)
    shortlist = build_supplier_shortlist(
        [supplier for supplier in ranked if rank_event_supplier(supplier, req) >= 0],
        "Relevant for event planning.",
        req.budget_per_person,
    )
    if not shortlist:
        shortlist = build_supplier_shortlist(
            [supplier for supplier in SUPPLIERS if supplier["event_available"]],
            "Potential event route.",
            req.budget_per_person,
        )

    format_copy = {
        "virtual": "Hosted virtual tasting with delivered packs",
        "in_person": "In-person tasting with a local host, merchant or venue",
        "hybrid": "Hybrid event with careful pack delivery and room facilitation",
        "not_sure": "Start with virtual or local in-person quotes and compare logistics",
    }[req.format]
    if req.budget_per_person < 25:
        format_copy = "Simple virtual or informal tasting, keeping pack cost and delivery under control"
    elif req.budget_per_person > 120:
        format_copy = "Premium hosted event with fine wine, food pairing and a private-room style experience"

    avoid = [
        "Avoid making the event too alcohol-led; keep education, food and pacing in the plan.",
        "Avoid assuming all attendees drink alcohol; offer alcohol-free alternatives.",
        "Avoid confirming dates until supplier availability, delivery, licensing and venue rules are checked.",
    ]
    if req.event_type == "client_entertainment":
        avoid.append("Avoid novelty formats that could feel awkward for clients or prospects.")

    subject = f"Corporate wine tasting enquiry for {req.attendee_count} attendees"
    body = (
        f"Hello,\n\nWe are planning a {readable(req.event_type)} wine tasting for around {req.attendee_count} attendees. "
        f"Our planning budget is {money(req.budget_per_person)} per person.\n\n"
        f"Preferred format: {readable(req.format)}\n"
        f"Location: {req.location or 'to be confirmed'}\n"
        f"Date: {req.date or 'to be confirmed'}\n"
        f"Tone: {readable(req.tone)}\n"
        f"Wine knowledge level: {readable(req.wine_knowledge_level)}\n"
        f"Food pairing needed: {'yes' if req.food_pairing_needed else 'no'}\n"
        f"Known preferences: {req.known_preferences or 'not known'}\n\n"
        "Could you confirm suitable formats, current pricing, host availability, delivery or venue requirements, alcohol-free options and any licensing considerations?\n\n"
        "Kind regards"
    )
    invite = (
        f"You are invited to a {readable(req.event_type)} wine tasting. The session will be {readable(req.tone)} "
        "and beginner-friendly, with alcohol-free alternatives available. Full details will follow once the supplier and date are confirmed."
    )

    plan = {
        "headline": f"{PRODUCT_NAME} event plan: {label} {readable(req.event_type)}",
        "summary": f"Plan for {req.attendee_count} attendees at around {money(req.budget_per_person)} per person.",
        "estimated_total_budget": f"{money(total)} before confirmed VAT, delivery, venue, service or food costs.",
        "recommended_format": format_copy,
        "event_structure": event_structure(req),
        "supplier_shortlist": shortlist,
        "what_to_avoid": avoid,
        "supplier_enquiry_email": {"subject": subject, "body": body},
        "internal_invite_copy": invite,
        "next_steps": [
            "Confirm date options, attendee count and any dietary or alcohol-free requirements.",
            "Ask shortlisted suppliers for current pricing, availability, delivery and licensing details.",
            "Choose the format that is easiest for attendees and safest for the business context.",
            "Share joining instructions, start time, finish time and responsible drinking expectations.",
        ],
        "disclaimer": DISCLAIMER,
    }
    return maybe_improve_plan(plan, "event")


def render(request: Request, template: str, title: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"title": title, "product": PRODUCT_NAME},
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html", "Corporate wine gifts and tasting events made simple")


@app.get("/gift-planner", response_class=HTMLResponse)
def gift_planner(request: Request):
    return render(request, "gift_planner.html", "Gift planner")


@app.get("/event-planner", response_class=HTMLResponse)
def event_planner(request: Request):
    return render(request, "event_planner.html", "Event planner")


@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return render(request, "pricing.html", "Pricing")


@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request):
    return render(request, "faq.html", "FAQ")


@app.get("/contact", response_class=HTMLResponse)
def contact(request: Request):
    return render(request, "contact.html", "Contact")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "product": PRODUCT_NAME,
        "openai_enabled": OPENAI_ENABLED,
        "supplier_count": len(SUPPLIERS),
    }


@app.get("/api/suppliers")
def suppliers():
    return {"suppliers": SUPPLIERS, "count": len(SUPPLIERS), "disclaimer": DISCLAIMER}


@app.post("/api/gift-plan")
def gift_plan(req: GiftPlanRequest):
    return make_gift_plan(req)


@app.post("/api/event-plan")
def event_plan(req: EventPlanRequest):
    return make_event_plan(req)


@app.post("/api/contact")
def contact_submit(req: ContactRequest):
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    record = req.model_dump()
    record["created_at"] = datetime.utcnow().isoformat() + "Z"
    with (data_dir / "contact_messages.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(f"Contact enquiry from {req.email}: {req.company or 'No company'}")
    return {"ok": True, "message": "Thanks. Your enquiry has been logged for follow-up."}
