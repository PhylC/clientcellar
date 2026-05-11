import csv
import io
import json
import logging
import math
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field, field_validator

from data.supplier_links import (
    SUPPLIER_LINK_CONFIG,
    get_supplier_link,
    supplier_affiliate_url as configured_supplier_affiliate_url,
    supplier_url as configured_supplier_url,
)
from data.suppliers import SUPPLIER_ENTRIES

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("clientcellar")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

PRODUCT_NAME = "ClientCellar"
DEFAULT_PAGE_TITLE = "ClientCellar | Corporate Wine Gifts and Tasting Event Planning"
DEFAULT_META_DESCRIPTION = (
    "Plan corporate wine gifts, staff gifts and tasting events with budget guidance, "
    "copy-ready business documents and practical checklists."
)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "clientcellar.db"
OPENAI_ENABLED = bool(os.getenv("OPENAI_API_KEY"))
PACK_ACCESS_REQUEST_COUNTS: dict[str, int] = {}
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
CANONICAL_ORIGIN = "https://clientcellar.co.uk"
CANONICAL_HOST = "clientcellar.co.uk"
WWW_HOST = "www.clientcellar.co.uk"

app = FastAPI(title=PRODUCT_NAME)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
logger.info(
    "RESEND_ENABLED=%s EMAIL_FROM_SET=%s",
    bool(os.getenv("RESEND_API_KEY")),
    bool(os.getenv("EMAIL_FROM")),
)


SITEMAP_STATIC_ROUTES = [
    "/",
    "/gift-planner",
    "/event-planner",
    "/guides",
    "/suppliers",
    "/pricing",
    "/example-premium-brief-pack",
    "/faq",
    "/about",
    "/contact",
    "/terms",
    "/privacy-policy",
    "/affiliate-disclosure",
    "/editorial-policy",
    "/supplier-partnerships",
    "/supplier-application",
    "/responsible-drinking",
    "/copyright",
    "/cookies",
    "/guides",
    "/premium-pack",
    "/corporate-wine-gifts",
    "/corporate-wine-tasting-events",
    "/client-wine-gifts",
    "/staff-wine-gifts",
    "/corporate-christmas-wine-gifts",
]
SITEMAP_EXCLUDED_GUIDE_SLUGS = {"corporate-champagne-gifts"}


def canonical_path(path: str) -> str:
    clean_path = urllib.parse.urlsplit(path or "/").path or "/"
    if not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"
    if clean_path != "/":
        clean_path = clean_path.rstrip("/")
    return clean_path or "/"


def canonical_url_for_path(path: str = "/") -> str:
    return f"{CANONICAL_ORIGIN}{canonical_path(path)}"


def first_header_value(value: str | None) -> str:
    return (value or "").split(",", 1)[0].strip()


def normalise_host(value: str | None) -> str:
    host = first_header_value(value).lower()
    if not host:
        return ""
    return host.split(":", 1)[0]


def forwarded_header_parts(value: str | None) -> dict[str, str]:
    parts: dict[str, str] = {}
    for item in first_header_value(value).split(";"):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        parts[key.strip().lower()] = raw_value.strip().strip('"')
    return parts


def is_render_host(host: str) -> bool:
    return host.endswith(".onrender.com") or host.endswith(".render.com")


@app.middleware("http")
async def canonical_redirect_middleware(request: Request, call_next):
    forwarded_parts = forwarded_header_parts(request.headers.get("forwarded"))
    forwarded_host = normalise_host(forwarded_parts.get("host") or request.headers.get("x-forwarded-host"))
    host = forwarded_host or normalise_host(request.headers.get("host"))
    forwarded_proto = first_header_value(forwarded_parts.get("proto") or request.headers.get("x-forwarded-proto")).lower()
    scheme = forwarded_proto or request.url.scheme
    path = request.url.path
    clean_path = canonical_path(path)
    should_redirect_host = host == WWW_HOST or is_render_host(host)
    should_redirect_scheme = host in {CANONICAL_HOST, WWW_HOST} and scheme == "http"
    should_redirect_path = path != clean_path
    if should_redirect_host or should_redirect_scheme or should_redirect_path:
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{CANONICAL_ORIGIN}{clean_path}{query}", status_code=301)
    return await call_next(request)


def payments_enabled() -> bool:
    return (
        os.getenv("PAYMENTS_ENABLED", "").lower() == "true"
        and bool(os.getenv("STRIPE_SECRET_KEY"))
        and bool(os.getenv("STRIPE_PRICE_ID"))
        and bool(os.getenv("APP_BASE_URL"))
    )


def supabase_settings() -> dict:
    url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("VITE_SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).strip().rstrip("/")
    anon_key = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("VITE_SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "url": url,
        "anon_key": anon_key,
        "service_role_key": service_role_key,
        "configured": bool(url and anon_key),
        "service_configured": bool(url and service_role_key),
    }


def _supabase_json_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    payload: dict | None = None,
    timeout: int = 8,
) -> dict | list | None:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=401, detail="Account session could not be verified.") from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Account service is temporarily unavailable.") from error
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def get_supabase_admin():
    """Create a server-side Supabase admin client when supabase-py is available."""
    settings = supabase_settings()
    if not settings["service_configured"]:
        return None
    try:
        from supabase import create_client
    except Exception:
        return None
    return create_client(settings["url"], settings["service_role_key"])


def verify_supabase_access_token(access_token: str | None) -> dict | None:
    if not access_token:
        return None
    settings = supabase_settings()
    if not settings["configured"]:
        return None
    try:
        data = _supabase_json_request(
            f"{settings['url']}/auth/v1/user",
            headers={
                "apikey": settings["anon_key"],
                "Authorization": f"Bearer {access_token}",
            },
        )
    except HTTPException:
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


def fetch_supabase_profile(user_id: str, access_token: str) -> dict:
    settings = supabase_settings()
    if not settings["configured"]:
        return {}
    encoded_id = urllib.parse.quote(user_id, safe="")
    data = _supabase_json_request(
        f"{settings['url']}/rest/v1/profiles?id=eq.{encoded_id}&select=id,email,plan,subscription_status,stripe_customer_id,stripe_subscription_id,updated_at",
        headers={
            "apikey": settings["anon_key"],
            "Authorization": f"Bearer {access_token}",
        },
    )
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else {}
    return {}


def upsert_supabase_profile(user_id: str | None, fields: dict) -> None:
    settings = supabase_settings()
    if not user_id or not settings["service_configured"]:
        return
    payload = {
        "id": user_id,
        **{key: value for key, value in fields.items() if value is not None},
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if len(payload) <= 2:
        return

    admin = get_supabase_admin()
    if admin is not None:
        try:
            admin.table("profiles").upsert(payload).execute()
            return
        except Exception as error:
            print("Supabase admin client upsert failed; trying REST fallback:", str(error))

    try:
        _supabase_json_request(
            f"{settings['url']}/rest/v1/profiles",
            method="POST",
            headers={
                "apikey": settings["service_role_key"],
                "Authorization": f"Bearer {settings['service_role_key']}",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            payload=payload,
        )
    except HTTPException as error:
        print("Supabase profile upsert skipped:", error.detail)


def update_supabase_profile_from_payment(user_id: str | None, fields: dict) -> None:
    upsert_supabase_profile(user_id, fields)


def update_supabase_profile_by_subscription(subscription_id: str | None, fields: dict) -> None:
    settings = supabase_settings()
    if not subscription_id or not settings["service_configured"]:
        return
    encoded_id = urllib.parse.quote(subscription_id, safe="")
    payload = {
        **{key: value for key, value in fields.items() if value is not None},
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        _supabase_json_request(
            f"{settings['url']}/rest/v1/profiles?stripe_subscription_id=eq.{encoded_id}",
            method="PATCH",
            headers={
                "apikey": settings["service_role_key"],
                "Authorization": f"Bearer {settings['service_role_key']}",
                "Prefer": "return=minimal",
            },
            payload=payload,
        )
    except HTTPException as error:
        print("Supabase subscription profile update skipped:", error.detail)


def stripe_obj_get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_db_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_leads_db() -> None:
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                company TEXT,
                phone TEXT,
                interested_in TEXT NOT NULL,
                recipient_count INTEGER,
                budget_per_recipient REAL,
                occasion TEXT,
                deadline TEXT,
                message TEXT,
                consent_to_contact BOOLEAN NOT NULL,
                planner_input_json TEXT,
                planner_output_json TEXT,
                source_page TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS supplier_clicks (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                supplier_id TEXT NOT NULL,
                tracking_slug TEXT NOT NULL,
                destination_url TEXT NOT NULL,
                source_page TEXT,
                user_agent TEXT,
                referrer TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS supplier_applications (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                business_name TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                website TEXT,
                supplier_type TEXT NOT NULL,
                regions_covered TEXT NOT NULL,
                corporate_gifting BOOLEAN NOT NULL,
                wine_tasting_events BOOLEAN NOT NULL,
                virtual_events BOOLEAN NOT NULL,
                bulk_orders BOOLEAN NOT NULL,
                personalisation BOOLEAN NOT NULL,
                typical_budget_min REAL,
                typical_budget_max REAL,
                message TEXT,
                consent_to_contact BOOLEAN NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS premium_packs (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pack_token TEXT UNIQUE NOT NULL,
                access_token TEXT UNIQUE,
                pack_type TEXT NOT NULL,
                email TEXT,
                customer_email TEXT,
                payment_status TEXT NOT NULL,
                stripe_session_id TEXT,
                stripe_payment_intent TEXT,
                amount_total INTEGER,
                currency TEXT,
                planner_input_json TEXT,
                planner_output_json TEXT,
                premium_preview_json TEXT,
                generated_content_json TEXT,
                plan_id TEXT,
                title TEXT,
                access_count INTEGER DEFAULT 0,
                download_count INTEGER DEFAULT 0,
                last_accessed_at TEXT
            )
            """
        )
        _ensure_premium_pack_columns(connection)
        connection.commit()


def _ensure_premium_pack_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(premium_packs)").fetchall()
    }
    additional_columns = [
        ("updated_at", "TEXT"),
        ("access_token", "TEXT"),
        ("customer_email", "TEXT"),
        ("stripe_payment_intent", "TEXT"),
        ("amount_total", "INTEGER"),
        ("currency", "TEXT"),
        ("generated_content_json", "TEXT"),
        ("plan_id", "TEXT"),
        ("title", "TEXT"),
        ("access_count", "INTEGER DEFAULT 0"),
        ("download_count", "INTEGER DEFAULT 0"),
        ("last_accessed_at", "TEXT"),
    ]
    for column_name, column_type in additional_columns:
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE premium_packs ADD COLUMN {column_name} {column_type}")
    if "access_token" not in existing_columns:
        connection.execute("UPDATE premium_packs SET access_token = pack_token WHERE access_token IS NULL")


def generate_pack_token() -> str:
    """Generate a unique pack token for premium pack tracking."""
    import secrets
    return secrets.token_urlsafe(24)


def save_premium_pack(
    pack_token: str,
    pack_type: str,
    customer_email: str | None,
    payment_status: str,
    stripe_session_id: str | None = None,
    stripe_payment_intent: str | None = None,
    amount_total: int | None = None,
    currency: str | None = None,
    planner_input: dict | None = None,
    planner_output: dict | None = None,
    premium_preview: dict | None = None,
) -> int:
    """Save a premium pack order to the database."""
    init_leads_db()
    with get_db_connection() as connection:
        now = datetime.utcnow().isoformat() + "Z"
        cursor = connection.execute(
            """
            INSERT INTO premium_packs (
                created_at, updated_at, pack_token, access_token, pack_type, email,
                customer_email, payment_status, stripe_session_id,
                stripe_payment_intent, amount_total, currency,
                planner_input_json, planner_output_json, premium_preview_json,
                generated_content_json, title
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                pack_token,
                pack_token,
                pack_type,
                customer_email,
                customer_email,
                payment_status,
                stripe_session_id,
                stripe_payment_intent,
                amount_total,
                currency,
                json.dumps(planner_input) if planner_input else None,
                json.dumps(planner_output) if planner_output else None,
                json.dumps(premium_preview) if premium_preview else None,
                json.dumps(premium_preview) if premium_preview else None,
                (premium_preview or {}).get("pack_name") if premium_preview else None,
            ),
        )
        connection.commit()
        return cursor.lastrowid


def get_premium_pack(pack_token: str) -> dict | None:
    """Retrieve a premium pack order by token."""
    init_leads_db()
    with get_db_connection() as connection:
        cursor = connection.execute(
            "SELECT * FROM premium_packs WHERE pack_token = ? OR access_token = ?",
            (pack_token, pack_token)
        )
        row = cursor.fetchone()
        if not row:
            return None
        pack = dict(row)
        if pack.get("customer_email"):
            pack["customer_email"] = pack["customer_email"]
        elif pack.get("email"):
            pack["customer_email"] = pack["email"]
        if pack.get("planner_input_json"):
            pack["planner_input"] = json.loads(pack["planner_input_json"])
        if pack.get("planner_output_json"):
            pack["planner_output"] = json.loads(pack["planner_output_json"])
        if pack.get("premium_preview_json"):
            pack["premium_preview"] = json.loads(pack["premium_preview_json"])
        elif pack.get("generated_content_json"):
            pack["premium_preview"] = json.loads(pack["generated_content_json"])
        if pack.get("generated_content_json"):
            pack["generated_content"] = json.loads(pack["generated_content_json"])
        return pack


def fetch_paid_premium_packs_by_email(email: str) -> list[dict]:
    init_leads_db()
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM premium_packs
            WHERE lower(COALESCE(customer_email, email, '')) = lower(?)
              AND payment_status = 'paid'
            ORDER BY created_at DESC
            """,
            (email,),
        ).fetchall()
    packs = []
    for row in rows:
        pack = dict(row)
        pack["customer_email"] = pack.get("customer_email") or pack.get("email")
        pack["access_token"] = pack.get("access_token") or pack.get("pack_token")
        packs.append(pack)
    return packs


def count_premium_packs_by_email(email: str) -> dict:
    init_leads_db()
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT
              COUNT(*) AS total_count,
              SUM(CASE WHEN payment_status = 'paid' THEN 1 ELSE 0 END) AS paid_count
            FROM premium_packs
            WHERE lower(COALESCE(customer_email, email, '')) = lower(?)
            """,
            (email,),
        ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0) if row else 0,
        "paid_count": int(row["paid_count"] or 0) if row else 0,
    }


def update_premium_pack_payment(
    pack_token: str,
    payment_status: str,
    stripe_session_id: str | None = None,
    stripe_payment_intent: str | None = None,
    amount_total: int | None = None,
    currency: str | None = None,
    customer_email: str | None = None,
) -> bool:
    """Update premium pack payment details."""
    init_leads_db()
    with get_db_connection() as connection:
        now = datetime.utcnow().isoformat() + "Z"
        connection.execute(
            """
            UPDATE premium_packs
            SET
                payment_status = ?,
                stripe_session_id = COALESCE(?, stripe_session_id),
                stripe_payment_intent = COALESCE(?, stripe_payment_intent),
                amount_total = COALESCE(?, amount_total),
                currency = COALESCE(?, currency),
                customer_email = COALESCE(?, customer_email),
                updated_at = ?
            WHERE pack_token = ?
            """,
            (
                payment_status,
                stripe_session_id,
                stripe_payment_intent,
                amount_total,
                currency,
                customer_email,
                now,
                pack_token,
            ),
        )
        connection.commit()
        return True


def touch_premium_pack_access(pack_token: str) -> bool:
    init_leads_db()
    with get_db_connection() as connection:
        now = datetime.utcnow().isoformat() + "Z"
        connection.execute(
            """
            UPDATE premium_packs
            SET access_count = COALESCE(access_count, 0) + 1,
                last_accessed_at = ?,
                updated_at = ?
            WHERE pack_token = ?
            """,
            (now, now, pack_token),
        )
        connection.commit()
        return True


def increment_premium_pack_download(pack_token: str) -> bool:
    init_leads_db()
    with get_db_connection() as connection:
        now = datetime.utcnow().isoformat() + "Z"
        connection.execute(
            """
            UPDATE premium_packs
            SET download_count = COALESCE(download_count, 0) + 1,
                updated_at = ?
            WHERE pack_token = ?
            """,
            (now, pack_token),
        )
        connection.commit()
        return True


def update_premium_pack_preview(pack_token: str, premium_preview: dict) -> bool:
    init_leads_db()
    with get_db_connection() as connection:
        now = datetime.utcnow().isoformat() + "Z"
        connection.execute(
            """
            UPDATE premium_packs
            SET premium_preview_json = ?,
                generated_content_json = ?,
                title = COALESCE(?, title),
                updated_at = ?
            WHERE pack_token = ?
            """,
            (
                json.dumps(premium_preview),
                json.dumps(premium_preview),
                premium_preview.get("pack_name"),
                now,
                pack_token,
            ),
        )
        connection.commit()
        return True


def save_lead(lead: "LeadRequest") -> int:
    init_leads_db()
    with get_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                created_at, name, email, company, phone, interested_in,
                recipient_count, budget_per_recipient, occasion, deadline,
                message, consent_to_contact, planner_input_json,
                planner_output_json, source_page
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat() + "Z",
                lead.name.strip(),
                str(lead.email),
                lead.company,
                lead.phone,
                lead.interested_in,
                lead.recipient_count,
                lead.budget_per_recipient,
                lead.occasion,
                lead.deadline,
                lead.message,
                lead.consent_to_contact,
                json.dumps(lead.planner_input) if lead.planner_input else None,
                json.dumps(lead.planner_output) if lead.planner_output else None,
                lead.source_page,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def fetch_leads(limit: int | None = None) -> list[sqlite3.Row]:
    init_leads_db()
    query = "SELECT * FROM leads ORDER BY created_at DESC"
    params: tuple[int, ...] = ()
    if limit:
        query += " LIMIT ?"
        params = (limit,)
    with get_db_connection() as connection:
        return list(connection.execute(query, params).fetchall())


def save_supplier_click(
    supplier: dict,
    destination_url: str,
    source_page: str | None,
    user_agent: str | None,
    referrer: str | None,
) -> None:
    init_leads_db()
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO supplier_clicks (
                created_at, supplier_id, tracking_slug, destination_url,
                source_page, user_agent, referrer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat() + "Z",
                supplier["supplier_id"],
                supplier["tracking_slug"],
                destination_url,
                source_page,
                user_agent,
                referrer,
            ),
        )
        connection.commit()


def fetch_supplier_applications(limit: int | None = None) -> list[sqlite3.Row]:
    init_leads_db()
    query = "SELECT * FROM supplier_applications ORDER BY created_at DESC"
    params: tuple[int, ...] = ()
    if limit:
        query += " LIMIT ?"
        params = (limit,)
    with get_db_connection() as connection:
        return list(connection.execute(query, params).fetchall())


def save_supplier_application(application: "SupplierApplicationRequest") -> int:
    init_leads_db()
    affiliate_note = (
        "Affiliate/tracked links available: "
        f"{readable(application.affiliate_links_available)}"
    )
    message = "\n\n".join(part for part in [application.message, affiliate_note] if part)
    with get_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO supplier_applications (
                created_at, business_name, contact_name, email, phone, website,
                supplier_type, regions_covered, corporate_gifting,
                wine_tasting_events, virtual_events, bulk_orders,
                personalisation, typical_budget_min, typical_budget_max,
                message, consent_to_contact
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat() + "Z",
                application.business_name,
                application.contact_name,
                str(application.email),
                application.phone,
                application.website,
                application.supplier_type,
                application.regions_covered,
                application.corporate_gifting,
                application.wine_tasting_events,
                application.virtual_events,
                application.bulk_orders,
                application.personalisation,
                application.typical_budget_min,
                application.typical_budget_max,
                message,
                application.consent_to_contact,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


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
        "website_url": configured_supplier_url("majestic"),
        "affiliate_url": configured_supplier_affiliate_url("majestic"),
        "enquiry_url": configured_supplier_url("majestic"),
        "url_purpose": "Corporate gifting page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful starting point for corporate wine gifts and larger orders.",
        "best_for": ["business wine gifts", "case gifting", "broad UK coverage", "possible event wine conversations"],
        "use_cases": ["client wine gifts", "event wine", "larger orders"],
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
        "website_url": configured_supplier_url("laithwaites"),
        "affiliate_url": configured_supplier_affiliate_url("laithwaites"),
        "enquiry_url": configured_supplier_url("laithwaites"),
        "url_purpose": "Wine gifts page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for wine gift browsing and mixed cases.",
        "best_for": ["wine gift cases", "mixed wine gifts", "gift delivery"],
        "use_cases": ["client wine gifts", "mixed cases"],
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
        "website_url": configured_supplier_url("virgin-wines"),
        "affiliate_url": configured_supplier_affiliate_url("virgin-wines"),
        "enquiry_url": configured_supplier_url("virgin-wines"),
        "url_purpose": "Wine gifts page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for straightforward consumer-style gifting.",
        "best_for": ["accessible wine gifts", "mixed cases"],
        "use_cases": ["client wine gifts", "staff gifts"],
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
        "website_url": configured_supplier_url("wine-society"),
        "affiliate_url": configured_supplier_affiliate_url("wine-society"),
        "enquiry_url": configured_supplier_url("wine-society"),
        "url_purpose": "Wine gifts page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Membership model may apply; buyer should check suitability.",
        "best_for": ["quality-focused wine gifts", "thoughtful bottle choices"],
        "use_cases": ["client wine gifts", "premium gifts"],
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
        "website_url": configured_supplier_url("berry-bros-rudd"),
        "affiliate_url": configured_supplier_affiliate_url("berry-bros-rudd"),
        "enquiry_url": configured_supplier_url("berry-bros-rudd"),
        "url_purpose": "Fine wines range page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Better suited to higher-budget or more formal gifting.",
        "best_for": ["premium client gifts", "fine wine", "Champagne and luxury gifting"],
        "use_cases": ["premium client gifts", "fine wine gifts"],
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
        "website_url": configured_supplier_url("fortnum-mason"),
        "affiliate_url": configured_supplier_affiliate_url("fortnum-mason"),
        "enquiry_url": configured_supplier_url("fortnum-mason"),
        "url_purpose": "Hampers page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Suitable for higher-value gifting where presentation matters.",
        "best_for": ["premium hampers", "luxury client gifts", "formal gifting"],
        "use_cases": ["hampers", "premium client gifts"],
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
        "website_url": configured_supplier_url("harvey-nichols-hampers"),
        "affiliate_url": configured_supplier_affiliate_url("harvey-nichols-hampers"),
        "enquiry_url": configured_supplier_url("harvey-nichols-hampers"),
        "url_purpose": "Corporate gifts service page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Retailer hamper route for polished food and drink gifts.",
        "best_for": ["stylish hampers", "client gifts", "premium employee gifts"],
        "active": False,
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
        "website_url": configured_supplier_url("selfridges-hampers"),
        "affiliate_url": configured_supplier_affiliate_url("selfridges-hampers"),
        "enquiry_url": configured_supplier_url("selfridges-hampers"),
        "url_purpose": "Wine and food hampers page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Department store gifting option; check corporate ordering and lead times.",
        "best_for": ["premium hampers", "recognisable retailer gifts"],
        "active": False,
    },
    {
        "id": "marks-spencer-corporate",
        "name": "M&S Hampers",
        "category": "hamper_company",
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
        "website_url": configured_supplier_url("marks-spencer-corporate"),
        "affiliate_url": configured_supplier_affiliate_url("marks-spencer-corporate"),
        "enquiry_url": configured_supplier_url("marks-spencer-corporate"),
        "url_purpose": "Food and drink hampers page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for straightforward hamper gifting; check delivery, alcohol contents and dietary options before ordering.",
        "best_for": ["accessible food and drink hampers", "staff gifts", "mainstream client gifting"],
        "use_cases": ["hampers", "staff gifts"],
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
        "website_url": configured_supplier_url("waitrose-cellar"),
        "affiliate_url": configured_supplier_affiliate_url("waitrose-cellar"),
        "enquiry_url": configured_supplier_url("waitrose-cellar"),
        "url_purpose": "Wine gifts page",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for straightforward wine gifting.",
        "best_for": ["mainstream wine gifts", "Champagne"],
        "use_cases": ["wine gifts", "simple event wine"],
    },
    {
        "id": "john-lewis-hampers",
        "name": "John Lewis Hampers",
        "category": "hamper_company",
        "typical_budget_min": 25,
        "typical_budget_max": 250,
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
        "website_url": configured_supplier_url("john-lewis-hampers"),
        "affiliate_url": configured_supplier_affiliate_url("john-lewis-hampers"),
        "enquiry_url": configured_supplier_url("john-lewis-hampers"),
        "url_purpose": "Hampers category",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for general gifting and non-specialist buyers.",
        "best_for": ["food and drink hampers", "broad gifting"],
        "use_cases": ["hampers", "staff gifts", "mixed recipients"],
    },
    {
        "id": "local-independent-wine-merchant",
        "name": "Local independent wine merchant",
        "category": "wine_merchant",
        "typical_budget_min": 15,
        "typical_budget_max": 250,
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
        "url_purpose": "Search locally",
        "url_checked_date": "2026-05-10",
        "url_type": "search_guidance",
        "notes": "Search for \"independent wine merchant near me\" plus your town/city. Useful when you need practical advice and delivery support.",
        "best_for": ["event wine advice", "flexible case orders", "local delivery"],
        "use_cases": ["event wine", "local delivery", "advice-led gifts"],
    },
    {
        "id": "noughty-thomson-scott",
        "name": "Noughty / Thomson & Scott",
        "category": "non_alcoholic",
        "typical_budget_min": 10,
        "typical_budget_max": 80,
        "bulk_orders": True,
        "corporate_gifting": True,
        "personalisation": False,
        "branding": False,
        "uk_delivery": True,
        "international_delivery": True,
        "event_available": True,
        "virtual_event_available": True,
        "in_person_event_available": True,
        "regions": ["UK", "International"],
        "website_url": configured_supplier_url("noughty-thomson-scott"),
        "affiliate_url": configured_supplier_affiliate_url("noughty-thomson-scott"),
        "enquiry_url": configured_supplier_url("noughty-thomson-scott"),
        "url_purpose": "Non-alcoholic sparkling wine",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful where alcohol may not be suitable.",
        "best_for": ["alcohol-free sparkling gifts", "inclusive events"],
        "use_cases": ["non-alcoholic gifts", "inclusive events"],
    },
    {
        "id": "dry-drinker",
        "name": "Dry Drinker",
        "category": "non_alcoholic",
        "typical_budget_min": 10,
        "typical_budget_max": 100,
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
        "website_url": configured_supplier_url("dry-drinker"),
        "affiliate_url": configured_supplier_affiliate_url("dry-drinker"),
        "enquiry_url": configured_supplier_url("dry-drinker"),
        "url_purpose": "Alcohol-free drinks retailer",
        "url_checked_date": "2026-05-10",
        "url_type": "normal",
        "notes": "Useful for workplace-safe or inclusive gifting.",
        "best_for": ["alcohol-free beer", "wine and spirits alternatives"],
        "use_cases": ["non-alcoholic gifts", "inclusive events", "workplace-safe gifting"],
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
        "notes": "Supplier type for Champagne-led suppliers and merchants.",
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


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "supplier"


def apply_central_supplier_entries() -> None:
    """Merge the central supplier data file into the richer planner model."""
    suppliers_by_id = {supplier["id"]: supplier for supplier in SUPPLIERS}
    for entry in SUPPLIER_ENTRIES:
        link_config = get_supplier_link(entry["id"])
        configured_url = link_config.url if link_config else entry.get("url")
        canonical_url = link_config.canonical_base_url if link_config else entry.get("url")
        affiliate_url = link_config.affiliate_url if link_config else entry.get("affiliateUrl")
        configured_active = link_config.active if link_config else entry.get("active", True)
        supplier = suppliers_by_id.get(entry["id"])
        if not supplier:
            supplier = {
                "id": entry["id"],
                "typical_budget_min": 10,
                "typical_budget_max": 250,
                "bulk_orders": True,
                "corporate_gifting": True,
                "personalisation": False,
                "branding": False,
                "uk_delivery": "UK" in entry.get("regions", []),
                "international_delivery": "International" in entry.get("regions", []),
                "event_available": "event wine" in entry.get("useCases", []) or "inclusive events" in entry.get("useCases", []),
                "virtual_event_available": "inclusive events" in entry.get("useCases", []),
                "in_person_event_available": "event wine" in entry.get("useCases", []),
            }
            SUPPLIERS.append(supplier)
            suppliers_by_id[entry["id"]] = supplier

        best_for = [item.strip() for item in str(entry.get("bestFor", "")).split(",") if item.strip()]
        supplier.update(
            {
                "name": entry["name"],
                "category": entry["category"],
                "website_url": canonical_url,
                "enquiry_url": configured_url,
                "affiliate_url": affiliate_url,
                "contact_url": configured_url or entry.get("contactUrl"),
                "contact_email": entry.get("contactEmail"),
                "contact_label": entry.get("contactLabel"),
                "contact_type": entry.get("contactType"),
                "search_suggestion": entry.get("searchSuggestion"),
                "url_purpose": entry.get("urlPurpose"),
                "url_checked_date": entry.get("checkedDate"),
                "url_type": "normal" if entry.get("url") else "search_guidance",
                "notes": entry.get("notes", ""),
                "regions": entry.get("regions", supplier.get("regions", [])),
                "best_for": best_for or supplier.get("best_for", []),
                "use_cases": entry.get("useCases", supplier.get("use_cases", [])),
                "commercial_relationship": "affiliate" if affiliate_url else "none",
                "active": configured_active,
            }
        )


def apply_supplier_link_config() -> None:
    for supplier in SUPPLIERS:
        link_config = get_supplier_link(supplier.get("id", ""))
        if not link_config:
            continue
        supplier.update(
            {
                "website_url": link_config.canonical_base_url,
                "enquiry_url": link_config.url,
                "affiliate_url": link_config.affiliate_url,
                "contact_url": link_config.url or supplier.get("contact_url"),
                "commercial_relationship": "affiliate" if link_config.affiliate_url else supplier.get("commercial_relationship", "none"),
                "active": supplier.get("active", link_config.active) and link_config.active,
                "link_category_tags": list(link_config.category_tags),
            }
        )


def normalise_suppliers() -> None:
    seen: set[str] = set()
    for supplier in SUPPLIERS:
        supplier_id = supplier.get("supplier_id") or supplier.get("id") or slugify(supplier["name"])
        slug = supplier.get("tracking_slug") or slugify(supplier_id)
        original_slug = slug
        counter = 2
        while slug in seen:
            slug = f"{original_slug}-{counter}"
            counter += 1
        seen.add(slug)

        relationship = supplier.get("commercial_relationship", "none")
        label = {
            "none": "Supplier to check",
            "affiliate": "Affiliate link",
            "referral": "Referral relationship",
            "sponsored": "Sponsored placement",
            "supplier_partner": "Supplier partner",
        }.get(relationship, "Supplier to check")
        is_affiliate = bool(supplier.get("affiliate_url") and relationship == "affiliate")
        disclosure = supplier.get("disclosure_note") or (
            "Affiliate or tracked supplier link where available. Confirm pricing, availability, delivery and suitability directly."
            if is_affiliate
            else "Normal supplier reference for planning. No affiliate relationship or endorsement is implied."
        )

        supplier.update(
            {
                "supplier_id": supplier_id,
                "description": supplier.get("description") or supplier.get("notes", ""),
                "tracking_slug": slug,
                "commercial_relationship": relationship,
                "commercial_relationship_label": label,
                "disclosure_note": disclosure,
                "is_affiliate": is_affiliate,
                "disclosure_label": "Affiliate link" if is_affiliate else "Normal supplier link",
                "url_purpose": supplier.get("url_purpose") or "Supplier page",
                "url_checked_date": supplier.get("url_checked_date"),
                "url_type": supplier.get("url_type") or ("affiliate" if is_affiliate else "normal"),
                "active": supplier.get("active", True),
                "url": supplier.get("website_url") or supplier.get("enquiry_url"),
                "urlPurpose": supplier.get("url_purpose") or "Supplier page",
                "checkedDate": supplier.get("url_checked_date") or "2026-05-10",
                "useCases": supplier.get("use_cases") or supplier.get("best_for", []),
                "isAffiliate": is_affiliate,
                "affiliateUrl": supplier.get("affiliate_url"),
                "contactUrl": supplier.get("contact_url"),
                "contactEmail": supplier.get("contact_email"),
                "contactLabel": supplier.get("contact_label"),
                "contactType": supplier.get("contact_type") or ("supplier_page" if supplier.get("contact_url") else "search_suggestion"),
                "searchSuggestion": supplier.get("search_suggestion"),
            }
        )


apply_central_supplier_entries()
apply_supplier_link_config()
normalise_suppliers()


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
    attendee_count: int = Field(gt=0, le=5000)
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


class PremiumPackPreviewRequest(BaseModel):
    pack_type: Literal["gift", "event"]
    planner_input: dict
    planner_output: dict


class CheckoutSessionRequest(BaseModel):
    pack_type: Literal["gift", "event"]
    email: EmailStr | None = None
    auth_user_id: str | None = None
    planner_input: dict | None = None
    planner_output: dict | None = None
    premium_preview: dict | None = None


class PackAccessRequest(BaseModel):
    email: EmailStr


class LeadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    company: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=80)
    interested_in: Literal["gifts", "events", "premium_pack", "supplier_intro", "other"]
    recipient_count: int | None = Field(default=None, gt=0, le=100000)
    budget_per_recipient: float | None = Field(default=None, gt=0, le=100000)
    occasion: str | None = Field(default=None, max_length=240)
    deadline: str | None = Field(default=None, max_length=160)
    message: str | None = Field(default=None, max_length=3000)
    consent_to_contact: bool
    planner_input: dict | None = None
    planner_output: dict | None = None
    source_page: str | None = Field(default=None, max_length=300)

    @field_validator("consent_to_contact")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Please confirm consent so ClientCellar can contact you about this enquiry.")
        return value


def has_generated_plan_payload(req: CheckoutSessionRequest) -> bool:
    """Checkout must upgrade a generated free plan, not start from a blank purchase."""
    return bool(req.planner_input and req.planner_output)


class SupplierApplicationRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=180)
    contact_name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=300)
    supplier_type: Literal[
        "wine_merchant",
        "hamper_supplier",
        "champagne_sparkling_specialist",
        "english_sparkling_producer",
        "corporate_gifting_provider",
        "wine_tasting_host",
        "virtual_tasting_provider",
        "other",
    ]
    regions_covered: str = Field(min_length=1, max_length=500)
    corporate_gifting: bool = False
    wine_tasting_events: bool = False
    virtual_events: bool = False
    bulk_orders: bool = False
    personalisation: bool = False
    typical_budget_min: float | None = Field(default=None, gt=0, le=100000)
    typical_budget_max: float | None = Field(default=None, gt=0, le=100000)
    affiliate_links_available: Literal["yes", "no", "not_sure"] = "not_sure"
    message: str | None = Field(default=None, max_length=3000)
    consent_to_contact: bool

    @field_validator("consent_to_contact")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Please confirm consent so ClientCellar can contact you about this supplier enquiry.")
        return value


def money(value: float) -> str:
    return f"£{value:,.0f}"


def readable(value: str) -> str:
    return value.replace("_", " ")


def supplier_category_label(supplier: dict) -> str:
    return {
        "wine_merchant": "Wine merchants",
        "hamper_company": "Hampers and corporate gifting",
        "corporate_gifting": "Hampers and corporate gifting",
        "wine_tasting": "Event wine and larger orders",
        "virtual_tasting": "Event wine and larger orders",
        "experience_provider": "Event wine and larger orders",
        "english_sparkling": "Wine merchants",
        "champagne_sparkling": "Wine merchants",
        "non_alcoholic": "Non-alcoholic options",
    }.get(supplier.get("category"), readable(supplier.get("category", "supplier route")).title())


def supplier_url(supplier: dict) -> str | None:
    return supplier.get("enquiry_url") or supplier.get("website_url")


def supplier_public_url(supplier_id: str) -> str | None:
    link_config = get_supplier_link(supplier_id)
    return link_config.url if link_config else None


def supplier_destination_url(supplier: dict) -> str | None:
    if supplier.get("is_affiliate") and supplier.get("affiliate_url"):
        return supplier.get("affiliate_url")
    return supplier.get("enquiry_url") or supplier.get("website_url")


def is_real_supplier(supplier: dict) -> bool:
    return bool(supplier_destination_url(supplier))


def supplier_by_id(supplier_id: str) -> dict | None:
    return next((supplier for supplier in SUPPLIERS if supplier["id"] == supplier_id and supplier.get("active", True)), None)


def supplier_by_name(name: str | None) -> dict | None:
    if not name:
        return None
    target = slugify(str(name))
    for supplier in SUPPLIERS:
        values = {
            slugify(str(supplier.get("name", ""))),
            slugify(str(supplier.get("id", ""))),
            slugify(str(supplier.get("supplier_id", ""))),
            slugify(str(supplier.get("tracking_slug", ""))),
        }
        if target in values:
            return supplier
    for supplier in SUPPLIERS:
        supplier_slug = slugify(str(supplier.get("name", "")))
        if supplier_slug and (supplier_slug in target or target in supplier_slug):
            return supplier
    return None


def contact_label_for_type(contact_type: str | None) -> str:
    return {
        "email": "Email supplier",
        "contact_form": "Contact form",
        "corporate_page": "Corporate gifting",
        "supplier_page": "Supplier page",
        "search_suggestion": "Search/contact directly",
    }.get(contact_type or "", "Contact supplier")


def supplier_contact_search_suggestion(row_or_supplier: dict | None, pack_type: str = "gift") -> str:
    label = " ".join(
        str(value)
        for value in [
            (row_or_supplier or {}).get("supplier"),
            (row_or_supplier or {}).get("supplier_type"),
            (row_or_supplier or {}).get("name"),
            (row_or_supplier or {}).get("category"),
        ]
        if value
    ).lower()
    if "local independent wine merchant" in label or "independent merchant" in label:
        return "independent wine merchant near me"
    if "english sparkling" in label:
        return "English sparkling wine producer corporate gifts"
    if "venue" in label or "caterer" in label:
        return "Ask your venue or caterer for wine package and corkage details"
    if "hamper" in label:
        return "corporate hamper supplier UK"
    if "supermarket" in label or "wine retailer" in label:
        return "wine gifts corporate delivery UK"
    if pack_type == "event":
        return "corporate wine tasting supplier UK"
    return "corporate wine gift supplier UK"


def supplier_contact_mailto(email: str, pack_type: str = "gift") -> str:
    subject = "Event wine enquiry" if pack_type == "event" else "Corporate gifting enquiry"
    requirement = "corporate wine event requirement" if pack_type == "event" else "corporate gifting requirement"
    body = (
        "Hello,\n\n"
        f"I am looking for help with a {requirement}.\n\n"
        "Please could you confirm:\n"
        "- suitable product/package options\n"
        "- unit pricing\n"
        "- delivery costs and timings\n"
        "- gift message or personalisation options\n"
        "- VAT invoice availability\n"
        "- substitutions if items are unavailable\n\n"
        "Thank you."
    )
    return f"mailto:{email}?{urllib.parse.urlencode({'subject': subject, 'body': body})}"


def supplier_contact_route(row_or_supplier: dict | None, pack_type: str = "gift") -> dict:
    row_or_supplier = row_or_supplier or {}
    supplier_key = row_or_supplier.get("supplier_id") or row_or_supplier.get("id")
    supplier = supplier_by_id(str(supplier_key)) if supplier_key else None
    supplier = supplier or supplier_by_name(row_or_supplier.get("supplier") or row_or_supplier.get("supplier_type") or row_or_supplier.get("name"))
    source = {**(supplier or {}), **row_or_supplier}
    contact_email = source.get("contact_email") or source.get("contactEmail")
    contact_url = source.get("contact_url") or source.get("contactUrl")
    contact_type = source.get("contact_type") or source.get("contactType")
    if contact_url and not contact_type:
        contact_type = "supplier_page"
    if not contact_url and not contact_email:
        contact_type = "search_suggestion"
    contact_label = source.get("contact_label") or source.get("contactLabel") or contact_label_for_type(contact_type)
    search_suggestion = (
        source.get("search_suggestion")
        or source.get("searchSuggestion")
        or supplier_contact_search_suggestion(source, pack_type)
    )
    mailto_url = supplier_contact_mailto(contact_email, pack_type) if contact_email else None
    return {
        "contact_email": contact_email,
        "contactEmail": contact_email,
        "contact_url": contact_url,
        "contactUrl": contact_url,
        "contact_label": contact_label,
        "contactLabel": contact_label,
        "contact_type": contact_type,
        "contactType": contact_type,
        "search_suggestion": search_suggestion,
        "searchSuggestion": search_suggestion,
        "mailto_url": mailto_url,
        "mailtoUrl": mailto_url,
    }


def enrich_supplier_comparison_rows(rows: list[dict], pack_type: str = "gift") -> list[dict]:
    enriched = []
    for row in rows or []:
        if not isinstance(row, dict):
            row = {"supplier": str(row)}
        merged = {**row, **supplier_contact_route(row, pack_type)}
        merged.update(supplier_advisory_comparison_fields(merged, pack_type))
        enriched.append(merged)
    return enriched


def supplier_advisory_comparison_fields(row: dict, pack_type: str = "gift") -> dict:
    supplier_name = str(row.get("supplier") or row.get("supplier_type") or row.get("name") or "Supplier route")
    label = " ".join([supplier_name, str(row.get("category") or ""), str(row.get("best_for") or "")]).lower()

    if pack_type == "event":
        if "venue" in label or "caterer" in label:
            profile = {
                "best_for": "Events where the venue controls service, corkage or glassware",
                "best_for_tags": ["Venue controlled", "Low admin"],
                "typical_spend": "Indicative: strongest when venue packages are already within the event budget",
                "minimum_order": "Usually tied to venue minimum spend or attendee count; get the service charge in writing",
                "branding_personalisation": "Limited branding, but menu cards or welcome messaging may be possible",
                "turnaround": "Start 3-4 weeks out so corkage, staffing and delivery rules are clear",
                "multi_address_delivery": "Usually not relevant unless tasting packs are shipped before the event",
                "ease_score": "7/10",
                "hidden_watchouts": "Corkage, service charge and house wine quality can make cheap headline prices misleading",
                "recommendation": "Use where operational control matters more than merchant choice.",
            }
        elif "non" in label or "alcohol-free" in label:
            profile = {
                "best_for": "Inclusive workplace events where not every attendee drinks alcohol",
                "best_for_tags": ["Inclusive", "Workplace safe"],
                "typical_spend": "Indicative: often useful around £15-£45 per attendee depending on format",
                "minimum_order": "Ask whether cases, mixed packs or per-attendee kits are available",
                "branding_personalisation": "Usually light personalisation only; packaging quality matters more than branding",
                "turnaround": "Allow 1-2 weeks, longer for mixed packs or Christmas delivery",
                "multi_address_delivery": "Ask whether individual home delivery is supported before choosing a virtual format",
                "ease_score": "6/10",
                "hidden_watchouts": "Some alcohol-free options feel like substitutes rather than a proper adult drinks experience",
                "recommendation": "Keep as a parallel route so the event does not exclude non-drinkers.",
            }
        elif "retailer" in label or "supermarket" in label:
            profile = {
                "best_for": "Simple self-managed events with clear quantities and one delivery point",
                "best_for_tags": ["Budget check", "Simple order"],
                "typical_spend": "Indicative: often strongest around £12-£35 per bottle before service costs",
                "minimum_order": "Check case availability rather than assuming bulk support",
                "branding_personalisation": "Little corporate personalisation; buyer handles presentation and service",
                "turnaround": "Allow 1-2 weeks and keep a substitution plan",
                "multi_address_delivery": "Usually poor fit for many addresses; best for one venue or office delivery",
                "ease_score": "6/10",
                "hidden_watchouts": "Retail substitutions and delivery windows can undermine event control",
                "recommendation": "Use as a benchmark or backup, not the lead route for a polished hosted event.",
            }
        else:
            profile = {
                "best_for": "Hosted tastings or larger event wine requirements where advice and logistics matter",
                "best_for_tags": ["Event advice", "Larger quantities"],
                "typical_spend": "Indicative: usually strongest around £45-£120 per attendee for hosted formats",
                "minimum_order": "Ask for attendee minimums, host fee, delivery terms and cancellation rules",
                "branding_personalisation": "Can support theme, run sheet or branded notes if requested early",
                "turnaround": "Begin supplier contact 3-6 weeks before the event; longer for Christmas or custom packs",
                "multi_address_delivery": "Ask for recipient data format and failed-delivery handling for virtual events",
                "ease_score": "8/10",
                "hidden_watchouts": "Host availability, delivery failures and unclear cancellation terms are the main risks",
                "recommendation": "Use as the lead route when the event needs structure, hosting or delivery support.",
            }
    elif "fortnum" in label:
        profile = {
            "best_for": "Premium client tiers where presentation matters more than tight budget control",
            "best_for_tags": ["VIP", "Premium hamper"],
            "typical_spend": "Indicative: usually strongest around £75-£200+ per recipient",
            "minimum_order": "May work for small counts, but ask how corporate orders and invoices are handled",
            "branding_personalisation": "Presentation is strong; branded inserts or bespoke notes need early confirmation",
            "turnaround": "Allow 2-4 weeks, longer for Christmas peaks or large address lists",
            "multi_address_delivery": "Check whether bulk multi-address upload is practical before using for all recipients",
            "ease_score": "6/10",
            "hidden_watchouts": "Risk: premium packaging can push spend above policy limits once delivery and VAT are added",
            "recommendation": "Use for VIP or senior client tiers, not necessarily the whole list.",
        }
    elif "m&s" in label or "marks" in label or "hamper" in label:
        profile = {
            "best_for": "Staff, mixed-recipient groups and standard clients where food variety is safer than one bottle",
            "best_for_tags": ["Broad appeal", "Hamper fallback"],
            "typical_spend": "Indicative: often useful around £30-£75 per recipient",
            "minimum_order": "Check whether business quantities can be handled smoothly before relying on retail checkout",
            "branding_personalisation": "Usually limited; prioritise gift message, dietary filters and alcohol contents",
            "turnaround": "Allow 1-3 weeks; Christmas cut-offs can move quickly",
            "multi_address_delivery": "Ask whether multiple addresses can be uploaded or whether orders must be placed manually",
            "ease_score": "7/10",
            "hidden_watchouts": "Risk: low-spend options may feel more retail than premium corporate gifting",
            "recommendation": "Use as the safest fallback when recipient preferences are unknown.",
        }
    elif "majestic" in label or "corporate wine" in label or "corporate gifting" in label:
        profile = {
            "best_for": "25-250 recipient campaigns where reliable fulfilment matters more than boutique curation",
            "best_for_tags": ["Standard clients", "Fulfilment"],
            "typical_spend": "Indicative: usually strongest around £45-£120 per recipient",
            "minimum_order": "Ask whether the planned quantity qualifies for corporate support, VAT invoice and order handling",
            "branding_personalisation": "Ask whether branded gift note, message handling and multi-address upload are supported",
            "turnaround": "Begin contact 2-3 weeks before dispatch; longer for Christmas or branded items",
            "multi_address_delivery": "Good route to test, but confirm file format and failed-delivery process before payment",
            "ease_score": "8/10",
            "hidden_watchouts": "Substitutions can change the perceived quality if the exact bottle or case is unavailable",
            "recommendation": "Use for the standard client tier; reserve independent or premium merchants for VIP recipients.",
        }
    elif "laithwaites" in label or "virgin" in label:
        profile = {
            "best_for": "Accessible wine gift cases where range and straightforward delivery are more important than bespoke advice",
            "best_for_tags": ["Wine gifts", "Case gifting"],
            "typical_spend": "Indicative: usually strongest around £35-£90 per recipient",
            "minimum_order": "Ask whether corporate quantities get a clearer account route than consumer checkout",
            "branding_personalisation": "Gift messages may be possible; branded inserts and proofing need confirmation",
            "turnaround": "Allow 1-3 weeks and build in substitution approval time",
            "multi_address_delivery": "Confirm whether address upload, tracking and exception handling are supported",
            "ease_score": "7/10",
            "hidden_watchouts": "Mixed cases can be efficient but may feel less tailored for senior relationships",
            "recommendation": "Use as a practical wine-only comparison against Majestic or a hamper supplier.",
        }
    elif "berry" in label or "wine society" in label or "independent" in label or "merchant" in label:
        profile = {
            "best_for": "VIP clients, senior relationships and advice-led bottle choices where taste matters",
            "best_for_tags": ["VIP", "Advice led"],
            "typical_spend": "Indicative: usually strongest around £60-£200+ per recipient",
            "minimum_order": "Often flexible, but ask how they handle corporate lists, invoices and repeat orders",
            "branding_personalisation": "Presentation and bottle advice can be strong; admin tooling may be lighter",
            "turnaround": "Allow 2-4 weeks if you need tailored recommendations or local delivery planning",
            "multi_address_delivery": "May be limited; check whether they can deliver to many addresses before committing",
            "ease_score": "5/10",
            "hidden_watchouts": "The best advice-led option can become admin-heavy for large recipient lists",
            "recommendation": "Reserve for VIP recipients or tricky briefs where a mainstream route feels too generic.",
        }
    elif "non" in label or "alcohol-free" in label:
        profile = {
            "best_for": "Recipients where alcohol suitability is uncertain or workplace policy is sensitive",
            "best_for_tags": ["Inclusive", "Alcohol-free"],
            "typical_spend": "Indicative: usually strongest around £20-£70 per recipient",
            "minimum_order": "Ask whether corporate gift packaging and invoices are available",
            "branding_personalisation": "Prioritise presentation quality and gift message over heavy branding",
            "turnaround": "Allow 1-2 weeks, longer for Christmas or mixed alternative packs",
            "multi_address_delivery": "Confirm whether individual delivery and tracking are supported",
            "ease_score": "6/10",
            "hidden_watchouts": "Some options may feel like compliance substitutes unless packaging is gift-worthy",
            "recommendation": "Keep as a planned alternative, especially for unknown preferences or internal stakeholders.",
        }
    else:
        profile = {
            "best_for": "Indicative supplier route for comparing fit, admin effort and recipient suitability",
            "best_for_tags": ["Indicative", "To validate"],
            "typical_spend": row.get("budget_fit") or "Indicative: confirm realistic bands directly with suppliers",
            "minimum_order": "Ask for minimum order quantity, VAT invoice route and corporate account requirements",
            "branding_personalisation": "Confirm gift notes, branded inserts, proofing time and packaging options before approval",
            "turnaround": "Begin supplier contact 2-3 weeks before dispatch; longer during Christmas peaks",
            "multi_address_delivery": "Confirm address file format, tracking and failed-delivery handling before sharing data",
            "ease_score": "6/10",
            "hidden_watchouts": "The headline option may look suitable but fail on admin, substitutions or delivery control",
            "recommendation": "Use as a comparison route until written supplier responses show the strongest fit.",
        }

    return {
        "best_for": row.get("advisory_best_for") or row.get("best_for_advisory") or profile["best_for"],
        "best_for_tags": row.get("best_for_tags") or profile["best_for_tags"],
        "typical_spend": row.get("typical_spend") or profile["typical_spend"],
        "minimum_order": row.get("minimum_order") or profile["minimum_order"],
        "branding_personalisation": row.get("branding_personalisation") or profile["branding_personalisation"],
        "turnaround": row.get("turnaround") or profile["turnaround"],
        "multi_address_delivery": row.get("multi_address_delivery") or profile["multi_address_delivery"],
        "ease_score": row.get("ease_score") or profile["ease_score"],
        "hidden_watchouts": row.get("hidden_watchouts") or profile["hidden_watchouts"],
        "recommendation": row.get("recommendation") or profile["recommendation"],
    }


def premium_executive_recommendation(pack_type: str = "gift", unit_budget: float = 0, count: int = 0) -> list[dict]:
    if pack_type == "event":
        return [
            {"label": "Recommended route", "value": "Use a dedicated event wine supplier where hosting, delivery or attendee packs matter; use venue packages only where corkage or service rules make outside supply impractical."},
            {"label": "Budget sweet spot", "value": "Indicative: £45-£120 per attendee for a credible hosted experience before venue/service variables."},
            {"label": "Recipient strategy", "value": "Separate hosted attendees, alcohol-free attendees and any VIP/client-facing stakeholders before asking for quotes."},
            {"label": "Timing", "value": "Begin supplier contact 3-6 weeks before the event; longer for Christmas, virtual packs or branded materials."},
            {"label": "Main risk", "value": "Choosing a format before confirming venue rules, delivery responsibilities, alcohol-free options and cancellation terms."},
        ]
    budget_note = (
        f"Indicative: the entered budget of {money(unit_budget)} is workable for mainstream gifting; ask for a stretch option if premium feel matters."
        if unit_budget and unit_budget < 65
        else "Indicative: £65-£95 per recipient is often the strongest range for a credible premium feel without overpaying."
    )
    return [
        {"label": "Recommended route", "value": "Use a mainstream corporate supplier for standard recipients and a specialist or independent merchant for VIP clients."},
        {"label": "Budget sweet spot", "value": budget_note},
        {"label": "Recipient strategy", "value": "Split recipients into VIP, standard client and internal stakeholder tiers before sending enquiries."},
        {"label": "Timing", "value": "Begin supplier contact 2-3 weeks before required dispatch; longer for Christmas or branded items."},
        {"label": "Main risk", "value": "Choosing a supplier before confirming multi-address delivery, gift notes, VAT invoicing and substitutions."},
    ]


def premium_what_we_would_do(pack_type: str = "gift") -> list[str]:
    if pack_type == "event":
        return [
            "Separate attendee groups into hosted guests, alcohol-free attendees and VIP/client-facing stakeholders.",
            "Use a dedicated event supplier if hosting, pacing or tasting packs matter.",
            "Use the venue or caterer route where corkage, service or licensing makes outside supply risky.",
            "Keep a supermarket or retailer route only as a benchmark or operational fallback.",
            "Confirm delivery ownership, cancellation rules, substitutions and alcohol-free handling before payment.",
        ]
    return [
        "Split the recipient list into VIP, standard client and internal stakeholder tiers.",
        "Use wine or premium drinks for known wine-friendly recipients.",
        "Use hampers only where recipient preference is unknown.",
        "Reserve boutique suppliers for senior/VIP relationships.",
        "Confirm delivery file format, cut-off dates, substitutions and invoice handling before payment.",
    ]


def premium_recommended_shortlist(rows: list[dict], pack_type: str = "gift") -> list[dict]:
    if not rows:
        return []

    def find_row(*terms: str) -> dict | None:
        for row in rows:
            label = " ".join([str(row.get("supplier") or ""), str(row.get("best_for") or ""), str(row.get("supplier_type") or "")]).lower()
            if any(term in label for term in terms):
                return row
        return None

    if pack_type == "event":
        overall = find_row("event", "tasting", "majestic") or rows[0]
        fallback = find_row("venue", "caterer", "retailer", "supermarket") or (rows[1] if len(rows) > 1 else rows[0])
        vip = find_row("premium", "independent", "merchant", "specialist") or overall
        return [
            {"rank": "Best overall", "supplier": overall.get("supplier") or overall.get("supplier_type"), "reason": "Strongest route when the brief needs hosting, delivery control or advice rather than only bottles."},
            {"rank": "Best fallback", "supplier": fallback.get("supplier") or fallback.get("supplier_type"), "reason": "Useful if venue rules, budget or timing make the lead route harder to execute."},
            {"rank": "Best VIP option", "supplier": vip.get("supplier") or vip.get("supplier_type"), "reason": "Best reserved for senior attendees or client-facing moments where presentation matters most."},
        ]
    overall = find_row("majestic", "corporate", "laithwaites", "virgin") or rows[0]
    fallback = find_row("hamper", "m&s", "fortnum", "john lewis") or (rows[1] if len(rows) > 1 else rows[0])
    vip = find_row("fortnum", "berry", "wine society", "independent", "merchant") or overall
    return [
        {"rank": "Best overall", "supplier": overall.get("supplier") or overall.get("supplier_type"), "reason": "Most likely to balance recipient count, admin effort, VAT invoice needs and delivery control."},
        {"rank": "Best fallback", "supplier": fallback.get("supplier") or fallback.get("supplier_type"), "reason": "Use when preferences are mixed or a food-and-drink gift feels safer than a single bottle."},
        {"rank": "Best VIP option", "supplier": vip.get("supplier") or vip.get("supplier_type"), "reason": "Reserve for senior relationships where advice, presentation or perceived quality matters more than speed."},
    ]


def normalise_supplier_label(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def comparison_supplier_name(row: dict) -> str:
    return str(row.get("supplier") or row.get("supplier_type") or row.get("name") or "Supplier route")


def find_comparison_row(rows: list[dict], supplier_name: str | None) -> dict:
    target = normalise_supplier_label(supplier_name)
    if not target:
        return {}
    for row in rows:
        label = normalise_supplier_label(comparison_supplier_name(row))
        if label == target or target in label or label in target:
            return row
    return {}


def premium_recommendation_summary(rows: list[dict], shortlist: list[dict], pack_type: str = "gift") -> list[dict]:
    if not rows:
        return []
    shortlist = shortlist or premium_recommended_shortlist(rows, pack_type)
    summary_by_supplier: dict[str, dict] = {}
    for item in shortlist[:3]:
        supplier_name = item.get("supplier") or "Supplier route"
        row = find_comparison_row(rows, supplier_name)
        row = row or next((candidate for candidate in rows if normalise_supplier_label(comparison_supplier_name(candidate)) == normalise_supplier_label(supplier_name)), {})
        display_name = comparison_supplier_name(row) if row else str(supplier_name)
        key = normalise_supplier_label(display_name)
        if key not in summary_by_supplier:
            contact = supplier_contact_route(row or {"supplier": display_name}, pack_type)
            summary_by_supplier[key] = {
                "supplier": display_name,
                "roles": [],
                "reasons": [],
                "contact_url": contact.get("contact_url"),
                "contactUrl": contact.get("contact_url"),
                "contact_label": contact.get("contact_label") or f"View {display_name}",
                "contactLabel": contact.get("contact_label") or f"View {display_name}",
                "mailto_url": contact.get("mailto_url"),
                "mailtoUrl": contact.get("mailto_url"),
                "search_suggestion": contact.get("search_suggestion"),
                "searchSuggestion": contact.get("search_suggestion"),
            }
        summary = summary_by_supplier[key]
        role = item.get("rank") or "Recommended"
        if role not in summary["roles"]:
            summary["roles"].append(role)
        reason = item.get("reason")
        if reason and reason not in summary["reasons"]:
            summary["reasons"].append(reason)

    merged = []
    for summary in summary_by_supplier.values():
        roles = summary.get("roles") or ["Recommended"]
        reasons = summary.get("reasons") or ["Strongest fit based on supplier route, admin effort and recipient suitability."]
        if len(roles) > 1:
            role_text = " and ".join(roles)
            summary["merged_role_label"] = role_text
            summary["reason"] = f"{summary['supplier']} covers {role_text.lower()} for this brief. {reasons[0]}"
        else:
            summary["merged_role_label"] = roles[0]
            summary["reason"] = reasons[0]
        merged.append(summary)
    return merged


def premium_recommendation_rationale(summary: list[dict], rows: list[dict], pack_type: str = "gift") -> list[str]:
    if not summary:
        return []
    if pack_type == "event":
        return [
            "The lead route is chosen for delivery control, hosting support and fewer operational surprises.",
            "Fallback routes stay visible in case venue rules, timing or attendee suitability change the buying path.",
            "The VIP route is separated so premium spend is reserved for moments where it changes the outcome.",
        ]
    lead = summary[0].get("supplier", "the lead supplier")
    return [
        f"{lead} is the clearest starting point because it best balances supplier practicality, budget fit and recipient suitability.",
        "Fallback and VIP routes are separated so mixed preferences and senior relationships are handled deliberately.",
        "The comparison still keeps alternatives available, but the first action is clear rather than turning the pack into a directory.",
    ]


def add_premium_advisory_sections(preview: dict, pack_type: str = "gift", unit_budget: float = 0, count: int = 0) -> dict:
    rows = preview.get("supplier_comparison") or []
    preview["supplier_comparison"] = enrich_supplier_comparison_rows(rows, pack_type)
    preview.setdefault("supplier_executive_recommendation", premium_executive_recommendation(pack_type, unit_budget, count))
    preview.setdefault("what_we_would_do", premium_what_we_would_do(pack_type))
    preview.setdefault("recommended_shortlist", premium_recommended_shortlist(preview["supplier_comparison"], pack_type))
    preview["recommendation_summary"] = premium_recommendation_summary(
        preview["supplier_comparison"],
        preview.get("recommended_shortlist") or [],
        pack_type,
    )
    preview["recommendation_rationale"] = premium_recommendation_rationale(
        preview.get("recommendation_summary") or [],
        preview["supplier_comparison"],
        pack_type,
    )
    return preview


def supplier_directory_card(
    name: str,
    best_for: str,
    use_case: str,
    budget_fit: str,
    notes: str,
    supplier: dict | None = None,
) -> dict:
    return {
        "name": supplier["name"] if supplier else name,
        "best_for": best_for,
        "use_case": use_case,
        "budget_fit": budget_fit,
        "notes": notes,
        "prepare_url": "/event-planner" if "tasting" in use_case.lower() or "event" in use_case.lower() else "/gift-planner",
        "visit_url": f"/out/supplier/{supplier['tracking_slug']}?source_page=/suppliers" if supplier and is_real_supplier(supplier) else None,
        "relationship_label": supplier["commercial_relationship_label"] if supplier else "Supplier type",
        "is_affiliate": supplier.get("is_affiliate", False) if supplier else False,
        "link_label": supplier_link_label(supplier) if supplier else "View supplier guidance",
    }


def supplier_link_label(supplier: dict) -> str:
    purpose = (supplier.get("url_purpose") or "").lower()
    if "corporate" in purpose:
        return "Check corporate gifting options"
    if "food and drink" in purpose:
        return "View food and drink gifts"
    if "fine wines" in purpose:
        return "View fine wines"
    if "hamper" in purpose:
        return "View hamper options"
    if "wine gifts" in purpose or "gifts" in purpose:
        return "View wine gifts"
    if "event" in purpose:
        return "Check event wine support"
    return "Visit supplier"


def supplier_button_url(supplier: dict, source_page: str) -> str | None:
    if not supplier or not is_real_supplier(supplier):
        return None
    return f"/out/supplier/{supplier['tracking_slug']}?source_page={urllib.parse.quote(source_page, safe='/')}"


def supplier_route_example(supplier_id: str, source_page: str) -> dict:
    supplier = supplier_by_id(supplier_id)
    if not supplier:
        return {}
    return {
        "id": supplier["id"],
        "name": supplier["name"],
        "category": supplier_category_label(supplier),
        "best_for": ", ".join(supplier.get("best_for", [])),
        "notes": supplier.get("notes", ""),
        "url": supplier_url(supplier),
        "tracked_url": supplier_button_url(supplier, source_page),
        "is_affiliate": supplier.get("is_affiliate", False),
        "link_label": supplier_link_label(supplier),
        "url_purpose": supplier.get("url_purpose"),
        "url_checked_date": supplier.get("url_checked_date"),
        "disclosure_note": supplier.get("disclosure_note"),
    }


def supplier_route_card(route: str, why: str, supplier_ids: list[str], ask: str, source_page: str) -> dict:
    examples = [supplier_route_example(supplier_id, source_page) for supplier_id in supplier_ids]
    examples = [example for example in examples if example]
    primary = next((example for example in examples if example.get("tracked_url")), None)
    return {
        "route": route,
        "route_name": route,
        "why": why,
        "why_it_fits": why,
        "examples": [example["name"] for example in examples],
        "example_suppliers": examples,
        "ask": ask,
        "what_to_ask": ask,
        "tracked_url": primary.get("tracked_url") if primary else None,
        "link_label": primary.get("link_label") if primary else "Visit supplier",
        "is_affiliate": primary.get("is_affiliate", False) if primary else False,
        "search_suggestion": f"{route.lower()} UK",
    }


def gift_supplier_route_cards(req: GiftPlanRequest) -> list[dict]:
    preference_text = f"{req.known_preferences or ''} {req.avoid or ''}".lower()
    routes: list[dict] = []
    if req.budget_per_recipient >= 75 or req.tone in {"premium", "impressive"} or req.gift_style == "sparkling":
        routes.append(supplier_route_card(
            "Premium wine merchant",
            "Better for formal client gifts, Champagne, fine wine or presentation-led gifting.",
            ["berry-bros-rudd", "fortnum-mason", "wine-society"],
            "Can they handle gift messaging, delivery timing, VAT invoice and multiple addresses?",
            "/gift-planner",
        ))
    routes.append(supplier_route_card(
        "Corporate wine gifting supplier",
        "Good for case gifting, repeated orders and practical delivery.",
        ["majestic", "laithwaites", "virgin-wines"],
        "Can they support bulk orders, gift notes, delivery tracking and substitutions?",
        "/gift-planner",
    ))
    if req.gift_style in {"wine_hamper", "not_sure"} or req.recipient_type in {"employees", "mixed"}:
        routes.append(supplier_route_card(
            "Hamper supplier",
            "Food-and-drink hampers can suit mixed preferences better than single bottles.",
            ["marks-spencer-corporate", "john-lewis-hampers", "fortnum-mason"],
            "Are alcohol-free or dietary options available?",
            "/gift-planner",
        ))
    if req.recipient_type in {"employees", "mixed"} or "alcohol" in preference_text or "non-alcohol" in preference_text:
        routes.append(supplier_route_card(
            "Non-alcoholic gifting supplier",
            "Safer for mixed workplace groups or uncertain recipient preferences.",
            ["noughty-thomson-scott", "dry-drinker"],
            "Are the products suitable for gifting and available for delivery by the required date?",
            "/gift-planner",
        ))
    routes.append(supplier_route_card(
        "Local independent wine merchant",
        "Good for smaller lists, VIP clients or more personal recommendations.",
        ["local-independent-wine-merchant"],
        "Check delivery coverage, invoice support and gift wrapping.",
        "/gift-planner",
    ))
    routes.append(supplier_route_card(
        "Supermarket / mainstream retailer",
        "Good for lower-budget or faster-turnaround gifting.",
        ["waitrose-cellar", "laithwaites", "virgin-wines"],
        "Check stock availability, delivery slots and substitutions.",
        "/gift-planner",
    ))
    unique = []
    seen = set()
    for route in routes:
        if route["route"] not in seen:
            unique.append(route)
            seen.add(route["route"])
    return unique[:6]


def event_supplier_route_cards(req: EventPlanRequest) -> list[dict]:
    routes = [
        supplier_route_card(
            "Event wine supplier / wine merchant",
            "Best for larger quantities, delivery planning and advice.",
            ["majestic", "local-independent-wine-merchant"],
            "Ask about delivery windows, substitutions, chilling, glassware, returns and corkage.",
            "/event-planner",
        ),
        {
            "route": "Venue/caterer wine package",
            "route_name": "Venue/caterer wine package",
            "why": "Best where the venue controls corkage or service.",
            "why_it_fits": "Best where the venue controls corkage or service.",
            "examples": ["Your venue", "Your caterer"],
            "example_suppliers": [],
            "ask": "Ask about corkage, minimum spend, house wine quality and service charges.",
            "what_to_ask": "Ask about corkage, minimum spend, house wine quality and service charges.",
            "tracked_url": None,
            "link_label": "Search locally",
            "is_affiliate": False,
            "search_suggestion": "venue wine package or caterer wine package near your venue",
        },
        supplier_route_card(
            "Supermarket/wine retailer",
            "Best for simple self-managed events with clear quantities.",
            ["waitrose-cellar", "majestic", "marks-spencer-corporate"],
            "Ask about delivery timing, substitutions and case availability.",
            "/event-planner",
        ),
        supplier_route_card(
            "Non-alcoholic drinks supplier",
            "Best for inclusive workplace events.",
            ["dry-drinker", "noughty-thomson-scott"],
            "Ask about alcohol-free sparkling, beers and adult soft drink alternatives.",
            "/event-planner",
        ),
    ]
    if req.format in {"virtual", "hybrid"}:
        routes.append(supplier_route_card(
            "Virtual tasting pack route",
            "Useful when attendees need packs delivered before a remote or hybrid session.",
            ["virgin-wines", "laithwaites", "dry-drinker"],
            "Ask about attendee address handling, delivery lead times, late packs and alcohol-free alternatives.",
            "/event-planner",
        ))
    return routes[:5]


def supplier_directory_sections() -> list[dict]:
    section_ids = {
        "Wine merchants": ["majestic", "laithwaites", "wine-society", "berry-bros-rudd", "virgin-wines"],
        "Hampers and corporate gifting": ["fortnum-mason", "marks-spencer-corporate", "waitrose-cellar", "john-lewis-hampers"],
        "Event wine and larger orders": ["majestic", "local-independent-wine-merchant"],
        "Non-alcoholic options": ["noughty-thomson-scott", "dry-drinker"],
    }
    sections = []
    for title, ids in section_ids.items():
        cards = []
        for supplier_id in ids:
            supplier = supplier_by_id(supplier_id)
            if not supplier:
                continue
            cards.append({
                "name": supplier["name"],
                "category": supplier_category_label(supplier),
                "best_for": ", ".join(supplier.get("best_for", [])),
                "notes": supplier.get("notes", ""),
                "what_to_check": "Check delivery dates, gift messages, alcohol contents, dietary options, substitutions and VAT invoices.",
                "visit_url": supplier_button_url(supplier, "/suppliers"),
                "relationship_label": supplier["commercial_relationship_label"],
                "is_affiliate": supplier.get("is_affiliate", False),
                "link_label": supplier_link_label(supplier),
                "url_purpose": supplier.get("url_purpose"),
                "search_guidance": "independent wine merchant near your town or city" if supplier["id"] == "local-independent-wine-merchant" else "corporate hamper supplier UK",
            })
        sections.append({"title": title, "cards": cards})
    return sections


def supplier_by_tracking_slug(tracking_slug: str) -> dict | None:
    return next((supplier for supplier in SUPPLIERS if supplier["tracking_slug"] == tracking_slug and supplier.get("active", True)), None)


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
                "supplier_id": supplier["id"],
                "name": supplier["name"],
                "category": readable(supplier["category"]),
                "why": f"{why_prefix} {supplier['notes']}",
                "budget_fit": f"Typical planning range {money(supplier['typical_budget_min'])}-{money(supplier['typical_budget_max'])}. Confirm current pricing directly.",
                "url": supplier_url(supplier),
                "tracked_url": f"/out/supplier/{supplier['tracking_slug']}" if is_real_supplier(supplier) else None,
                "affiliate_url": supplier["affiliate_url"],
                "is_affiliate": supplier.get("is_affiliate", False),
                "relationship_label": supplier["commercial_relationship_label"],
                "disclosure_note": supplier["disclosure_note"],
                "url_purpose": supplier.get("url_purpose"),
                "url_checked_date": supplier.get("url_checked_date"),
                "url_type": supplier.get("url_type"),
                "link_label": supplier_link_label(supplier),
                "contact_url": supplier.get("contact_url"),
                "contactUrl": supplier.get("contact_url"),
                "contact_email": supplier.get("contact_email"),
                "contactEmail": supplier.get("contact_email"),
                "contact_label": supplier.get("contact_label") or contact_label_for_type(supplier.get("contact_type")),
                "contactLabel": supplier.get("contact_label") or contact_label_for_type(supplier.get("contact_type")),
                "contact_type": supplier.get("contact_type"),
                "contactType": supplier.get("contact_type"),
                "search_suggestion": supplier.get("search_suggestion")
                or (
                    "independent wine merchant near your town or city"
                    if supplier["id"] in {"local-independent-wine-merchant", "independent-merchant"}
                    else f"{readable(supplier['category'])} UK"
                ),
                "searchSuggestion": supplier.get("search_suggestion")
                or (
                    "independent wine merchant near your town or city"
                    if supplier["id"] in {"local-independent-wine-merchant", "independent-merchant"}
                    else f"{readable(supplier['category'])} UK"
                ),
            }
        )
    return shortlist


def supplier_category_for_gift(req: GiftPlanRequest) -> str:
    if req.gift_style in {"hamper", "mixed_case"}:
        return "Corporate hamper supplier" if req.gift_style == "hamper" else "Corporate wine gift supplier"
    if req.gift_style in {"champagne", "sparkling"} or req.budget_per_recipient >= 75:
        return "Champagne or premium wine specialist"
    if req.branding_needed or req.recipient_count >= 50:
        return "Corporate wine gift supplier"
    return "Premium wine merchant"


def supplier_category_for_event(req: EventPlanRequest) -> str:
    if req.format == "virtual":
        return "Virtual tasting host"
    if req.format == "in_person":
        return "Wine tasting event provider"
    if req.format == "hybrid":
        return "Hybrid tasting event supplier"
    return "Wine tasting event provider"


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
    active_suppliers = [supplier for supplier in SUPPLIERS if supplier.get("active", True)]
    ranked = sorted(active_suppliers, key=lambda supplier: rank_gift_supplier(supplier, req), reverse=True)
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

    supplier_category = supplier_category_for_gift(req)
    supplier_routes = [
        supplier_category,
        "Independent wine merchant",
        "Corporate gifting supplier" if req.recipient_count >= 20 or req.branding_needed else "Wine merchant or retailer",
        "Hamper supplier" if req.gift_style in {"wine_hamper", "not_sure"} else "Supermarket or wine retailer",
    ]
    if req.gift_style == "sparkling" or req.budget_per_recipient >= 75:
        supplier_routes.append("Champagne/sparkling wine specialist")
    preference_text = f"{req.known_preferences or ''} {req.avoid or ''}".lower()
    if req.recipient_type in {"employees", "mixed"} or "alcohol" in preference_text or "non-alcohol" in preference_text:
        supplier_routes.append("Non-alcoholic gifting supplier")
    supplier_routes = list(dict.fromkeys(supplier_routes))
    supplier_questions = [
        "Can you deliver to one address or multiple addresses?",
        "Can you include gift messages?",
        "Can you provide VAT invoices?",
        "What happens if a product is out of stock?",
        "What is the cut-off date for delivery?",
        "Are non-alcoholic or dietary alternatives available?",
        "Do you support bulk or corporate orders?",
    ]
    if req.branding_needed:
        supplier_questions.append("What artwork format, proofing timeline and branding minimums apply?")
    if req.international_needed:
        supplier_questions.append("Which countries can you deliver alcohol to, and what customs or age-verification rules apply?")
    recipient_occasion_fit = [
        f"{readable(req.recipient_type).title()} gifts should be broad-appeal, policy-aware and easy to fulfil at this volume.",
        f"For {req.occasion}, prioritise presentation, delivery certainty and an inclusive route over niche wine choices.",
    ]
    risks_and_checks = avoid + [
        "Confirm live stock, pricing, VAT, delivery coverage and cut-off dates directly with suppliers.",
        "Check company gifting policy, bribery limits, alcohol suitability and recipient preferences before ordering.",
        "Keep a written record of quote assumptions, substitutions, delivery terms and approval notes.",
    ]
    budget_guidance = [
        f"Planning budget: {money(req.budget_per_recipient)} per recipient, around {money(total)} total before supplier-confirmed extras.",
        "This should cover the gift item or pack direction, but VAT, delivery, fulfilment, gift notes, branding and substitutions need confirming directly.",
        "Ask suppliers about minimum order quantities, recipient data format and delivery cut-offs before seeking internal approval.",
    ]
    internal_approval_summary = (
        f"Approval requested to approach {supplier_category.lower()} options for {req.recipient_count} "
        f"{readable(req.recipient_type)} gifts for {req.occasion}. Planning budget is "
        f"{money(req.budget_per_recipient)} per recipient, subject to supplier quotes, VAT, delivery, "
        "lead times, substitution policy, alcohol suitability and company gifting rules."
    )

    next_steps = [
        "Confirm budget owner, recipient count and any alcohol-free requirements.",
        "Shortlist two or three suppliers in the recommended category.",
        "Ask about VAT, delivery costs, minimum order quantities and recipient data format.",
        "Confirm lead times, delivery cut-offs and substitution policy in writing.",
        "Prepare the recipient CSV and gift message before approving the order.",
        "Keep procurement, tax and HR approval notes with the supplier quote.",
    ]
    if req.branding_needed:
        next_steps.insert(1, "Confirm branding artwork specs, proofing time and minimum order quantity.")

    plan = {
        "headline": f"{PRODUCT_NAME} gift plan: {label} {readable(req.recipient_type)} gifting",
        "summary": f"Plan {req.recipient_count} {readable(req.recipient_type)} gifts for {req.occasion} at around {money(req.budget_per_recipient)} each.",
        "estimated_total_budget": f"{money(total)} before confirmed delivery, VAT, packaging or fulfilment extras.",
        "recommended_direction": strategy,
        "recipient_occasion_fit": recipient_occasion_fit,
        "suggested_gift_direction": strategy,
        "budget_guidance": budget_guidance,
        "supplier_category": supplier_category,
        "supplier_routes_to_check": supplier_routes,
        "supplier_route_cards": gift_supplier_route_cards(req),
        "recommended_strategy": strategy,
        "recommended_gift_types": gift_types(req),
        "supplier_shortlist": shortlist,
        "suppliers": shortlist,
        "supplier_recommendations": shortlist,
        "suggested_suppliers": shortlist,
        "questions_to_ask_suppliers": supplier_questions,
        "supplier_questions": supplier_questions,
        "risks_and_checks": risks_and_checks,
        "supplier_links_note": "Supplier links are not required to use this plan. You can use the supplier route guidance to contact retailers or merchants directly.",
        "what_to_avoid": avoid,
        "message_templates": templates_out,
        "supplier_enquiry_email": {"subject": subject, "body": body},
        "internal_approval_summary": internal_approval_summary,
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
    active_suppliers = [supplier for supplier in SUPPLIERS if supplier.get("active", True)]
    ranked = sorted(active_suppliers, key=lambda supplier: rank_event_supplier(supplier, req), reverse=True)
    shortlist = build_supplier_shortlist(
        [supplier for supplier in ranked if rank_event_supplier(supplier, req) >= 0],
        "Relevant for event planning.",
        req.budget_per_person,
    )
    if not shortlist:
        shortlist = build_supplier_shortlist(
            [supplier for supplier in active_suppliers if supplier["event_available"]],
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
    supplier_category = supplier_category_for_event(req)
    bottles_estimate = max(1, math.ceil(req.attendee_count * 0.45))
    serving_assumptions = [
        "Use this as an early planning estimate, not a confirmed order quantity.",
        "A hosted tasting often works from roughly two to three modest pours per attendee, adjusted by format, food and duration.",
        "Confirm final quantities with the venue, caterer or event wine supplier before booking.",
    ]
    wine_quantity_estimate = [
        f"Initial bottle estimate: around {bottles_estimate} standard 75cl bottles for {req.attendee_count} attendees, before supplier or venue adjustment.",
        "Virtual tasting packs may be priced per attendee rather than by bottle count.",
        "For in-person events, confirm glassware, service pace, corkage, venue restrictions and alcohol-free alternatives.",
    ]
    if req.food_pairing_needed:
        wine_mix = "A structured three-wine mix with food pairing notes and alcohol-free alternatives."
    elif req.event_type == "client_entertainment" or req.tone == "client_safe":
        wine_mix = "A polished, low-risk mix such as sparkling arrival, approachable white and approachable red, with modest pours."
    elif req.budget_per_person < 25:
        wine_mix = "Two accessible wines or one wine plus an alcohol-free alternative, keeping delivery and hosting cost under control."
    else:
        wine_mix = "A balanced tasting mix across sparkling, white and red or a themed three-wine flight."
    supplier_routes = [
        supplier_category,
        "Event wine supplier",
        "Wine merchant events team",
        "Corporate gifting supplier" if req.format in {"virtual", "hybrid"} else "Local wine merchant",
    ]
    if req.food_pairing_needed:
        supplier_routes.append("Venue or caterer-supported wine supplier")
    if req.format in {"virtual", "hybrid"}:
        supplier_routes.append("Virtual tasting pack provider")
    supplier_routes = list(dict.fromkeys(supplier_routes))
    supplier_questions = [
        "Can you supply the required quantities by the event date?",
        "Do you offer sale-or-return?",
        "Can you deliver to the venue?",
        "Can you advise on red/white/sparkling mix?",
        "Are glassware, chilling or service included?",
        "Does the venue charge corkage?",
        "What substitutions may be made?",
    ]
    risks_and_checks = avoid + [
        "Quantities are planning estimates; confirm final numbers with the venue, caterer or supplier.",
        "Confirm stock, pricing, glassware, delivery, licensing, corkage, food pairing and venue rules before booking.",
        "Keep responsible drinking expectations, finish time and transport considerations clear in the invite.",
    ]
    budget_guidance = [
        f"Planning budget: {money(req.budget_per_person)} per attendee, around {money(total)} total before supplier-confirmed extras.",
        "This should cover the broad event format, but VAT, host fee, delivery, venue, glassware, food, corkage and minimum spend need confirming directly.",
        "Ask suppliers about lead times, cancellation terms, alcohol-free options, delivery logistics and substitution policy before committing.",
    ]
    internal_approval_summary = (
        f"Approval requested to approach {supplier_category.lower()} options for a {readable(req.event_type)} "
        f"for around {req.attendee_count} attendees. Planning budget is {money(req.budget_per_person)} "
        "per attendee, subject to supplier quotes, VAT, delivery or venue requirements, host availability, "
        "alcohol-free options and cancellation terms."
    )

    plan = {
        "headline": f"{PRODUCT_NAME} event plan: {label} {readable(req.event_type)}",
        "summary": f"Plan for {req.attendee_count} attendees at around {money(req.budget_per_person)} per person.",
        "estimated_total_budget": f"{money(total)} before confirmed VAT, delivery, venue, service or food costs.",
        "recommended_direction": format_copy,
        "event_summary": f"{readable(req.event_type).title()} for {req.attendee_count} attendees, planned at around {money(req.budget_per_person)} per person.",
        "guest_count_and_serving_assumptions": serving_assumptions,
        "serving_assumptions": serving_assumptions,
        "wine_quantity_estimate": wine_quantity_estimate,
        "recommended_wine_mix": wine_mix,
        "budget_guidance": budget_guidance,
        "supplier_category": supplier_category,
        "supplier_routes_to_check": supplier_routes,
        "supplier_route_cards": event_supplier_route_cards(req),
        "recommended_format": format_copy,
        "event_structure": event_structure(req),
        "supplier_shortlist": shortlist,
        "suppliers": shortlist,
        "supplier_recommendations": shortlist,
        "suggested_suppliers": shortlist,
        "questions_to_ask_event_wine_suppliers": supplier_questions,
        "supplier_questions": supplier_questions,
        "risks_and_checks": risks_and_checks,
        "supplier_links_note": "Supplier links are not required to use this plan. You can use the supplier route guidance to contact retailers, merchants or event suppliers directly.",
        "what_to_avoid": avoid,
        "supplier_enquiry_email": {"subject": subject, "body": body},
        "internal_approval_summary": internal_approval_summary,
        "internal_invite_copy": invite,
        "next_steps": [
            "Confirm budget owner, date options, attendee count and any dietary or alcohol-free requirements.",
            "Shortlist two or three suppliers in the recommended category.",
            "Ask shortlisted suppliers for current pricing, VAT, availability, delivery and licensing details.",
            "Confirm lead times, cancellation terms and substitution policy in writing.",
            "Choose the format that is easiest for attendees and safest for the business context.",
            "Share joining instructions, start time, finish time and responsible drinking expectations.",
        ],
        "disclaimer": DISCLAIMER,
    }
    return maybe_improve_plan(plan, "event")


def make_premium_pack_preview(req: PremiumPackPreviewRequest) -> dict:
    output = req.planner_output
    planner_input = req.planner_input
    is_gift = req.pack_type == "gift"
    count = int((planner_input.get("recipient_count") if is_gift else planner_input.get("attendee_count")) or 0)
    unit_budget = float((planner_input.get("budget_per_recipient") if is_gift else planner_input.get("budget_per_person")) or 0)
    planned_spend = count * unit_budget
    contingency = planned_spend * 0.1
    supplier_shortlist = output.get("supplier_shortlist", [])
    deadline = planner_input.get("delivery_deadline") or planner_input.get("date") or "to be confirmed"

    def gift_route() -> str:
        style = planner_input.get("gift_style", "not_sure")
        return {
            "wine_hamper": "Classic wine hamper",
            "sparkling": "English sparkling or Champagne-style gift",
            "mixed_case": "Mixed red/white gift",
            "wine": "Classic wine gift",
        }.get(style, "Low-risk wine hamper, sparkling or mixed red/white gift")

    def supplier_matrix() -> list[dict]:
        rows = []
        for supplier in supplier_shortlist[:5]:
            supplier_type = supplier.get("name", "Supplier type")
            budget_fit = supplier.get("budget_fit", "Confirm current pricing directly.")
            row = {
                "supplier": supplier_type,
                "supplier_type": supplier_type,
                "product_package": supplier.get("category", "Indicative package route"),
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask whether VAT invoice, branded gift note and multi-address upload are supported before committing.",
                "lead_time": "Begin supplier contact 2-3 weeks before required dispatch; longer for Christmas or branded items.",
                "pros": supplier.get("why", "Relevant to the current brief."),
                "risks": "Confirm live pricing, availability, delivery, VAT, minimum orders and substitutions.",
                "decision": "Use only if the written response proves admin, delivery and substitution handling are strong enough.",
                "best_for": supplier.get("category", "supplier route"),
                "budget_fit": budget_fit,
                "strengths": supplier.get("why", "Relevant to the current brief."),
                "watchouts": "Confirm live pricing, availability, delivery, VAT, minimum orders and substitutions.",
                "questions_to_ask": "Can you meet the count, deadline, delivery coverage and data requirements for this brief?",
            }
            row.update(supplier_contact_route(supplier, req.pack_type))
            rows.append(row)
        fallback_rows = [
            {
                "supplier": "Supplier type to confirm",
                "supplier_type": "Supplier type to confirm",
                "product_package": "Indicative package route",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask whether gift notes, branding and proofing can be handled inside the deadline.",
                "lead_time": "Begin supplier contact 2-3 weeks before dispatch; longer in seasonal peaks.",
                "pros": "Keeps supplier conversations structured.",
                "risks": "No live pricing or availability is included.",
                "decision": "Use only after the supplier confirms admin, delivery and substitution handling in writing.",
                "best_for": "Initial market comparison",
                "budget_fit": "Confirm directly with suppliers.",
                "strengths": "Keeps supplier conversations structured.",
                "watchouts": "No live pricing or availability is included.",
                "questions_to_ask": "Can you provide a written quote with inclusions, exclusions and lead times?",
            }
        ]
        return rows or enrich_supplier_comparison_rows(fallback_rows, req.pack_type)

    supplier_questions = [
        "Can you handle this recipient or attendee count?",
        "What exactly is included in the quoted price?",
        "Is VAT included or excluded?",
        "Is delivery included, and can you support multiple addresses?",
        "What are the order cut-off dates and final approval deadlines?",
        "Can you include personalised messages?",
        "Can you provide a VAT invoice and written quote?",
        "What happens if a recipient is unavailable for delivery?",
        "Are alcohol-free alternatives available?",
        "How do you handle damaged, missing or delayed deliveries?",
        "Can you provide tracking or delivery confirmation?",
        "Are substitutions possible, and how are they approved?",
        "What recipient or attendee data format do you need?",
        "What cancellation, refund or amendment terms apply?",
    ]
    risk_checklist = [
        "Alcohol may not be suitable for every recipient or attendee.",
        "Check company gifting, expenses and procurement policy.",
        "Check client gift limits and anti-bribery or corruption policy.",
        "Offer alcohol-free alternatives where appropriate.",
        "Confirm delivery data handling before sharing recipient addresses.",
        "Check GDPR and data sharing requirements for recipient or attendee lists.",
        "Confirm international delivery restrictions, customs and courier rules.",
        "Confirm supplier pricing, stock, substitutions, delivery and availability in writing.",
        "Keep written supplier quotes and internal approval notes.",
        "Avoid gifts or event formats that could feel excessive for the relationship.",
    ]
    decision_scorecard = [
        {"criterion": "Budget fit", "score": "To score", "notes": "Compare quotes against budget including VAT and delivery."},
        {"criterion": "Brand fit", "score": "To score", "notes": "Check the option feels appropriate for the company and relationship."},
        {"criterion": "Delivery capability", "score": "To score", "notes": "Confirm count, locations, deadline and exception handling."},
        {"criterion": "Personalisation", "score": "To score", "notes": "Check messages, branding and proofing time."},
        {"criterion": "Low-risk suitability", "score": "To score", "notes": "Check broad appeal and alcohol-free alternatives."},
        {"criterion": "Admin effort", "score": "To score", "notes": "Assess address collection, approvals and follow-up work."},
        {"criterion": "Overall recommendation", "score": "To decide", "notes": "Choose the best balance of fit, confidence and admin effort."},
    ]

    base_budget = [
        {"label": "Planning budget", "amount": money(unit_budget), "note": "Per recipient/attendee before live supplier confirmation."},
        {"label": "Estimated spend", "amount": money(planned_spend), "note": "Count multiplied by planning budget."},
        {"label": "Delivery/venue allowance", "amount": "To confirm", "note": "Ask suppliers to quote this separately."},
        {"label": "Optional contingency", "amount": money(contingency), "note": "10% planning allowance for changes or extras."},
        {"label": "Estimated total range", "amount": f"{money(planned_spend)} + extras to {money(planned_spend + contingency)} + extras", "note": "Live supplier pricing, VAT and availability must be confirmed."},
    ]

    if is_gift:
        route = gift_route()
        supplier_brief = {
            "Recipient count": str(count or "To be confirmed"),
            "Budget per recipient": money(unit_budget),
            "Occasion": planner_input.get("occasion", "To be confirmed"),
            "Delivery deadline": deadline,
            "Required delivery coverage": "UK-only" if planner_input.get("uk_only") else "Confirm UK and any international requirements",
            "Branding/personalisation needs": "Branding required" if planner_input.get("branding_needed") else "No branding required unless simple",
            "Message requirements": "Personal gift messages needed" if planner_input.get("personal_message_needed") else "Standard message acceptable",
            "Known preferences": planner_input.get("known_preferences") or "Not known",
            "What to avoid": planner_input.get("avoid") or "Overly quirky bottles, unsuitable alcohol-led options and unconfirmed substitutions",
            "Decision timeline": "Quote and options needed within 24-48 hours where possible",
            "Required quote format": "Itemised quote showing unit price, VAT, delivery, packaging, personalisation, substitutions and lead time",
        }
        email_body = (
            "Hi [Supplier Name],\n\n"
            f"We are preparing a corporate gifting order for {count or 'the planned number of'} recipients and would like a written quote and recommendation.\n\n"
            "Requirements:\n"
            f"- Recommended route: {route}\n"
            f"- Occasion: {supplier_brief['Occasion']}\n"
            f"- Recipient count: {count or 'to confirm'}\n"
            f"- Budget range: around {money(unit_budget)} per recipient, plus VAT/delivery/personalisation where applicable\n"
            f"- Delivery deadline: {deadline}\n"
            f"- Delivery coverage: {supplier_brief['Required delivery coverage']}\n"
            f"- Messages: {supplier_brief['Message requirements']}\n"
            f"- Branding/personalisation: {supplier_brief['Branding/personalisation needs']}\n"
            f"- Known preferences: {supplier_brief['Known preferences']}\n"
            f"- Avoid: {supplier_brief['What to avoid']}\n\n"
            "Please send a quote with: product/package options, unit price, VAT, delivery cost, personalisation options, lead time, minimum order quantity, substitutions policy, alcohol-free alternatives, recipient data format and failed-delivery handling.\n\n"
            "Ideally we would like an itemised quote within 24-48 hours so we can compare options internally.\n\n"
            "Kind regards"
        )
        preview = {
            "pack_name": "ClientCellar Premium Brief Pack",
            "pack_type": "gift",
            "executive_summary": f"This Premium Brief Pack recommends a {route.lower()} route for {count or 'the planned number of'} recipients. It is designed to brief suppliers clearly, compare quotes consistently and support internal approval before any order is placed. Live pricing, stock, delivery and suitability must be confirmed directly.",
            "decision_recommendation": {"recommended_route": route, "why": "It balances broad appeal, corporate suitability, presentation and delivery practicality.", "suits": "Client, partner or employee gifting where tastes are mixed or unknown.", "may_not_suit": "Recipients who do not drink alcohol, strict gift policies or complex international delivery."},
            "budget_breakdown": base_budget,
            "supplier_brief": supplier_brief,
            "supplier_comparison": supplier_matrix(),
            "supplier_enquiry_email": {"subject": f"Corporate gifting quote request - {count or 'to confirm'} recipients", "body": email_body},
            "supplier_questions_checklist": supplier_questions,
            "internal_approval_note": f"Approval requested to progress a {route.lower()} corporate gifting route for {count or 'the planned number of'} recipients at a planning budget of {money(unit_budget)} per recipient, subject to supplier quotes, VAT, delivery, company gifting policy and alcohol suitability checks.",
            "risk_checklist": risk_checklist,
            "recipient_csv_template": "recipient_name,email,company,address_line_1,address_line_2,city,postcode,country,gift_message,alcohol_free_required,delivery_notes",
            "message_variants": [
                {"tone": "Formal client", "message": "Thank you for your continued partnership. With best wishes from the team."},
                {"tone": "Warm client", "message": "A small thank-you for working with us this year. We appreciate the partnership and hope you enjoy it."},
                {"tone": "Employee appreciation", "message": "Thank you for your hard work and energy. We hope you enjoy this small token of appreciation."},
                {"tone": "Partner thank-you", "message": "Thank you for your support and collaboration. We look forward to continuing the partnership."},
                {"tone": "Christmas neutral", "message": "With best wishes for a restful break and a successful year ahead."},
                {"tone": "Project completion", "message": "Thank you for your work with us on this project. We appreciated the collaboration."},
                {"tone": "Referral thank-you", "message": "Thank you for the introduction and your continued support. It is much appreciated."},
                {"tone": "Premium understated", "message": "With thanks from all of us. Please accept this as a small note of appreciation."},
            ],
            "timeline_action_plan": ["Today: confirm recipient list, budget owner, gift policy and alcohol-free requirements.", "Within 24 hours: send supplier enquiry using the structured brief.", "Within 48 hours: compare quotes using the scorecard and check VAT/delivery assumptions.", "One week before deadline: approve final messages, artwork and recipient CSV.", "Delivery week: monitor exceptions, failed deliveries and replacements."],
            "internal_update": f"Update: I’ve prepared a supplier-ready gifting brief for {count or 'the planned number of'} recipients. Recommended route: {route}. Planning budget: {money(unit_budget)} per recipient, with delivery/VAT to be confirmed. Next step is to request itemised supplier quotes and compare options for approval.",
            "final_recommendation": f"Send the supplier enquiry email to 2-3 suppliers, compare itemised quotes in the table, then approve the {route.lower()} option with the best balance of budget fit, delivery confidence, suitability and admin effort.",
            "decision_scorecard": decision_scorecard,
            "print_note": "Use the print/save, copy and download actions on this page for internal approval records.",
            "disclaimer": DISCLAIMER,
        }
    else:
        event_format = output.get("recommended_format", "Hosted corporate wine tasting")
        supplier_brief = {
            "Attendee count": str(count or "To be confirmed"),
            "Budget per attendee": money(unit_budget),
            "Event type": readable(planner_input.get("event_type", "corporate tasting")),
            "Preferred format": readable(planner_input.get("format", "not_sure")),
            "Location": planner_input.get("location") or "To be confirmed / remote",
            "Date": deadline,
            "Tone": readable(planner_input.get("tone", "fun")),
            "Wine knowledge level": readable(planner_input.get("wine_knowledge_level", "mixed")),
            "Food pairing needed": "Yes" if planner_input.get("food_pairing_needed") else "No / optional",
            "Known preferences": planner_input.get("known_preferences") or "Not known",
            "Decision timeline": "Availability and quote needed within 24-48 hours where possible",
            "Required quote format": "Itemised quote showing host fee, wine/packs, VAT, delivery, venue/food costs, cancellation terms and lead time",
        }
        email_body = (
            "Hi [Supplier Name],\n\n"
            f"We are planning a corporate wine tasting for around {count or 'the planned number of'} attendees and would like a written quote and suggested format.\n\n"
            f"- Recommended format: {event_format}\n"
            f"- Event type: {supplier_brief['Event type']}\n"
            f"- Location/date: {supplier_brief['Location']} / {supplier_brief['Date']}\n"
            f"- Attendee count: {count or 'to confirm'}\n"
            f"- Budget range: around {money(unit_budget)} per attendee, plus VAT/delivery/venue/food where applicable\n"
            f"- Tone: {supplier_brief['Tone']}\n"
            f"- Wine knowledge level: {supplier_brief['Wine knowledge level']}\n"
            f"- Food pairing: {supplier_brief['Food pairing needed']}\n\n"
            "Please send a quote with: event/package options, unit price or per-head price, VAT, delivery or venue costs, personalisation options, lead time, host availability, alcohol-free options, dietary handling, booking deadline and cancellation terms.\n\n"
            "Kind regards"
        )
        preview = {
            "pack_name": "ClientCellar Premium Brief Pack",
            "pack_type": "event",
            "executive_summary": f"This Premium Brief Pack recommends {event_format.lower()} for {count or 'the planned number of'} attendees. It is designed to brief event hosts, compare options, keep the format inclusive and support internal approval before booking. Live host availability, venue requirements, delivery and pricing must be confirmed directly.",
            "decision_recommendation": {"recommended_route": event_format, "why": "It gives the event enough structure for a corporate setting while keeping supplier questions clear.", "suits": "Team socials, client entertainment, away days or virtual events with mixed wine knowledge.", "may_not_suit": "Teams where alcohol is inappropriate, delivery addresses cannot be shared or venue/licensing rules are unclear."},
            "budget_breakdown": base_budget,
            "supplier_brief": supplier_brief,
            "supplier_comparison": supplier_matrix(),
            "supplier_enquiry_email": {"subject": f"Corporate wine tasting quote request - {count or 'to confirm'} attendees", "body": email_body},
            "event_run_of_show": ["Welcome and responsible drinking note - 5 minutes", "Host introduction and format overview - 5 minutes", "First wine or alcohol-free serve - 15 minutes", "Second wine with guided discussion - 15 minutes", "Optional food pairing or team activity - 20 minutes", "Final tasting, Q&A and close - 10 minutes"],
            "internal_invite_copy": output.get("internal_invite_copy", "You are invited to a corporate wine tasting. Full details will follow."),
            "supplier_questions_checklist": supplier_questions,
            "risk_checklist": risk_checklist,
            "alcohol_free_options_note": "Ask the supplier for alcohol-free tasting packs or a comparable non-alcoholic alternative so the event remains inclusive.",
            "attendee_info_template": "attendee_name,email,company,delivery_address,dietary_requirements,alcohol_free_required,accessibility_needs,notes",
            "timeline_action_plan": ["Today: confirm attendees, format, budget owner and alcohol-free requirements.", "Within 24 hours: send supplier/host enquiry using the structured brief.", "Within 48 hours: compare quotes using the scorecard and check inclusions/exclusions.", "One week before event: confirm attendee list, delivery addresses, joining details and dietary needs.", "Event week: monitor pack delivery, final run sheet and attendee exceptions."],
            "internal_approval_note": f"Approval requested to progress a corporate wine tasting for {count or 'the planned number of'} attendees at a planning budget of {money(unit_budget)} per attendee, subject to supplier quotes, VAT, delivery, host availability, venue requirements and cancellation terms.",
            "decision_scorecard": decision_scorecard,
            "message_variants": [{"tone": "Internal invite", "message": output.get("internal_invite_copy", "You are invited to a corporate wine tasting. Full details will follow.")}, {"tone": "Client-safe", "message": "Join us for a relaxed hosted wine tasting with light structure, sensible pacing and alcohol-free options available."}, {"tone": "Team social", "message": "Join the team for a beginner-friendly wine tasting session with plenty of space for questions and conversation."}],
            "internal_update": f"Update: I’ve prepared a supplier-ready event brief for {count or 'the planned number of'} attendees. Recommended format: {event_format}. Planning budget: {money(unit_budget)} per attendee, with delivery/venue/VAT to be confirmed. Next step is to request itemised supplier quotes and compare options for approval.",
            "final_recommendation": f"Send the supplier enquiry email to 2-3 event providers, compare itemised quotes in the table, then approve the format with the clearest inclusions, delivery/venue confidence, alcohol-free support and cancellation terms.",
            "print_note": "Use the print/save, copy and download actions on this page for internal approval records.",
            "disclaimer": DISCLAIMER,
        }
    preview = maybe_improve_plan(preview, "premium_pack")
    return add_premium_advisory_sections(preview, req.pack_type, unit_budget, count)


def make_fallback_premium_pack_preview(pack_type: str = "gift", pack: dict | None = None) -> dict:
    """Build a complete paid-pack document when saved planner details are unavailable."""
    is_event = pack_type == "event"
    pack_label = "event wine brief" if is_event else "gift brief"
    route = "Corporate wine tasting event provider" if is_event else "Corporate wine gift supplier or premium wine merchant"
    count_label = "attendee count" if is_event else "recipient count"
    csv_template = (
        "attendee_name,email,company,delivery_address,dietary_requirements,alcohol_free_required,accessibility_needs,notes"
        if is_event
        else "recipient_name,email,company,address_line_1,address_line_2,city,postcode,country,gift_message,alcohol_free_required,delivery_notes"
    )
    email_subject = (
        "Corporate wine tasting quote request"
        if is_event
        else "Corporate gifting quote request"
    )
    email_body = (
        "Hi [Supplier Name],\n\n"
        f"We are preparing a corporate {pack_label} and would like an itemised recommendation and quote.\n\n"
        "Please include suitable options, quantity assumptions, budget range, VAT, delivery or venue requirements, personalisation options, lead times, alcohol-free alternatives, substitutions, cancellation terms and any minimum order terms.\n\n"
        "We will confirm final quantities, deadline and delivery details before placing any order or booking.\n\n"
        "Kind regards"
    )
    fallback_note = (
        "Some planning details were not available, so this pack has been prepared as a supplier-ready starting point. "
        "Confirm live pricing, stock, delivery and suitability directly with suppliers."
    )
    preview = {
        "pack_name": "ClientCellar Premium Brief Pack",
        "pack_type": pack_type,
        "fallback_note": fallback_note,
        "executive_summary": (
            f"{fallback_note} Use this pack to brief suppliers, compare options and prepare a decision-ready internal recommendation."
        ),
        "decision_recommendation": {
            "recommended_route": route,
            "why": "This route keeps the buying process structured while supplier details, pricing and availability are confirmed directly.",
            "suits": "UK business gifting, client thank-yous, staff recognition or workplace-appropriate wine planning.",
            "may_not_suit": "Recipients or workplaces where alcohol is unsuitable, gift limits are strict or international delivery is complex.",
        },
        "budget_breakdown": [
            {"label": "Planning budget", "amount": "To confirm", "note": "Set a per-person or per-recipient budget before requesting quotes."},
            {"label": "Estimated quantity", "amount": "To confirm", "note": f"Confirm final {count_label} and any alcohol-free alternatives."},
            {"label": "Delivery / fulfilment", "amount": "To confirm", "note": "Ask suppliers to itemise delivery, packaging, VAT and substitutions."},
            {"label": "Contingency", "amount": "10% suggested", "note": "Allow for failed deliveries, substitutions, extra guests or deadline changes."},
        ],
        "supplier_brief": {
            "Brief type": "Corporate wine tasting event" if is_event else "Corporate wine gift",
            "Quantity": f"Final {count_label} to be confirmed",
            "Budget": "Ask supplier for options at sensible budget bands and itemised costs",
            "Deadline": "To be confirmed before order or booking",
            "Delivery / location": "UK requirements to be confirmed directly",
            "Preferences": "Provide known preferences, dietary needs and alcohol-free requirements where relevant",
            "Quote format": "Itemised quote showing VAT, delivery, lead time, substitutions and cancellation terms",
        },
        "supplier_comparison": [
            {
                "supplier_id": "majestic",
                "supplier": "Majestic",
                "supplier_type": route,
                "product_package": "Indicative package route",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask whether gift notes, branding and proofing can be handled inside the deadline.",
                "lead_time": "Begin supplier contact 2-3 weeks before dispatch; longer in seasonal peaks.",
                "pros": "Structured corporate enquiry and supplier-ready quote comparison.",
                "risks": "No live stock, price or availability is included.",
                "decision": "Use only after the supplier confirms admin, delivery and substitution handling in writing.",
                "best_for": "Primary buying route",
                "budget_fit": "Confirm against agreed budget bands.",
                "strengths": "Structured corporate enquiry and supplier-ready quote comparison.",
                "watchouts": "No live stock, price or availability is included.",
                "questions_to_ask": "Can you meet the quantity, deadline, delivery/location and alcohol-free requirements?",
            },
            {
                "supplier_id": None if is_event else "marks-spencer-corporate",
                "supplier": "Venue/caterer wine package" if is_event else "M&S Hampers",
                "supplier_type": "Venue/caterer wine package" if is_event else "Corporate hamper supplier",
                "product_package": "Venue wine package" if is_event else "Wine hamper or alternative hamper",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Service notes and menu details" if is_event else "Gift message and packaging options",
                "lead_time": "Begin supplier contact 2-3 weeks before dispatch; longer in seasonal peaks.",
                "pros": "Keeps service, corkage and venue rules in one place." if is_event else "Can combine wine with food, packaging and gift messaging.",
                "risks": "Check corkage, service charges and house wine quality." if is_event else "Check allergens, substitutions, breakage and delivery coverage.",
                "decision": "Useful fallback if venue rules make outside supply hard." if is_event else "Useful fallback if single-bottle gifting feels too narrow.",
                "best_for": "Venue-controlled events and low-admin service" if is_event else "Reducing taste risk and improving presentation",
                "budget_fit": "Useful when corkage or service control matters." if is_event else "Useful when one bottle may feel too narrow.",
                "strengths": "Keeps service, corkage and venue rules in one place." if is_event else "Can combine wine with food, packaging and gift messaging.",
                "watchouts": "Check corkage, service charges and house wine quality." if is_event else "Check allergens, substitutions, breakage and delivery coverage.",
                "questions_to_ask": "Can you confirm corkage, service charge, house wine quality and alcohol-free options?" if is_event else "Can you provide alcohol-free or food-only alternatives for unsuitable recipients?",
            },
            {
                "supplier_id": "local-independent-wine-merchant",
                "supplier": "Local independent wine merchant",
                "supplier_type": "Local independent wine merchant",
                "product_package": "Merchant-led wine gift route",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Likely limited; confirm directly",
                "lead_time": "Begin supplier contact 1-3 weeks before dispatch and keep a backup option.",
                "pros": "Advice-led recommendations and more personal bottle selection.",
                "risks": "May have lighter multi-address delivery and corporate admin tooling.",
                "decision": "Best reserved for VIP or advice-led recipients.",
                "best_for": "VIP recipients and more personal recommendations",
                "budget_fit": "Often useful for higher-touch comparison.",
                "strengths": "Advice-led recommendations and more personal bottle selection.",
                "watchouts": "May have lighter multi-address delivery and corporate admin tooling.",
                "questions_to_ask": "Can you support business orders, VAT receipts, multiple addresses and message inserts?",
            },
        ],
        "supplier_enquiry_email": {"subject": email_subject, "body": email_body},
        "supplier_questions_checklist": [
            "Can you support the required quantity and deadline?",
            "What exactly is included in the quoted price?",
            "Is VAT included or excluded?",
            "Are delivery, packaging and message inserts included?",
            "What recipient or attendee data format do you need?",
            "What substitutions may be made, and how are they approved?",
            "Can you provide alcohol-free alternatives?",
            "Can you provide a VAT receipt or itemised invoice?",
            "What are the cancellation, amendment and failed-delivery terms?",
        ],
        "message_variants": [
            {"tone": "Formal client", "message": "Thank you for your continued partnership. With best wishes from the team."},
            {"tone": "Warm thank-you", "message": "A small thank-you for your support. We appreciate working with you."},
            {"tone": "Staff recognition", "message": "Thank you for your hard work and contribution. We hope you enjoy this small token of appreciation."},
        ],
        "risk_checklist": [
            "Check whether alcohol is suitable for every recipient or workplace.",
            "Consider alcohol-free alternatives.",
            "Confirm client gift, procurement and anti-bribery policies.",
            "Confirm supplier pricing, stock, delivery and substitutions directly.",
            "Check GDPR/data sharing before sending recipient or attendee details.",
            "Keep written supplier quotes and approval notes.",
        ],
        "timeline_action_plan": [
            "Confirm budget owner, quantity, deadline and suitability requirements.",
            "Send the supplier-ready enquiry email to 2-3 relevant supplier types.",
            "Compare quotes using budget, delivery, suitability and admin effort.",
            "Get internal approval before order or booking.",
            "Confirm final data, messaging, delivery and substitution policy with the chosen supplier.",
        ],
        "internal_approval_note": (
            f"Approval requested to proceed with a supplier shortlist for a corporate {pack_label}. "
            "Final supplier choice should be based on itemised quotes, VAT/delivery assumptions, recipient suitability, policy checks and fulfilment confidence."
        ),
        "recipient_csv_template": None if is_event else csv_template,
        "attendee_info_template": csv_template if is_event else None,
        "internal_update": (
            f"I have prepared a supplier-ready {pack_label} pack. Next step is to request itemised quotes and compare options for approval."
        ),
        "final_recommendation": (
            "Send the supplier enquiry email to 2-3 relevant suppliers, compare itemised quotes in the table, then choose the option with the strongest budget fit, delivery confidence and suitability checks."
        ),
        "print_note": "Print or save this page as a PDF for internal approval.",
        "disclaimer": DISCLAIMER,
    }
    return add_premium_advisory_sections(preview, pack_type)


def normalise_premium_pack_view_preview(pack: dict, preview: dict | None) -> dict:
    """Ensure the paid pack view always has visible document sections."""
    pack_type = (preview or {}).get("pack_type") or pack.get("pack_type") or "gift"
    preview = dict(preview or {})
    if not preview:
        preview = make_fallback_premium_pack_preview(pack_type, pack)
    preview = add_premium_advisory_sections(preview, pack_type)

    sections = preview.get("sections") or preview.get("document_sections")
    document_sections = []
    if isinstance(sections, list):
        for index, section in enumerate(sections, start=1):
            if isinstance(section, dict):
                title = section.get("title") or section.get("heading") or f"Section {index}"
                content = section.get("content") or section.get("body") or section.get("text")
                item_list = section.get("items") or section.get("item_list")
            else:
                title = f"Section {index}"
                content = str(section)
                item_list = None
            document_sections.append({"title": title, "content": content, "item_list": item_list})
    elif preview.get("content"):
        document_sections.append({"title": "Premium Brief Pack", "content": preview.get("content")})

    if not document_sections:
        supplier_brief = preview.get("supplier_brief") or {}
        decision = preview.get("decision_recommendation") or {}
        budget = preview.get("budget_breakdown") or []
        comparison = preview.get("supplier_comparison") or []
        questions = preview.get("supplier_questions_checklist") or []
        messages = preview.get("message_variants") or []
        risks = preview.get("risk_checklist") or []
        next_steps = preview.get("timeline_action_plan") or []

        def table_items(mapping: dict) -> list[str]:
            return [f"{str(key).replace('_', ' ').title()}: {value}" for key, value in mapping.items() if value]

        def budget_items(rows: list[dict]) -> list[str]:
            return [
                f"{row.get('label', 'Budget item')}: {row.get('amount', 'To confirm')} - {row.get('note', 'Confirm directly.')}"
                for row in rows
            ]

        email = preview.get("supplier_enquiry_email") or {}
        document_sections = [
            {"title": "Executive summary", "content": preview.get("executive_summary")},
            {"title": "Supplier enquiry email", "content": email.get("body")},
            {"title": "Supplier quote comparison table", "content": "Use this table to compare written supplier quotes consistently." if comparison else None},
            {"title": "Budget and quantity breakdown", "item_list": budget_items(budget)},
            {"title": "Internal approval summary", "content": preview.get("internal_approval_note")},
            {"title": "Supplier questions checklist", "item_list": questions},
            {"title": "Risk checklist", "item_list": risks},
            {"title": "Final recommendation", "content": preview.get("final_recommendation") or decision.get("why") or preview.get("internal_update")},
        ]

    document_sections = [
        section for section in document_sections
        if section.get("content") or section.get("item_list")
    ]
    if not document_sections:
        fallback = make_fallback_premium_pack_preview(pack_type, pack)
        return normalise_premium_pack_view_preview(pack, fallback)

    preview["document_sections"] = document_sections
    preview.setdefault("pack_name", "ClientCellar Premium Brief Pack")
    preview.setdefault("pack_type", pack_type)
    preview.setdefault("disclaimer", DISCLAIMER)
    return preview


def render_email_html(text_body: str) -> str:
    paragraphs = "".join(
        f"<p>{line}</p>" if line else "<br>"
        for line in text_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").split("\n")
    )
    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#241713">
      {paragraphs}
    </div>
    """


def send_email(recipient_email: str, subject: str, text_body: str, html_body: str | None = None) -> dict:
    """Send transactional email with Resend. Requires verified sending domain in Resend dashboard."""
    from_email = os.getenv("EMAIL_FROM", "ClientCellar <hello@clientcellar.co.uk>")
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        logger.error(
            "REQUEST_ACCESS_EMAIL_FAILED error=missing_resend_api_key recipient=%s subject=%s",
            recipient_email,
            subject,
        )
        return {"sent": False, "provider": "resend", "reason": "missing_api_key"}

    try:
        import resend
        logger.info("RESEND_IMPORT_OK")
        resend.api_key = resend_api_key
        logger.info(
            "REQUEST_ACCESS_SENDING_EMAIL recipient=%s subject=%s from=%s",
            recipient_email,
            subject,
            from_email,
        )
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": [recipient_email],
                "subject": subject,
                "html": html_body or render_email_html(text_body),
                "text": text_body,
            }
        )
        response_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info("REQUEST_ACCESS_EMAIL_SENT resend_id=%s recipient=%s subject=%s", response_id, recipient_email, subject)
        return {"sent": True, "provider": "resend", "id": response_id}
    except Exception as exc:
        logger.exception("REQUEST_ACCESS_EMAIL_FAILED error=%s recipient=%s subject=%s", repr(exc), recipient_email, subject)
        return {"sent": False, "provider": "resend", "error": str(exc)}


def build_premium_pack_email(request: Request, customer_email: str | None, pack_token: str) -> dict | None:
    """Send/prepare the post-payment saved-pack email."""
    if not customer_email:
        return None
    premium_pack_url = absolute_url(request, f"/premium-pack/view/{pack_token}")
    subject = "Your ClientCellar Premium Brief Pack is ready"
    body = (
        "Your Premium Brief Pack is ready to view and download.\n\n"
        f"Open your pack:\n{premium_pack_url}\n\n"
        "Keep this email safe — it lets you return to your saved pack later.\n\n"
        "You can also use My packs on ClientCellar to request your secure link again."
    )
    send_result = send_email(customer_email, subject, body)
    logger.info(
        "Premium pack ready email processed recipient=%s pack_token=%s sent=%s response_id=%s reason=%s",
        customer_email,
        pack_token,
        send_result.get("sent"),
        send_result.get("id"),
        send_result.get("reason") or send_result.get("error"),
    )
    email_payload = {
        "to": customer_email,
        "subject": subject,
        "body": body,
        "premium_pack_url": premium_pack_url,
        "send_result": send_result,
    }
    return email_payload


def send_pack_ready_email(request: Request, pack: dict) -> dict | None:
    """Server-side saved-pack email helper backed by Resend."""
    customer_email = pack.get("customer_email") or pack.get("email")
    access_token = pack.get("access_token") or pack.get("pack_token")
    return build_premium_pack_email(request, customer_email, access_token)


def send_pack_recovery_email(request: Request, email: str, packs: list[dict]) -> list[dict]:
    """Send recovery email without revealing pack existence to the browser."""
    prepared = []
    for pack in packs:
        access_token = pack.get("access_token") or pack.get("pack_token")
        prepared.append(
            {
                "title": pack.get("title") or "Premium Brief Pack",
                "premium_pack_url": absolute_url(request, f"/premium-pack/view/{access_token}"),
            }
        )
    if prepared:
        lines = [
            "Your saved Premium Brief Packs are ready to access.",
            "",
            *[
                f"- {item['title']}\n  {item['premium_pack_url']}"
                for item in prepared
            ],
            "",
            "Keep these links secure.",
            "",
            "If you did not request this email, you can ignore it.",
        ]
        logger.info(
            "REQUEST_ACCESS_SENDING_EMAIL recipient=%s pack_count=%s",
            email,
            len(prepared),
        )
        result = send_email(email, "Your ClientCellar Premium Brief Packs", "\n".join(lines))
        logger.info(
            "Premium pack recovery email processed recipient=%s pack_count=%s sent=%s response_id=%s reason=%s",
            email,
            len(prepared),
            result.get("sent"),
            result.get("id"),
            result.get("reason") or result.get("error"),
        )
        if not result.get("sent"):
            logger.warning(
                "REQUEST_ACCESS_EMAIL_FAILED error=%s recipient=%s fallback_urls=%s",
                result.get("reason") or result.get("error"),
                email,
                [item["premium_pack_url"] for item in prepared],
            )
    if not prepared:
        logger.info("REQUEST_ACCESS_NO_PACKS email=%s", email)
    return prepared


def allow_pack_access_request(email: str) -> bool:
    """Lightweight process-local throttle for recovery requests; replace with durable rate limiting later."""
    key = email.lower().strip()
    count = PACK_ACCESS_REQUEST_COUNTS.get(key, 0) + 1
    PACK_ACCESS_REQUEST_COUNTS[key] = count
    return count <= 5


GUIDES = {
    "corporate-wine-gifts-uk": {
        "title": "Corporate Wine Gifts UK",
        "description": "A practical UK guide to corporate wine gifts for clients, employees, suppliers and partners.",
        "h1": "Corporate wine gifts for UK businesses",
        "intro": "Corporate wine gifts work best when they are thoughtful, easy to fulfil and safe for the business context. This guide helps you choose sensible routes without relying on live prices or stock claims.",
        "audience": [
            "Client, prospect and partner gift planning.",
            "Employee thank-you gifts and seasonal staff gifting.",
            "Supplier or partner gifts where the tone needs to stay professional.",
        ],
        "budget": [
            "Under £20: keep it simple. Consider modest bottles, small sparkling alternatives, gift cards or alcohol-free choices where wine feels too tight.",
            "£20-£40: a practical band for a good single bottle, small hamper or broad-appeal sparkling option.",
            "£40-£75: a strong corporate range for wine hampers, English sparkling, Champagne alternatives and classic mixed gifts.",
            "£75+: premium gifts, fine wine merchant routes, Champagne or luxury hampers with stronger presentation.",
        ],
        "approaches": [
            "For unknown tastes, choose sparkling, classic red/white pairs or a hamper rather than a quirky single bottle.",
            "For clients, keep the choice polished and low-risk.",
            "For employees, offer choice or an alcohol-free alternative wherever possible.",
        ],
        "avoid": [
            "Do not assume every recipient drinks alcohol.",
            "Do not promise delivery dates until the supplier confirms them.",
            "Avoid obscure styles for clients or prospects unless you know their taste.",
        ],
        "checklist": [
            "Confirm recipient count, addresses and deadline.",
            "Check company gifting, tax and procurement rules.",
            "Ask suppliers about current price, delivery, VAT, minimum orders and message options.",
            "Prepare a recipient CSV before ordering.",
        ],
        "faqs": [
            {"q": "What is a safe corporate wine gift?", "a": "A safe option is usually classic, recognisable and easy to enjoy: sparkling, a balanced red/white pair, or a wine and food hamper."},
            {"q": "How much should we spend on client wine gifts?", "a": "Many businesses start around £40-£75 for a polished client gift, but the right amount depends on the relationship, policy and occasion."},
        ],
        "cta": "Plan corporate gifts",
        "cta_url": "/gift-planner",
        "related": ["christmas-wine-gifts-for-clients", "staff-wine-gifts", "corporate-wine-hampers"],
        "affiliate": True,
    },
    "christmas-wine-gifts-for-clients": {
        "title": "Christmas Wine Gifts for Clients",
        "description": "Plan safe, polished Christmas wine gifts for clients with budget guidance, message ideas and supplier enquiry tips.",
        "h1": "Christmas wine gifts for clients",
        "intro": "Christmas client gifts need earlier planning because supplier cut-offs, branded packaging, recipient data and delivery windows can all become tight in November and December.",
        "audience": [
            "Account teams planning client thank-you gifts.",
            "Businesses sending gifts to prospects, referrers or partners.",
            "Teams that need a professional message and low-risk gift style.",
        ],
        "budget": [
            "Under £40: choose a good single bottle, sparkling alternative or compact hamper.",
            "£40-£75: a strong range for English sparkling, Champagne alternatives and wine hampers.",
            "£75+: consider Champagne, premium hampers or fine wine merchant gifts for priority accounts.",
        ],
        "approaches": [
            "Use safe gift styles: sparkling, classic red/white pair, wine and food hamper, or premium alcohol-free choice.",
            "Champagne is not the only festive option; English sparkling and Crémant-style choices can feel polished without being too flashy.",
            "Keep messages warm but professional: thank the recipient for the partnership and avoid heavy sales language.",
        ],
        "avoid": [
            "Leaving delivery and address collection until the final week.",
            "Overly novelty bottles or risky jokes on packaging.",
            "Assuming all client contacts can accept alcohol or gifts under their company policy.",
        ],
        "checklist": [
            "Collect addresses and any gift acceptance limits early.",
            "Ask suppliers for Christmas order cut-offs and delivery exclusions.",
            "Prepare one standard message plus optional account-specific variants.",
            "Check alcohol-free and non-alcohol alternatives for sensitive recipients.",
        ],
        "faqs": [
            {"q": "What message should we include?", "a": "Keep it short: thank them for the partnership, wish them a restful festive break, and sign off from the team."},
            {"q": "What is a good alternative to Champagne?", "a": "English sparkling, Crémant-style sparkling wine or a premium wine hamper can be strong alternatives."},
        ],
        "cta": "Plan Christmas client gifts",
        "cta_url": "/gift-planner",
        "related": ["corporate-wine-gifts-uk", "champagne-gifts-for-clients", "client-thank-you-wine-gifts"],
        "affiliate": True,
    },
    "staff-wine-gifts": {
        "title": "Staff Wine Gifts",
        "description": "A practical guide to employee wine gifts, workplace policy, alcohol-free options and bulk ordering.",
        "h1": "Staff wine gifts and employee thank-yous",
        "intro": "Employee wine gifts can work well, but they need more care than client gifts because workplace policy, inclusivity and personal preference matter.",
        "audience": [
            "HR, operations and founders planning staff thank-you gifts.",
            "Managers arranging year-end gifts for teams.",
            "Businesses that need a bulk ordering checklist before speaking to suppliers.",
        ],
        "budget": [
            "Under £20: consider simple bottles, mini formats, gift cards or non-wine alternatives.",
            "£20-£40: useful for single bottles, small hampers or sparkling alternatives.",
            "£40-£75: allows stronger hampers, mixed gifts and better presentation.",
        ],
        "approaches": [
            "Offer a choice where possible: red, white, sparkling, hamper or alcohol-free.",
            "Use broad-appeal styles rather than specialist bottles.",
            "Keep the message appreciative and inclusive.",
        ],
        "avoid": [
            "Making alcohol the only available reward.",
            "Ignoring religious, health, pregnancy, recovery or personal preference considerations.",
            "Sending gifts without checking HR and expenses policy.",
        ],
        "checklist": [
            "Confirm headcount and budget including VAT and delivery.",
            "Ask whether employees can choose an alcohol-free option.",
            "Check address collection and privacy handling.",
            "Confirm supplier data format, delivery lead time and failed-delivery process.",
        ],
        "faqs": [
            {"q": "Can you send wine gifts to employees?", "a": "Often yes, but check workplace policy and offer alcohol-free alternatives so the gift stays inclusive."},
            {"q": "Are wine gifts appropriate for every workplace?", "a": "No. Some workplaces or teams will be better served by food hampers, vouchers or choice-based gifts."},
        ],
        "cta": "Plan staff wine gifts",
        "cta_url": "/gift-planner",
        "related": ["corporate-wine-gifts-uk", "corporate-wine-hampers", "virtual-wine-tasting-for-teams"],
        "affiliate": True,
    },
    "client-thank-you-wine-gifts": {
        "title": "Client Thank-You Wine Gifts",
        "description": "Professional thank-you wine gift ideas after a deal, project, referral or meeting.",
        "h1": "Client thank-you wine gifts",
        "intro": "A thank-you gift after a project, deal, referral or important meeting should feel considered, not extravagant or awkward.",
        "audience": [
            "Sales and account teams thanking clients after a deal.",
            "Consultants and agencies sending project completion gifts.",
            "Businesses thanking referrers or partners.",
        ],
        "budget": [
            "£20-£40: practical single bottle or compact hamper.",
            "£40-£75: polished wine hamper, English sparkling or classic red/white pair.",
            "£75+: premium-but-not-flashy gift for high-value relationships.",
        ],
        "approaches": [
            "Keep the tone professional and warm.",
            "Choose safer styles such as sparkling, classic Rioja Reserva-style red, balanced white or a hamper.",
            "Use premium presentation without making the gift feel like pressure or inducement.",
        ],
        "avoid": [
            "Flashy gifts that could create procurement or anti-bribery concerns.",
            "Very personal messages unless the relationship supports it.",
            "Sending alcohol where the recipient's policy may prevent acceptance.",
        ],
        "checklist": [
            "Check gift limits and acceptance rules.",
            "Confirm the recipient's correct delivery address.",
            "Ask the supplier for a discreet gift note option.",
            "Keep a record of the gift value for internal compliance.",
        ],
        "faqs": [
            {"q": "What should a client thank-you note say?", "a": "A simple line such as 'Thank you for working with us on this project. We appreciated the partnership.' is usually enough."},
        ],
        "cta": "Create a thank-you gift plan",
        "cta_url": "/gift-planner",
        "related": ["corporate-wine-gifts-uk", "christmas-wine-gifts-for-clients", "champagne-gifts-for-clients"],
        "affiliate": True,
    },
    "corporate-wine-hampers": {
        "title": "Corporate Wine Hampers",
        "description": "When to choose corporate wine hampers, budget guidance, branding notes and practical supplier questions.",
        "h1": "Corporate wine hampers",
        "intro": "Wine hampers can be more forgiving than a single bottle because they combine presentation, food and choice. They are especially useful when recipient tastes are unknown.",
        "audience": [
            "Teams sending client, partner or employee gifts.",
            "Businesses that want a warmer gift than a single bottle.",
            "Marketing and operations teams considering branded packaging.",
        ],
        "budget": [
            "£25-£40: compact hamper or wine-plus-snack format.",
            "£40-£75: strong corporate range for wine and food pairings.",
            "£75+: premium hampers with stronger packaging and personalisation options.",
        ],
        "approaches": [
            "Use wine and food pairing gifts for broad appeal.",
            "Ask about branded sleeves, gift notes, delivery inserts and proofing times.",
            "Choose hampers when presentation matters or tastes are mixed.",
        ],
        "avoid": [
            "Overly large hampers that are hard to deliver or store.",
            "Perishable food without clear delivery timing.",
            "Branding that delays the order beyond your deadline.",
        ],
        "checklist": [
            "Confirm hamper contents, substitutions and allergens.",
            "Ask whether alcohol-free hamper options are available.",
            "Check branding minimum order quantities and artwork deadlines.",
            "Confirm delivery coverage and failed-delivery handling.",
        ],
        "faqs": [
            {"q": "When is a hamper better than a bottle?", "a": "When tastes are unknown, presentation matters, or you want to include food and alcohol-free alternatives."},
        ],
        "cta": "Plan wine hampers",
        "cta_url": "/gift-planner",
        "related": ["corporate-wine-gifts-uk", "staff-wine-gifts", "christmas-wine-gifts-for-clients"],
        "affiliate": True,
    },
    "corporate-champagne-gifts": {
        "title": "Corporate Champagne Gifts",
        "description": "A UK business guide to Champagne, English sparkling and Crémant-style corporate gifts.",
        "h1": "Corporate Champagne and sparkling wine gifts",
        "intro": "Champagne can feel celebratory and premium, but it is not always the most suitable or best-value corporate gift. Sparkling alternatives can be just as polished.",
        "audience": [
            "Businesses marking deals, milestones or festive moments.",
            "Teams sending premium client gifts.",
            "Anyone comparing Champagne with English sparkling or Crémant-style options.",
        ],
        "budget": [
            "£30-£45: consider English sparkling or quality sparkling alternatives.",
            "£45-£75: useful range for Champagne alternatives, English sparkling and gift packaging.",
            "£75+: Champagne, premium sparkling hampers or fine wine merchant routes.",
        ],
        "approaches": [
            "Champagne signals celebration and premium positioning.",
            "English sparkling can be a strong UK-focused choice.",
            "Crémant-style sparkling can offer a polished alternative where Champagne feels too expensive or obvious.",
        ],
        "avoid": [
            "Choosing Champagne purely for status if the recipient may not drink alcohol.",
            "Overly flashy presentation for conservative client relationships.",
            "Assuming international delivery is simple for alcohol gifts.",
        ],
        "checklist": [
            "Confirm gift acceptance limits and alcohol policy.",
            "Ask suppliers for packaging, gift note and delivery options.",
            "Compare Champagne, English sparkling and hamper routes.",
            "Include alcohol-free alternatives for mixed groups.",
        ],
        "faqs": [
            {"q": "What is a good alternative to Champagne?", "a": "English sparkling wine or Crémant-style sparkling wine can feel celebratory while giving you more flexibility on budget."},
        ],
        "cta": "Plan sparkling wine gifts",
        "cta_url": "/gift-planner",
        "related": ["christmas-wine-gifts-for-clients", "client-thank-you-wine-gifts", "corporate-wine-gifts-uk"],
        "affiliate": True,
    },
    "virtual-wine-tasting-for-teams": {
        "title": "Virtual Wine Tasting for Teams",
        "description": "Plan remote and hybrid team wine tasting events with budget, delivery and invite guidance.",
        "h1": "Virtual wine tasting for teams",
        "intro": "Virtual wine tastings can work well for remote and hybrid teams when packs arrive on time, the host keeps it inclusive and the format is not too boozy.",
        "audience": [
            "Remote and hybrid teams planning socials.",
            "People teams organising lightweight team events.",
            "Managers who need an internal invite and supplier enquiry brief.",
        ],
        "budget": [
            "Under £25 per head: informal tasting or simple pack route.",
            "£25-£60 per head: strong range for hosted virtual tastings with delivered packs.",
            "£60+ per head: more premium wines, food pairing or stronger facilitation.",
        ],
        "approaches": [
            "A supplier usually ships packs to attendees and provides a host on video.",
            "Send joining details early and include a clear finish time.",
            "Offer alcohol-free packs so nobody is excluded.",
        ],
        "avoid": [
            "Leaving address collection too late.",
            "Making drinking feel compulsory.",
            "Choosing a format that requires too much wine knowledge.",
        ],
        "checklist": [
            "Confirm attendee addresses and privacy handling.",
            "Ask suppliers about delivery lead times and missed deliveries.",
            "Prepare an internal invite with date, time, format and alcohol-free options.",
            "Check whether food pairing changes the delivery deadline.",
        ],
        "faqs": [
            {"q": "Can virtual wine tastings work for remote teams?", "a": "Yes, if packs arrive on time, the host is engaging and alcohol-free options are available."},
            {"q": "How much does a corporate wine tasting cost?", "a": "A practical hosted virtual tasting often sits around £25-£60 per head, but suppliers must confirm current pricing."},
        ],
        "cta": "Plan a virtual tasting",
        "cta_url": "/event-planner",
        "related": ["wine-tasting-team-building", "corporate-wine-tasting-london", "staff-wine-gifts"],
        "affiliate": False,
    },
    "corporate-wine-tasting-london": {
        "title": "Corporate Wine Tasting London",
        "description": "Plan London corporate wine tastings for client entertainment, team socials and hosted private events.",
        "h1": "Corporate wine tasting events in London",
        "intro": "London corporate wine tastings can work for client entertainment, team socials and private hosted events, but venue, timing and transport details matter.",
        "audience": [
            "London teams planning client entertainment.",
            "Businesses organising team socials or away-day add-ons.",
            "Event planners comparing private rooms, merchants and hosted tastings.",
        ],
        "budget": [
            "Under £60 per head: simple hosted tasting or merchant-led format.",
            "£60-£120 per head: polished client-safe tasting, private room or food pairing.",
            "£120+ per head: premium private event, fine wine or dinner pairing.",
        ],
        "approaches": [
            "For client entertainment, keep the tone polished and not too boozy.",
            "For team socials, choose a format with light structure and room for conversation.",
            "Private rooms and hosted tastings can help with service, pacing and atmosphere.",
        ],
        "avoid": [
            "Venues that are awkward for transport after drinking.",
            "Late finishes that make the event feel heavy.",
            "Formats that assume strong wine knowledge.",
        ],
        "checklist": [
            "Confirm location, start time, finish time and transport options.",
            "Ask about licensing, service, food, water and dietary requirements.",
            "Confirm minimum spend, room hire and cancellation terms.",
            "Include alcohol-free alternatives in the brief.",
        ],
        "faqs": [
            {"q": "How much should a London corporate tasting cost?", "a": "A hosted event might be planned from around £60 per head upwards, depending on venue, wine, food and service. Confirm pricing with suppliers."},
        ],
        "cta": "Plan a London wine tasting",
        "cta_url": "/event-planner",
        "related": ["wine-tasting-team-building", "virtual-wine-tasting-for-teams", "corporate-wine-gifts-uk"],
        "affiliate": False,
    },
    "wine-tasting-team-building": {
        "title": "Wine Tasting Team Building",
        "description": "Use wine tasting as team building without making the event too boozy or exclusive.",
        "h1": "Wine tasting as team building",
        "intro": "Wine tasting can be a good team-building format when it is structured, inclusive and paced carefully. The goal is conversation and shared learning, not heavy drinking.",
        "audience": [
            "People teams organising socials or away days.",
            "Managers looking for a fun but professional activity.",
            "Remote, hybrid and office-based teams comparing event formats.",
        ],
        "budget": [
            "Under £25 per head: informal tasting or simple virtual format.",
            "£25-£60 per head: hosted tasting with accessible wines.",
            "£60-£120 per head: stronger in-person experience with food pairing or private host.",
        ],
        "approaches": [
            "Fun formats can include quizzes, blind tasting or food pairing.",
            "Educational formats work well for mixed seniority because they give the session structure.",
            "Inclusivity matters: provide alcohol-free options and avoid pressure to drink.",
        ],
        "avoid": [
            "Over-boozy formats, large pours or drinking games.",
            "Technical sessions that alienate beginners.",
            "Ignoring dietary, accessibility and alcohol-free needs.",
        ],
        "checklist": [
            "Choose fun, educational or client-safe tone before contacting suppliers.",
            "Confirm attendee count, budget and format.",
            "Ask about alcohol-free alternatives and food pairing.",
            "Share clear internal invite copy with timing and expectations.",
        ],
        "faqs": [
            {"q": "Are wine tastings good team-building events?", "a": "They can be, if the format is inclusive, beginner-friendly and not centred on drinking volume."},
            {"q": "How much does a corporate wine tasting cost?", "a": "Plan around £25-£60 per head for many hosted formats, with premium in-person events costing more."},
        ],
        "cta": "Plan a team tasting",
        "cta_url": "/event-planner",
        "related": ["virtual-wine-tasting-for-teams", "corporate-wine-tasting-london", "staff-wine-gifts"],
        "affiliate": False,
    },
}


GUIDES.update(
    {
        "corporate-wine-gifts-under-50": {
            "title": "Corporate Wine Gifts Under £50",
            "description": "Plan corporate wine gifts under £50 per person with sensible supplier routes, budget caveats and policy checks.",
            "h1": "Corporate wine gifts under £50 per person",
            "intro": "A £50 per person budget can produce a polished corporate wine gift if you keep the brief focused and leave room for VAT, delivery and substitutions.",
            "audience": [
                "Sales and account teams sending client thank-yous.",
                "Office managers planning seasonal staff gifts.",
                "Businesses that need a credible gift without a luxury budget.",
            ],
            "budget": [
                "£25-£35: single bottle, compact sparkling option or modest wine-plus-snack route.",
                "£35-£50: better presentation, classic red/white pair, English sparkling alternative or small hamper.",
                "Confirm whether prices include VAT, delivery, gift notes and packaging before comparing suppliers.",
            ],
            "approaches": [
                "Ask wine merchants for broad-appeal options rather than obscure bottles.",
                "Use hampers where mixed preferences or presentation matter.",
                "Keep alcohol-free alternatives in scope for employees and unknown recipients.",
            ],
            "avoid": [
                "Spending the full £50 on product before delivery and VAT are confirmed.",
                "Assuming bulk orders qualify for the same price as a single website listing.",
                "Choosing novelty packaging that delays fulfilment.",
            ],
            "checklist": [
                "Confirm recipient count, delivery deadline and budget owner.",
                "Ask for two or three options within budget including delivery and VAT.",
                "Request substitution policy, failed-delivery handling and gift note options.",
                "Check workplace gifting and anti-bribery limits.",
            ],
            "faqs": [
                {"q": "Is £50 enough for a corporate wine gift?", "a": "Yes, for many UK business gifts. The safest route is usually a classic bottle, sparkling alternative or compact hamper with delivery costs confirmed."}
            ],
            "cta": "Plan gifts under £50",
            "cta_url": "/gift-planner",
            "related": ["corporate-wine-gifts-under-100", "corporate-wine-gifts-uk", "corporate-wine-hampers"],
            "affiliate": True,
        },
        "corporate-wine-gifts-under-100": {
            "title": "Corporate Wine Gifts Under £100",
            "description": "A practical guide to corporate wine gifts under £100 per person, including premium routes, supplier questions and delivery checks.",
            "h1": "Corporate wine gifts under £100 per person",
            "intro": "A budget up to £100 per recipient gives you more room for polished presentation, stronger supplier service and premium-but-appropriate choices.",
            "audience": [
                "Client teams planning priority account gifts.",
                "Founders thanking partners or referrers.",
                "Marketing and operations teams comparing premium hampers, Champagne and fine wine merchant routes.",
            ],
            "budget": [
                "£50-£75: strong corporate range for English sparkling, premium hampers or classic mixed wine gifts.",
                "£75-£100: Champagne route, fine wine merchant gift, larger hamper or presentation-led option.",
                "Keep a reserve for VAT, delivery, branded inserts and failed-delivery handling.",
            ],
            "approaches": [
                "Use tiering: reserve higher budgets for priority relationships while keeping policy limits visible.",
                "Ask suppliers for a premium option and a fallback option in case stock changes.",
                "Consider English sparkling or hampers when Champagne feels too obvious.",
            ],
            "avoid": [
                "Sending a gift that feels excessive for the relationship or policy context.",
                "Choosing highly specialist wine unless the recipient's taste is known.",
                "Skipping internal approval for higher-value client gifts.",
            ],
            "checklist": [
                "Confirm gifting limits and procurement approval route.",
                "Ask suppliers for itemised quotes and delivery assumptions.",
                "Prepare a recipient CSV with messages and delivery notes.",
                "Record gift values for internal compliance.",
            ],
            "faqs": [
                {"q": "What should be included in a £100 client wine gift?", "a": "Common routes include Champagne or English sparkling, a polished hamper, a premium red/white pair or a fine wine merchant selection. Confirm fit and policy before ordering."}
            ],
            "cta": "Plan premium corporate gifts",
            "cta_url": "/gift-planner",
            "related": ["luxury-wine-gifts-for-clients", "champagne-gifts-for-clients", "client-gift-policy-checklist"],
            "affiliate": True,
        },
        "luxury-wine-gifts-for-clients": {
            "title": "Luxury Wine Gifts for Clients",
            "description": "Plan luxury wine gifts for clients without overclaiming, overstepping policy or relying on unverified supplier availability.",
            "h1": "Luxury wine gifts for clients",
            "intro": "Luxury client wine gifts need careful judgement. The gift should feel appropriate, well presented and easy to justify internally, not excessive or awkward.",
            "audience": [
                "Senior account teams thanking priority clients.",
                "Professional services firms arranging partner or referrer gifts.",
                "Founders sending high-touch thank-yous to investors or strategic partners.",
            ],
            "budget": [
                "£75-£150: premium sparkling, fine wine merchant route or high-quality hamper.",
                "£150+: specialist fine wine, Champagne or tailored merchant selection where policy allows.",
                "Always confirm VAT, delivery, age verification and insurance for higher-value shipments.",
            ],
            "approaches": [
                "Use a fine wine merchant or premium gift supplier that understands corporate fulfilment.",
                "Ask for restrained presentation rather than flashy branding.",
                "Prepare an internal approval note before ordering higher-value gifts.",
            ],
            "avoid": [
                "Assuming expensive always means more appropriate.",
                "Sending alcohol to recipients whose policy may prohibit it.",
                "Using language that implies a gift is intended to influence a decision.",
            ],
            "checklist": [
                "Check gift value thresholds and anti-bribery policy.",
                "Request itemised supplier quote and substitution rules.",
                "Confirm recipient suitability and alcohol-free alternatives.",
                "Keep a clear record of the business reason and recipient list.",
            ],
            "faqs": [
                {"q": "Are luxury wine gifts suitable for clients?", "a": "Sometimes, but only where relationship, policy and recipient suitability support it. A restrained, well-documented approach is safer than a flashy one."}
            ],
            "cta": "Plan luxury client gifts",
            "cta_url": "/gift-planner",
            "related": ["corporate-wine-gifts-under-100", "client-gift-policy-checklist", "client-thank-you-wine-gifts"],
            "affiliate": True,
        },
        "english-sparkling-corporate-gifts": {
            "title": "English Sparkling Corporate Gifts",
            "description": "Use English sparkling wine as a polished UK corporate gift route, with budget bands, supplier questions and suitability reminders.",
            "h1": "English sparkling wine corporate gifts",
            "intro": "English sparkling wine can be a strong UK-focused alternative to Champagne for client gifts, staff gifts and celebration moments where alcohol is appropriate.",
            "audience": [
                "Teams looking for a UK business gifting angle.",
                "Client gift buyers comparing sparkling options.",
                "Event planners pairing tasting packs with a hosted session.",
            ],
            "budget": [
                "£30-£45: practical entry point for many English sparkling gift routes.",
                "£45-£75: stronger presentation, gift packaging or hamper pairing.",
                "£75+: premium sparkling hamper or merchant-led selection.",
            ],
            "approaches": [
                "Use English sparkling where the UK provenance is relevant to the business relationship.",
                "Ask suppliers for gift notes, packaging and bulk delivery support.",
                "Compare with Champagne, Crémant-style alternatives and alcohol-free sparkling options.",
            ],
            "avoid": [
                "Claiming it is a guaranteed better choice than Champagne.",
                "Ignoring recipients who do not drink alcohol.",
                "Assuming all producers can handle corporate bulk delivery.",
            ],
            "checklist": [
                "Confirm minimum order quantities and delivery coverage.",
                "Ask about current vintage, substitutions and presentation.",
                "Prepare recipient data in the supplier's preferred format.",
                "Include alcohol-free sparkling alternatives where appropriate.",
            ],
            "faqs": [
                {"q": "Is English sparkling suitable for corporate gifting?", "a": "It can be a polished option, especially when a UK-focused gift feels appropriate. Suppliers must still confirm availability and delivery."}
            ],
            "cta": "Plan sparkling wine gifts",
            "cta_url": "/gift-planner",
            "related": ["champagne-gifts-for-clients", "corporate-wine-gifts-uk", "corporate-wine-gifts-under-50"],
            "affiliate": True,
        },
        "wine-gifts-for-sales-teams": {
            "title": "Wine Gifts for Sales Teams",
            "description": "A practical guide for sales teams sending client wine gifts with approval, budget and supplier briefing in mind.",
            "h1": "Wine gifts for sales teams to send clients",
            "intro": "Sales teams often need repeatable gift routes: clear budget bands, consistent messages, recipient data control and enough policy awareness to avoid awkward moments.",
            "audience": [
                "Sales teams sending post-renewal or end-of-year client gifts.",
                "Account managers thanking key contacts after projects.",
                "Revenue leaders setting a consistent gifting process.",
            ],
            "budget": [
                "£25-£50: useful for broad client thank-you gifting at scale.",
                "£50-£100: stronger route for priority accounts where policy allows.",
                "Use tiering carefully and document why recipients sit in each band.",
            ],
            "approaches": [
                "Create a small approved menu of gift routes rather than each salesperson improvising.",
                "Use neutral, appreciative message copy without sales pressure.",
                "Ask suppliers for repeatable CSV ordering and delivery reporting.",
            ],
            "avoid": [
                "Sending gifts without checking client acceptance rules.",
                "Using gifts as leverage around negotiations or renewals.",
                "Letting inconsistent messages or budgets create internal risk.",
            ],
            "checklist": [
                "Agree recipient tiers and budget bands.",
                "Collect addresses securely and confirm consent where needed.",
                "Ask suppliers for delivery reports and failed-delivery process.",
                "Keep a record for finance and compliance.",
            ],
            "faqs": [
                {"q": "Should sales teams send wine gifts?", "a": "They can where appropriate, but the process should be policy-aware, documented and inclusive of non-alcohol options."}
            ],
            "cta": "Plan client gifts",
            "cta_url": "/gift-planner",
            "related": ["client-thank-you-wine-gifts", "client-gift-policy-checklist", "corporate-gifting-recipient-csv-template"],
            "affiliate": True,
        },
        "wine-gifts-for-agencies": {
            "title": "Corporate Wine Gifts for Agencies",
            "description": "Plan corporate wine gifts for agencies sending client thank-yous, festive gifts or project completion gifts.",
            "h1": "Corporate wine gifts for agencies",
            "intro": "Agencies often need gifts that feel creative but still client-safe. The best route is polished, practical and easy for account teams to brief.",
            "audience": [
                "Creative, media, digital and PR agencies thanking clients.",
                "Account teams sending project completion gifts.",
                "Agency founders planning partner or referral thank-yous.",
            ],
            "budget": [
                "£25-£50: practical thank-you bottle, compact hamper or sparkling alternative.",
                "£50-£100: stronger presentation or client-tiered gifting.",
                "Allow extra time and budget for branded inserts if needed.",
            ],
            "approaches": [
                "Use gift notes that thank the client for the project or partnership without sounding promotional.",
                "Choose presentation-led hampers or sparkling routes for broad appeal.",
                "Keep a simple approval process for account teams.",
            ],
            "avoid": [
                "Overly quirky bottles that reflect agency taste more than recipient fit.",
                "Branded packaging that delays fulfilment beyond the deadline.",
                "Assuming every client contact can accept alcohol.",
            ],
            "checklist": [
                "Confirm client list, messages and budget owner.",
                "Ask suppliers about gift notes, branding, substitutions and delivery reports.",
                "Check client gift policies for public sector or regulated clients.",
                "Offer alcohol-free alternatives where appropriate.",
            ],
            "faqs": [
                {"q": "What wine gifts work well for agencies?", "a": "Sparkling, classic wine hampers and polished gift boxes usually work better than risky novelty choices."}
            ],
            "cta": "Plan agency wine gifts",
            "cta_url": "/gift-planner",
            "related": ["wine-gifts-for-sales-teams", "client-thank-you-wine-gifts", "christmas-wine-gifts-for-clients"],
            "affiliate": True,
        },
        "wine-gifts-for-law-firms": {
            "title": "Corporate Wine Gifts for Law Firms",
            "description": "Plan professional, policy-aware wine gifts for law firms and legal services businesses.",
            "h1": "Corporate wine gifts for law firms",
            "intro": "Law firm gifting should be restrained, professional and easy to document. Policy, conflicts and client suitability matter as much as the bottle.",
            "audience": [
                "Legal marketing and business development teams.",
                "Partners thanking referrers, clients or intermediaries.",
                "Operations teams arranging festive gifting with compliance awareness.",
            ],
            "budget": [
                "£40-£75: polished but controlled range for many professional services gifts.",
                "£75-£150: priority relationships where policy allows and approval is documented.",
                "Confirm VAT, delivery and acceptance limits before shortlisting.",
            ],
            "approaches": [
                "Use classic, conservative gift styles and restrained messages.",
                "Prepare an internal approval summary with recipient, value and business reason.",
                "Consider hampers or alcohol-free alternatives for uncertain recipients.",
            ],
            "avoid": [
                "Extravagant gifts that could create perception or compliance concerns.",
                "Sending gifts connected to active decisions or sensitive matters.",
                "Skipping conflict, bribery or procurement checks.",
            ],
            "checklist": [
                "Check firm and client gifting policy.",
                "Record gift value, recipient and reason.",
                "Ask suppliers for itemised quotes and proof of delivery.",
                "Include alternatives for recipients who do not drink alcohol.",
            ],
            "faqs": [
                {"q": "Can law firms send client wine gifts?", "a": "Often yes, but they should be modest, policy-aware and documented. Client acceptance rules should be checked directly."}
            ],
            "cta": "Plan professional services gifts",
            "cta_url": "/gift-planner",
            "related": ["client-gift-policy-checklist", "luxury-wine-gifts-for-clients", "corporate-wine-gifts-uk"],
            "affiliate": True,
        },
        "wine-gifts-for-accountancy-firms": {
            "title": "Corporate Wine Gifts for Accountancy Firms",
            "description": "A practical guide to corporate wine gifts for accountancy firms, including client tiers, policy checks and supplier briefs.",
            "h1": "Corporate wine gifts for accountancy firms",
            "intro": "Accountancy firm gifting works best when it is predictable, appropriate and easy for finance or practice management to approve.",
            "audience": [
                "Accountancy practices sending year-end client gifts.",
                "Partners thanking referrers or long-term clients.",
                "Practice managers coordinating bulk festive gifting.",
            ],
            "budget": [
                "£25-£50: scalable route for broad client lists.",
                "£50-£100: stronger option for priority clients and referrers.",
                "Use clear tiering and keep records for internal review.",
            ],
            "approaches": [
                "Build a repeatable supplier brief for annual gifting.",
                "Use classic styles, hampers or English sparkling for broad appeal.",
                "Ask for clean invoices, VAT clarity and delivery reporting.",
            ],
            "avoid": [
                "Unclear recipient lists that lead to duplicate or missed deliveries.",
                "Leaving address collection until December.",
                "Overlooking client gift acceptance policies.",
            ],
            "checklist": [
                "Confirm client tiers and approval thresholds.",
                "Prepare recipient CSV and gift messages.",
                "Ask suppliers about VAT, delivery charges and failed deliveries.",
                "Include alcohol-free or non-wine alternatives.",
            ],
            "faqs": [
                {"q": "What wine gifts suit accountancy clients?", "a": "Classic wine gifts, sparkling routes and compact hampers are usually safer than niche bottles. Confirm policy and suitability first."}
            ],
            "cta": "Plan accountancy client gifts",
            "cta_url": "/gift-planner",
            "related": ["corporate-gifting-recipient-csv-template", "client-gift-policy-checklist", "christmas-wine-gifts-for-clients"],
            "affiliate": True,
        },
        "client-gift-policy-checklist": {
            "title": "Client Gift Policy Checklist",
            "description": "Use this client gift policy checklist before sending corporate wine gifts, hampers or tasting invitations.",
            "h1": "Client gift policy checklist",
            "intro": "Before ordering wine gifts or event invitations, check the policy context. A small amount of preparation can prevent awkward acceptance, bribery or procurement issues.",
            "audience": [
                "Sales, marketing and operations teams sending client gifts.",
                "Professional services firms with regulated or public sector clients.",
                "Teams preparing an internal approval note for gift spend.",
            ],
            "budget": [
                "Set a maximum gift value per recipient before choosing suppliers.",
                "Check whether VAT, delivery and packaging count towards the internal limit.",
                "Higher-value gifts should have a clearer business reason and approval trail.",
            ],
            "approaches": [
                "Ask whether the recipient organisation publishes gift acceptance rules.",
                "Record recipient, company, value, occasion and business reason.",
                "Offer non-alcohol alternatives for recipient suitability and inclusion.",
            ],
            "avoid": [
                "Sending gifts around procurement, renewal or decision points without review.",
                "Using language that implies the gift is designed to influence business.",
                "Treating alcohol as the default where suitability is unknown.",
            ],
            "checklist": [
                "Confirm your organisation's gifting, anti-bribery and expenses policies.",
                "Check client acceptance limits and disclosure requirements.",
                "Confirm recipient suitability and alcohol-free alternatives.",
                "Record item value, delivery cost, VAT and supplier details.",
                "Keep approval notes with the order record.",
            ],
            "faqs": [
                {"q": "Is this legal advice?", "a": "No. This is a practical planning checklist. Use your own legal, procurement or compliance guidance where required."}
            ],
            "cta": "Create a policy-aware gift plan",
            "cta_url": "/gift-planner",
            "related": ["corporate-gifting-recipient-csv-template", "wine-gifts-for-law-firms", "corporate-wine-gifts-uk"],
            "affiliate": False,
        },
        "corporate-gifting-recipient-csv-template": {
            "title": "Corporate Gifting Recipient CSV Template",
            "description": "Plan the recipient data needed for corporate wine gifts, including addresses, messages, delivery notes and suitability fields.",
            "h1": "Corporate gifting recipient CSV template",
            "intro": "Clean recipient data is one of the biggest differences between a smooth corporate gift order and a messy one. Prepare the CSV before asking suppliers for final quotes.",
            "audience": [
                "Operations teams coordinating bulk gift delivery.",
                "Sales teams preparing client recipient lists.",
                "HR teams sending staff gifts with alternative options.",
            ],
            "budget": [
                "A CSV does not set budget, but it helps suppliers price delivery, packaging and substitutions accurately.",
                "Separate recipient tiers if different budget bands apply.",
                "Include notes for alcohol-free alternatives so supplier quotes are realistic.",
            ],
            "approaches": [
                "Use columns for name, email, company, address lines, city, postcode, country, gift message and notes.",
                "Add optional fields for tier, alcohol-free preference, delivery deadline and internal owner.",
                "Ask suppliers which fields they require before finalising the upload.",
            ],
            "avoid": [
                "Collecting more personal data than needed.",
                "Mixing unconfirmed addresses with final addresses.",
                "Sending spreadsheets without access control or privacy checks.",
            ],
            "checklist": [
                "Confirm recipient consent or appropriate business basis for delivery data.",
                "Validate postcodes and delivery countries.",
                "Mark VIP, policy-sensitive or alcohol-free recipients clearly.",
                "Confirm failed-delivery reporting with the supplier.",
                "Delete or archive data according to your internal privacy process.",
            ],
            "faqs": [
                {"q": "What fields should a recipient CSV include?", "a": "Start with recipient name, company, email, address, postcode, country, gift message and notes. Add tier, deadline and alcohol-free preference where useful."}
            ],
            "cta": "Create a gift plan",
            "cta_url": "/gift-planner",
            "related": ["client-gift-policy-checklist", "wine-gifts-for-sales-teams", "corporate-wine-gifts-uk"],
            "affiliate": False,
        },
    }
)


PUBLISHER_DISCLOSURE = (
    "ClientCellar may earn a commission if you buy through links on this page. "
    "Our recommendations are written to help buyers choose suitable client gifts, "
    "not to favour any one retailer."
)

DEFAULT_MERCHANT_LINKS = [
    {
        "name": "Majestic Wine",
        "url": configured_supplier_url("majestic"),
        "note": "Corporate gifting page for client and staff wine gift enquiries.",
        "url_purpose": "Corporate gifting page",
        "url_checked_date": "2026-05-10",
        "is_affiliate": bool(configured_supplier_affiliate_url("majestic")),
    },
    {
        "name": "Berry Bros. & Rudd",
        "url": configured_supplier_url("berry-bros-rudd"),
        "note": "Fine wines range worth considering for premium client gifts, Champagne and formal gifting.",
        "url_purpose": "Fine wines range page",
        "url_checked_date": "2026-05-10",
        "is_affiliate": bool(configured_supplier_affiliate_url("berry-bros-rudd")),
    },
    {
        "name": "Fortnum & Mason",
        "url": configured_supplier_url("fortnum-mason"),
        "note": "Hampers page for presentation-led premium food and drink gifting.",
        "url_purpose": "Hampers page",
        "url_checked_date": "2026-05-10",
        "is_affiliate": bool(configured_supplier_affiliate_url("fortnum-mason")),
    },
]


def publisher_guide(
    title: str,
    h1: str,
    description: str,
    intro: str,
    audience: list[str],
    budget: list[str],
    best_for: list[str],
    approaches: list[str],
    considerations: list[str],
    avoid: list[str],
    checklist: list[str],
    faqs: list[dict],
    related: list[str],
    merchant_links: list[dict] | None = None,
) -> dict:
    return {
        "title": title,
        "h1": h1,
        "description": description,
        "intro": intro,
        "audience": audience,
        "budget": budget,
        "best_for": best_for,
        "approaches": approaches,
        "considerations": considerations,
        "avoid": avoid,
        "checklist": checklist,
        "faqs": faqs,
        "cta": "Plan corporate gifts",
        "cta_url": "/gift-planner",
        "related": related,
        "affiliate": True,
        "affiliate_disclosure": PUBLISHER_DISCLOSURE,
        "merchant_links": merchant_links or DEFAULT_MERCHANT_LINKS,
    }


GUIDES.update(
    {
        "best-client-wine-gifts": publisher_guide(
            "Best Client Wine Gifts",
            "Best client wine gifts",
            "Practical client wine gift ideas for UK businesses, with budget bands, suitability checks and supplier questions.",
            "This guide helps sales, account and founder teams choose client wine gifts that feel useful, appropriate and easy to brief without pretending any retailer has guaranteed stock or pricing.",
            ["Account managers sending thank-yous.", "Founders thanking strategic partners.", "Marketing teams planning seasonal client gifts."],
            ["£20-£40: classic single bottle, sparkling alternative or compact hamper.", "£40-£75: polished gift box, English sparkling or wine-and-food route.", "£75-£150+: premium merchant, Champagne or presentation-led hamper where policy allows."],
            ["Project completion gifts.", "Christmas thank-yous.", "Renewal or referral acknowledgements where gifts are policy-appropriate."],
            ["Choose broad-appeal styles: sparkling, classic red/white pairs or wine hampers.", "Keep messages warm and professional.", "Ask suppliers for gift notes, VAT, delivery and substitutions in one quote."],
            ["Recipient gift policy.", "Alcohol suitability and alternatives.", "Delivery address quality.", "Whether the gift value needs internal approval."],
            ["Flashy gifts that feel like inducements.", "Niche bottles unless you know the recipient's taste.", "Sending alcohol where the recipient may not accept it."],
            ["Confirm budget and recipient count.", "Shortlist two or three supplier routes.", "Ask about delivery, VAT and substitutions.", "Prepare a recipient CSV before ordering."],
            [{"q": "What is a safe client wine gift?", "a": "A classic sparkling, red/white pair or modest wine hamper is usually safer than a highly niche bottle."}],
            ["corporate-wine-gifts-uk", "client-gift-policy-checklist", "corporate-gifting-recipient-csv-template"],
        ),
        "corporate-wine-gifts-uk": publisher_guide(
            "Corporate Wine Gifts UK",
            "Corporate wine gifts for UK businesses",
            "A UK-focused guide to corporate wine gifts, including budgets, supplier routes, delivery and workplace suitability.",
            "Corporate wine gifts work best when the brief is practical: clear budget, suitable recipients, reliable delivery and supplier-ready instructions.",
            ["UK businesses sending client, staff or partner gifts.", "Office managers arranging bulk delivery.", "Teams comparing wine, hampers and sparkling routes."],
            ["Under £25: simple wine or non-alcoholic alternative.", "£25-£50: useful corporate gifting range for many recipients.", "£50-£100+: premium hamper, Champagne, English sparkling or fine wine route."],
            ["Client appreciation.", "Staff recognition where alcohol is appropriate.", "Partner and supplier thank-yous."],
            ["Use tiered budgets for different recipient groups.", "Ask for corporate ordering support and delivery reporting.", "Include alcohol-free alternatives for mixed recipient lists."],
            ["Procurement and anti-bribery policy.", "Recipient suitability.", "Age verification and failed delivery handling.", "Supplier minimum order quantities."],
            ["Assuming live website stock applies to bulk orders.", "Skipping gift acceptance checks.", "Over-personal messages for business contacts."],
            ["Define recipient groups.", "Confirm deadline.", "Ask suppliers for itemised quotes.", "Keep a record of gift value and business reason."],
            [{"q": "Do corporate wine gifts need approval?", "a": "Often they should be checked against internal gifting, expenses and anti-bribery policies before ordering."}],
            ["best-client-wine-gifts", "corporate-wine-gifts-under-50", "client-gift-policy-checklist"],
        ),
        "best-wine-gifts-under-25": publisher_guide(
            "Best Wine Gifts Under £25",
            "Best wine gifts under £25",
            "Budget-conscious wine gift ideas under £25 for client thank-yous, staff gifts and modest business gestures.",
            "A budget under £25 can still work for simple corporate gifting if you keep delivery, VAT and presentation expectations realistic.",
            ["Teams sending higher-volume modest gifts.", "Staff thank-you organisers.", "Small businesses needing a low-risk gesture."],
            ["£10-£15: consider alcohol-free options, mini formats or simple bottles.", "£15-£25: better single bottle, compact gift sleeve or small food pairing.", "Delivery may push the all-in cost above £25."],
            ["Low-value thank-yous.", "Internal team gifts.", "Add-ons to cards or small hampers."],
            ["Ask suppliers for case pricing.", "Keep packaging simple.", "Consider vouchers or non-alcoholic gifts if delivery makes wine uneconomical."],
            ["Delivery cost may dominate the budget.", "Presentation may be basic.", "Recipient suitability still matters."],
            ["Pretending a low budget is a luxury gift.", "Choosing novelty labels over broad appeal.", "Ignoring alcohol-free alternatives."],
            ["Set an all-in budget.", "Ask whether VAT and delivery are included.", "Choose simple classic styles.", "Keep gift notes short."],
            [{"q": "Can you send a decent wine gift under £25?", "a": "Yes, but it is usually a simple single-bottle route and delivery costs must be checked carefully."}],
            ["best-wine-gifts-under-50", "staff-wine-gifts", "non-alcoholic-client-gifts"],
        ),
        "best-wine-gifts-under-50": publisher_guide(
            "Best Wine Gifts Under £50",
            "Best wine gifts under £50",
            "Wine gifts under £50 for UK business buyers, with sensible options for clients, staff and partners.",
            "The under-£50 range is one of the most useful corporate gifting bands because it can cover a polished bottle, sparkling option or compact hamper.",
            ["Client service teams.", "Office managers.", "Founders sending thoughtful thank-yous."],
            ["£25-£35: classic single bottle or sparkling alternative.", "£35-£50: stronger presentation, wine-and-food option or English sparkling.", "Confirm delivery and VAT before comparing."],
            ["Client thank-yous.", "Festive gifting.", "Staff recognition with alternatives."],
            ["Choose classic styles over experimental bottles.", "Use hampers for mixed tastes.", "Ask for alcohol-free substitutes."],
            ["Supplier delivery coverage.", "Gift acceptance policies.", "Minimum order quantities.", "Whether branding delays fulfilment."],
            ["Using the full budget before delivery is included.", "Assuming all recipients drink alcohol.", "Leaving address collection too late."],
            ["Collect recipient count.", "Request two options within budget.", "Ask about substitutions.", "Prepare message copy."],
            [{"q": "What is the best wine gift under £50?", "a": "For business gifting, a classic sparkling, red/white pair or compact hamper is often worth considering."}],
            ["corporate-wine-gifts-under-50", "best-client-wine-gifts", "food-and-wine-hampers"],
        ),
        "best-wine-gifts-under-100": publisher_guide(
            "Best Wine Gifts Under £100",
            "Best wine gifts under £100",
            "Premium-but-practical wine gift ideas under £100 for clients, partners and senior business contacts.",
            "Under £100 gives buyers room for stronger presentation and higher-quality supplier service, but the gift still needs to feel proportionate and policy-safe.",
            ["Priority client gifting.", "Partner thank-yous.", "Senior stakeholder gifts where approval is clear."],
            ["£50-£75: English sparkling, premium hamper or classic mixed gift.", "£75-£100: Champagne route, fine wine merchant or presentation-led hamper.", "Keep approval records for higher values."],
            ["Priority accounts.", "Milestone thank-yous.", "Executive gifts where appropriate."],
            ["Ask suppliers for premium and fallback options.", "Compare Champagne, English sparkling and hamper routes.", "Keep presentation restrained."],
            ["Anti-bribery policy.", "Recipient acceptance limits.", "Insurance or tracking for higher-value delivery.", "Substitution policy."],
            ["Gifts that feel excessive.", "Highly specialist bottles without taste knowledge.", "Unclear business reason."],
            ["Check policy limits.", "Get itemised quote.", "Confirm delivery tracking.", "Record value and recipient."],
            [{"q": "Is £100 too much for a client wine gift?", "a": "It depends on the relationship and policy context. Higher-value gifts should be approved and documented."}],
            ["corporate-wine-gifts-under-100", "luxury-wine-gifts-for-clients", "client-gift-policy-checklist"],
        ),
        "champagne-gifts-for-clients": publisher_guide(
            "Champagne Gifts for Clients",
            "Champagne gifts for clients",
            "How to choose Champagne gifts for clients without overstepping budget, policy or recipient suitability.",
            "Champagne can be a polished client gift, but it is not always the safest or best-value option. This guide helps compare Champagne with sparkling alternatives.",
            ["Teams marking milestones.", "Client entertainment follow-ups.", "Priority account gifting."],
            ["£40-£60: entry Champagne or strong sparkling alternative.", "£60-£100: gift-boxed Champagne or premium English sparkling.", "£100+: Champagne hamper or fine wine merchant option."],
            ["Celebrations.", "Deal completions where gifting is appropriate.", "Festive client gifts."],
            ["Compare Champagne with English sparkling.", "Ask about gift boxes and delivery.", "Keep messages understated."],
            ["Whether Champagne feels too showy.", "Recipient alcohol suitability.", "Company gift limits.", "Stock and vintage substitutions."],
            ["Buying for status alone.", "Ignoring sparkling alternatives.", "Assuming all clients can accept alcohol."],
            ["Confirm policy.", "Ask for options at two budgets.", "Check presentation and delivery.", "Include alcohol-free alternative if needed."],
            [{"q": "Is Champagne a good client gift?", "a": "It can be, especially for celebratory moments, but English sparkling or a hamper may be more suitable in some contexts."}],
            ["english-sparkling-corporate-gifts", "best-wine-gifts-under-100", "luxury-wine-gifts-for-clients"],
        ),
        "red-wine-gifts-for-clients": publisher_guide(
            "Red Wine Gifts for Clients",
            "Red wine gifts for clients",
            "Practical guidance on choosing red wine gifts for clients, including styles, budgets and suitability checks.",
            "Red wine can be a classic corporate gift, but it works best when you choose broad-appeal styles and avoid assuming specialist tastes.",
            ["Client thank-yous.", "Professional services gifting.", "Food-and-wine hamper buyers."],
            ["£20-£40: classic Rioja, Bordeaux-style blend or Italian red route.", "£40-£75: better presentation or red-and-food hamper.", "£75+: fine wine merchant selection where taste is known."],
            ["Recipients known to enjoy red wine.", "Wine-and-food hampers.", "Autumn and winter gifting."],
            ["Choose recognised, balanced styles.", "Pair with food if tastes are uncertain.", "Ask suppliers for drink-now bottles rather than cellar-only choices."],
            ["Taste preference.", "Storage and delivery conditions.", "Whether a mixed gift would be safer.", "Alcohol-free alternatives."],
            ["Very tannic or obscure bottles for unknown recipients.", "Overstating rarity or investment value.", "Sending red wine where preferences are unknown."],
            ["Ask for broad-appeal options.", "Confirm gift packaging.", "Include gift note.", "Check delivery timings."],
            [{"q": "What red wine works for client gifts?", "a": "Classic, recognisable and drinkable styles are usually safer than niche or highly technical bottles."}],
            ["best-client-wine-gifts", "food-and-wine-hampers", "client-gifting-etiquette-uk"],
        ),
        "white-wine-gifts-for-clients": publisher_guide(
            "White Wine Gifts for Clients",
            "White wine gifts for clients",
            "How to choose white wine gifts for clients, including safer styles, budgets and when to choose sparkling instead.",
            "White wine gifts can feel lighter and food-friendly, especially when you choose classic styles or pair them with a hamper.",
            ["Spring and summer client gifts.", "Food hamper buyers.", "Recipients known to prefer white wine."],
            ["£15-£30: classic Sauvignon Blanc, Chardonnay or European white route.", "£30-£60: stronger single bottle, pair or presentation box.", "£60+: premium white wine or mixed hamper."],
            ["Warm-weather gifting.", "Food pairings.", "Lower-key thank-yous."],
            ["Choose recognisable regions or styles.", "Consider sparkling if celebration is the main point.", "Ask about chilled delivery only if relevant."],
            ["Recipient taste.", "Delivery timing.", "Food pairing if included.", "Whether mixed red/white is safer."],
            ["Overly sweet or niche styles unless requested.", "Assuming white wine suits every recipient.", "Ignoring alcohol-free alternatives."],
            ["Confirm style preferences if known.", "Ask suppliers for two options.", "Check packaging.", "Include delivery notes."],
            [{"q": "Is white wine suitable for corporate gifts?", "a": "Yes, where the recipient is likely to enjoy it. For unknown tastes, sparkling or hampers may be safer."}],
            ["best-client-wine-gifts", "food-and-wine-hampers", "champagne-gifts-for-clients"],
        ),
        "luxury-wine-hampers-uk": publisher_guide(
            "Luxury Wine Hampers UK",
            "Luxury wine hampers in the UK",
            "A UK buyer guide to luxury wine hampers for clients, partners and senior business contacts.",
            "Luxury wine hampers can combine presentation, food and flexibility, but the best choice depends on policy, delivery and recipient suitability.",
            ["Priority client gifts.", "Executive thank-yous.", "Festive corporate gifting."],
            ["£50-£100: polished wine and food hamper.", "£100-£200: premium presentation and broader contents.", "£200+: luxury hamper where approval and recipient fit are clear."],
            ["High-touch client relationships.", "Recipients with mixed wine tastes.", "Presentation-led Christmas gifts."],
            ["Check contents, allergens and substitutions.", "Ask about branded notes and delivery reports.", "Compare alcohol and alcohol-free hamper options."],
            ["Perishable contents.", "Allergens.", "Delivery coverage.", "Gift acceptance limits."],
            ["Oversized hampers that are hard to deliver.", "Unclear substitution policy.", "Assuming bigger always means better."],
            ["Confirm all contents.", "Ask about failed deliveries.", "Prepare recipient data.", "Record gift value."],
            [{"q": "Are luxury hampers good client gifts?", "a": "They can be useful where presentation matters and policy allows, especially if supplier delivery is reliable."}],
            ["corporate-wine-hampers", "best-wine-gifts-under-100", "food-and-wine-hampers"],
        ),
        "wine-gifts-for-christmas": publisher_guide(
            "Wine Gifts for Christmas",
            "Wine gifts for Christmas",
            "Plan Christmas wine gifts for clients and staff with supplier lead times, budget bands and responsible gifting checks.",
            "Christmas wine gifting needs earlier planning because delivery slots, packaging, address data and substitutions become harder late in the year.",
            ["Client teams.", "HR and office managers.", "Founders sending festive thank-yous."],
            ["£20-£40: simple festive bottle or alcohol-free alternative.", "£40-£75: sparkling, hamper or red/white pair.", "£75+: premium hamper or Champagne route."],
            ["Bulk client gifts.", "Staff gifts with choice.", "Festive thank-you campaigns."],
            ["Start early.", "Ask suppliers for Christmas cut-offs.", "Use clear message templates.", "Keep alcohol-free alternatives visible."],
            ["Order deadlines.", "Recipient address data.", "Gift acceptance policies.", "Substitutions if festive stock changes."],
            ["Waiting until December.", "Assuming all addresses are current.", "Overly jokey packaging or messages."],
            ["Collect recipient CSV.", "Confirm final dispatch date.", "Ask for delivery report.", "Prepare fallback gifts."],
            [{"q": "When should businesses order Christmas wine gifts?", "a": "Start supplier conversations well before December, especially for bulk delivery or branded packaging."}],
            ["christmas-wine-gifts-for-clients", "wine-gifts-for-christmas", "corporate-gifting-recipient-csv-template"],
        ),
        "wine-gifts-for-thank-you": publisher_guide(
            "Wine Gifts for Thank You",
            "Wine gifts for thank-you moments",
            "Choose thank-you wine gifts for clients, referrers and partners without making the gesture feel excessive.",
            "Thank-you wine gifts should feel warm, proportionate and easy to accept. The message matters as much as the bottle.",
            ["Project completion gifts.", "Referral thank-yous.", "Partner appreciation."],
            ["£20-£40: modest bottle or compact hamper.", "£40-£75: polished gift box or sparkling route.", "£75+: premium route for high-value relationships with approval."],
            ["Project completion.", "Helpful referral.", "Long-term partnership milestone."],
            ["Keep the note short and specific.", "Use classic styles.", "Check whether the recipient can accept gifts."],
            ["Timing around procurement decisions.", "Gift value.", "Recipient suitability.", "Delivery address accuracy."],
            ["Language that sounds transactional.", "Overly expensive gestures.", "Alcohol as the only option."],
            ["Define reason for gift.", "Check policy.", "Choose supplier route.", "Write concise message."],
            [{"q": "What should a thank-you wine gift message say?", "a": "Keep it simple: thank the recipient for the project, referral or partnership without sales pressure."}],
            ["client-thank-you-wine-gifts", "best-client-wine-gifts", "client-gifting-etiquette-uk"],
        ),
        "wine-gifts-for-new-business": publisher_guide(
            "Wine Gifts for New Business",
            "Wine gifts for new business relationships",
            "How to approach wine gifts for new clients and partners while keeping compliance and tone in mind.",
            "Wine gifts around new business need caution. They should never feel like pressure or a reward for a decision.",
            ["Teams welcoming new clients after contracts are complete.", "Founders thanking new partners.", "Account teams starting onboarding."],
            ["£20-£50: modest welcome gift.", "£50-£100: polished gift where policy allows.", "Higher budgets should be approved and documented."],
            ["Post-signature welcome gifts.", "Partner onboarding.", "Celebrating completed work rather than influencing decisions."],
            ["Send after commercial decisions are complete.", "Use restrained wording.", "Keep a clear record of value and purpose."],
            ["Timing against procurement decisions.", "Anti-bribery policy.", "Recipient organisation rules.", "Whether non-alcohol is safer."],
            ["Sending during negotiations.", "Implying the gift is tied to future business.", "Extravagant presentation."],
            ["Check timing.", "Record business reason.", "Ask supplier for itemised quote.", "Offer alternative gift route."],
            [{"q": "Should you send wine gifts to new clients?", "a": "Only where policy and timing are appropriate. Avoid gifts during active procurement or decision-making."}],
            ["client-gift-policy-checklist", "wine-gifts-for-sales-teams", "best-client-wine-gifts"],
        ),
        "wine-gifts-for-events": publisher_guide(
            "Wine Gifts for Events",
            "Wine gifts for events",
            "Plan wine gifts for event attendees, speakers, hosts and clients with delivery and suitability checks.",
            "Event wine gifts can work as follow-ups, speaker thank-yous or tasting pack alternatives, but they need careful delivery and inclusion planning.",
            ["Event organisers.", "Marketing teams.", "Client hospitality teams."],
            ["£15-£30: simple attendee thank-you.", "£30-£60: better gift box or sparkling option.", "£60+: speaker or VIP gift where policy allows."],
            ["Speaker thank-yous.", "VIP attendee gifts.", "Post-event client follow-up."],
            ["Use event context in the note.", "Confirm attendee addresses securely.", "Offer alcohol-free alternatives."],
            ["GDPR and address handling.", "International delivery.", "Age verification.", "Event sponsor policy."],
            ["Bulk sending without consent.", "Alcohol-only gifts for mixed audiences.", "Late delivery after the event."],
            ["Confirm recipient list.", "Ask supplier for delivery reporting.", "Prepare message variants.", "Check alternatives."],
            [{"q": "Can wine gifts be sent after events?", "a": "Yes, where appropriate, but address handling, recipient suitability and gift policy should be checked first."}],
            ["wine-gifts-for-events", "virtual-wine-tasting-for-teams", "corporate-gifting-recipient-csv-template"],
        ),
        "best-wine-accessories-for-gifts": publisher_guide(
            "Best Wine Accessories for Gifts",
            "Best wine accessories for gifts",
            "Wine accessory gift ideas for clients and staff when alcohol itself may not be suitable.",
            "Wine accessories can be useful when you want a related gift without sending alcohol, or when recipient preferences are unknown.",
            ["Alcohol-sensitive workplaces.", "Recipients who enjoy wine but may prefer non-alcohol gifts.", "Add-ons to hampers."],
            ["Under £20: bottle stoppers, openers or simple accessories.", "£20-£50: decanters, glassware or gift sets.", "£50+: premium glassware or presentation-led accessories."],
            ["Non-alcohol gifting.", "Event follow-ups.", "Wine tasting accessories."],
            ["Choose practical items over gimmicks.", "Check delivery fragility.", "Consider branded notebooks or tasting cards for events."],
            ["Breakage risk.", "Whether the accessory assumes alcohol use.", "Recipient usefulness.", "Gift packaging."],
            ["Novelty accessories that feel cheap.", "Fragile items without protective delivery.", "Claims about improving wine quality unless supplier substantiates them."],
            ["Confirm budget.", "Ask about packaging.", "Check delivery method.", "Consider pairing with alcohol-free alternatives."],
            [{"q": "Are wine accessories good client gifts?", "a": "They can be, especially when alcohol is not suitable or you want a practical add-on."}],
            ["non-alcoholic-client-gifts", "wine-gifts-for-events", "client-gifting-etiquette-uk"],
        ),
        "how-much-to-spend-on-client-gifts": publisher_guide(
            "How Much to Spend on Client Gifts",
            "How much to spend on client gifts",
            "A practical UK guide to client gift budgets, including wine gift bands and policy checks.",
            "Client gift budgets should be proportionate, documented and suitable for the relationship. This guide gives planning bands rather than rules.",
            ["Sales leaders.", "Office managers.", "Finance and operations teams reviewing gift spend."],
            ["Under £25: modest thank-you.", "£25-£50: common corporate gifting range.", "£50-£100: priority client gift.", "£100+: approval strongly recommended."],
            ["Budget setting.", "Tiered client lists.", "Internal approval conversations."],
            ["Set tiers before selecting suppliers.", "Include VAT and delivery.", "Record reason and recipient."],
            ["Anti-bribery thresholds.", "Client policy.", "Tax and expenses handling.", "Recipient suitability."],
            ["Copying another company's budget without context.", "Ignoring delivery costs.", "Spending more to compensate for weak messaging."],
            ["Define tiers.", "Check internal policy.", "Build all-in budget.", "Prepare approval note."],
            [{"q": "What is a normal client gift budget?", "a": "Many businesses use £25-£75 for practical gifts, but the right budget depends on policy, relationship and occasion."}],
            ["client-gift-policy-checklist", "best-wine-gifts-under-50", "best-wine-gifts-under-100"],
        ),
        "client-gifting-etiquette-uk": publisher_guide(
            "Client Gifting Etiquette UK",
            "Client gifting etiquette in the UK",
            "UK client gifting etiquette for wine gifts, hampers and thank-you presents.",
            "Good client gifting is about suitability, timing and restraint. A well-chosen modest gift can be better than an expensive awkward one.",
            ["Professional services firms.", "Sales and account teams.", "Founders sending client thank-yous."],
            ["Modest gifts: under £40.", "Polished gifts: £40-£75.", "Higher-value gifts: policy approval recommended."],
            ["Thank-you gifts.", "Christmas gifting.", "Post-project appreciation."],
            ["Keep wording professional.", "Avoid gifts during sensitive commercial decisions.", "Offer alternatives where alcohol may not suit."],
            ["Bribery and procurement policies.", "Recipient religion, health or recovery context.", "Public sector restrictions.", "Timing."],
            ["Lavish gifts without approval.", "Over-familiar messages.", "Alcohol as the only option."],
            ["Check policy.", "Choose appropriate timing.", "Write simple note.", "Record value."],
            [{"q": "What is good client gifting etiquette?", "a": "Keep gifts proportionate, policy-aware and useful. Avoid pressure, excess and assumptions about alcohol."}],
            ["client-gift-policy-checklist", "wine-gifts-for-thank-you", "best-client-wine-gifts"],
        ),
        "food-and-wine-hampers": publisher_guide(
            "Food and Wine Hampers",
            "Food and wine hampers",
            "How to choose food and wine hampers for clients, staff and partners, including allergens, budgets and delivery.",
            "Food and wine hampers can work well when tastes are mixed because they offer more variety than a single bottle.",
            ["Client gift buyers.", "HR and office managers.", "Festive gifting planners."],
            ["£25-£50: compact food-and-wine option.", "£50-£100: stronger hamper range.", "£100+: luxury hamper where policy allows."],
            ["Mixed preferences.", "Christmas gifts.", "Presentation-led client thank-yous."],
            ["Ask about allergens.", "Check substitutions.", "Compare alcohol and alcohol-free hamper versions."],
            ["Perishables.", "Dietary requirements.", "Delivery timing.", "Recipient storage."],
            ["Ignoring allergies.", "Oversized hampers for office delivery.", "Assuming all contents are fixed."],
            ["Confirm contents.", "Ask about substitutions.", "Collect addresses.", "Prepare alternatives."],
            [{"q": "Are food and wine hampers safer than wine alone?", "a": "Often they are more flexible, but allergens, alcohol suitability and delivery still need checking."}],
            ["corporate-wine-hampers", "luxury-wine-hampers-uk", "non-alcoholic-client-gifts"],
        ),
        "non-alcoholic-client-gifts": publisher_guide(
            "Non-Alcoholic Client Gifts",
            "Non-alcoholic client gifts",
            "Client gift ideas and checks for situations where wine or alcohol may not be suitable.",
            "Non-alcoholic gifts are important for inclusive corporate gifting and can be the better choice where recipient preferences are unknown.",
            ["HR teams.", "Client teams with mixed recipient lists.", "Regulated or alcohol-sensitive workplaces."],
            ["Under £25: premium soft drinks, snacks or small accessories.", "£25-£50: alcohol-free hamper or food gift.", "£50+: luxury food hamper or personalised non-alcohol route."],
            ["Staff gifts.", "Unknown recipient preferences.", "Workplaces where alcohol is not appropriate."],
            ["Offer choice where possible.", "Use premium food, coffee, tea or alcohol-free sparkling routes.", "Make alternatives equal in quality."],
            ["Dietary needs.", "Religious and health considerations.", "Allergens.", "Delivery and shelf life."],
            ["Treating alternatives as an afterthought.", "Labelling that singles recipients out.", "Assuming non-alcohol gifts are less valued."],
            ["Ask suppliers for alcohol-free options.", "Collect preferences carefully.", "Check allergens.", "Match budgets fairly."],
            [{"q": "Should businesses offer non-alcoholic gifts?", "a": "Yes, especially for staff gifts, mixed groups and recipients whose preferences are unknown."}],
            ["staff-wine-gifts", "best-wine-accessories-for-gifts", "client-gifting-etiquette-uk"],
        ),
        "personalised-wine-gifts": publisher_guide(
            "Personalised Wine Gifts",
            "Personalised wine gifts",
            "A practical guide to personalised wine gifts for clients, including branding, notes and delivery timing.",
            "Personalisation can make a gift feel more considered, but it can also add lead time and create extra proofing risk.",
            ["Marketing teams.", "Agencies.", "Founders sending small batches of client gifts."],
            ["£25-£50: gift note or sleeve personalisation.", "£50-£100: branded insert, box or premium packaging.", "£100+: bespoke hamper or higher-touch supplier route."],
            ["Project completion gifts.", "Christmas campaigns.", "Small priority client lists."],
            ["Use tasteful gift notes before custom labels.", "Ask for proofing deadlines.", "Keep branding restrained."],
            ["Artwork lead time.", "Minimum order quantities.", "Client policy on branded gifts.", "Substitution process."],
            ["Novelty labels for formal clients.", "Rushing proof approval.", "Personalisation that delays delivery past the occasion."],
            ["Confirm branding requirements.", "Ask for proofs.", "Set approval deadline.", "Prepare fallback plain packaging."],
            [{"q": "Are personalised wine gifts good for clients?", "a": "They can be, if restrained and professionally executed. Gift notes are often safer than heavily branded bottles."}],
            ["wine-gifts-for-agencies", "best-client-wine-gifts", "corporate-gifting-recipient-csv-template"],
        ),
        "wine-gift-baskets-uk": publisher_guide(
            "Wine Gift Baskets UK",
            "Wine gift baskets in the UK",
            "UK wine gift basket buying guidance for corporate clients, staff and partner gifts.",
            "Wine gift baskets are similar to hampers but often more compact. They can work for business gifting when presentation and delivery are clear.",
            ["Client gifting.", "Staff thank-yous.", "Partner gifts with food pairings."],
            ["£25-£50: compact basket or wine-plus-snack option.", "£50-£100: stronger presentation and contents.", "£100+: premium basket where policy allows."],
            ["Festive gifts.", "Mixed preferences.", "Recipients who may appreciate food as well as wine."],
            ["Check basket contents and packaging.", "Ask whether alcohol-free versions exist.", "Compare with boxed hampers for delivery robustness."],
            ["Allergens.", "Breakage risk.", "Delivery coverage.", "Substitutions."],
            ["Fragile baskets without protective delivery.", "Unclear contents.", "Sending alcohol-only baskets to mixed recipient lists."],
            ["Confirm contents.", "Ask about delivery protection.", "Prepare recipient CSV.", "Check alternatives."],
            [{"q": "What is the difference between a wine basket and a hamper?", "a": "Baskets are often presentation-led and compact; hampers may be boxed and easier for courier delivery. Confirm packaging with suppliers."}],
            ["food-and-wine-hampers", "corporate-wine-hampers", "luxury-wine-hampers-uk"],
        ),
    }
)


SEO_PAGES = {
    "corporate-wine-gifts": {
        "title": "Corporate Wine Gifts",
        "h1": "Corporate wine gifts for UK businesses",
        "description": "Plan UK corporate wine gifts with budget guidance, supplier direction and enquiry-ready briefs for clients, staff and business events.",
        "intro": "Corporate wine gifts can work well when the brief is practical: clear budget, sensible recipient assumptions, reliable delivery and a supplier who can handle business ordering.",
        "sections": [
            ("When wine gifts work well", ["Client thank-yous after a project or renewal.", "Partner gifts where a polished but practical item is appropriate.", "Staff gifting where alcohol-free alternatives are also offered."]),
            ("Budget ranges", ["£20-£40 per recipient: simple bottle, half bottle, alcohol-free alternative or modest gift route.", "£40-£75 per recipient: stronger wine gift, small hamper or sparkling option.", "£75+ per recipient: premium wine merchant, Champagne route or presentation-led hamper."]),
            ("What to ask suppliers", ["Can you handle corporate ordering and bulk delivery?", "What recipient data format do you need?", "Are VAT, delivery, gift notes and substitutions included?", "What alcohol-free alternatives are available?"]),
            ("Delivery and compliance considerations", ["Confirm age verification and failed-delivery handling.", "Check company gifting, anti-bribery, HR and procurement policies.", "Do not assume every recipient drinks alcohol."]),
        ],
        "primary_cta": ("Use the gift planner", "/gift-planner"),
        "related": [("Supplier directory", "/suppliers"), ("Client wine gifts", "/client-wine-gifts"), ("Staff wine gifts", "/staff-wine-gifts")],
    },
    "corporate-wine-tasting-events": {
        "title": "Corporate Wine Tasting Events",
        "h1": "Corporate wine tasting events",
        "description": "Plan corporate wine tasting events for clients, teams and hospitality, with budget guidance, supplier questions and event planning checklists.",
        "intro": "A good corporate wine tasting is structured, inclusive and easy for attendees. The aim is a professional event with sensible pacing, not a heavy-drinking format.",
        "sections": [
            ("In-person vs virtual tastings", ["In-person works well for hospitality, private rooms and higher-touch client events.", "Virtual tastings suit remote teams and distributed clients, but delivery logistics matter.", "Hybrid formats need extra planning for both room and remote attendees."]),
            ("Guest numbers", ["Small groups can be more conversational and premium.", "Larger groups need a clearer run sheet, host control and simpler wine choices.", "Confirm final attendee count before pack delivery or venue commitment."]),
            ("Budget ranges", ["Under £25 per head: simple or informal route.", "£25-£60 per head: hosted virtual or accessible in-person format.", "£60-£120+ per head: premium host, venue, food pairing or private room."]),
            ("Venue and delivery considerations", ["Ask about licensing, glassware, food, water, transport and accessibility.", "For virtual events, confirm delivery lead times, substitutions and late-pack process."]),
        ],
        "primary_cta": ("Use the event planner", "/event-planner"),
        "related": [("Supplier directory", "/suppliers"), ("Corporate wine gifts", "/corporate-wine-gifts"), ("Virtual tasting guide", "/guides/virtual-wine-tasting-for-teams")],
    },
    "client-wine-gifts": {
        "title": "Client Wine Gifts",
        "h1": "Client wine gifts and customer thank-you gifts",
        "description": "Practical guide to client wine gifts, including budget bands, supplier considerations, delivery timing and enquiry-ready planning.",
        "intro": "Client wine gifts should feel considered without being awkward. The safest route is usually broad appeal, clear value, a short message and careful delivery planning.",
        "sections": [
            ("Choosing gifts by client tier", ["Everyday clients: practical bottle, sparkling alternative or modest hamper.", "Key accounts: stronger presentation, premium merchant or mixed case.", "VIP relationships: check policy first, then consider fine wine or presentation-led hamper."]),
            ("Avoiding awkward gift choices", ["Avoid highly unusual bottles unless you know the recipient well.", "Offer alcohol-free or non-alcoholic alternatives.", "Check anti-bribery, procurement and client gift policies."]),
            ("Branding and packaging", ["Subtle gift notes often work better than heavy branding.", "Ask suppliers about branded sleeves, cards, proofing time and minimum order quantity."]),
            ("Delivery timing", ["Build in time for address collection, failed deliveries and substitutions.", "Christmas and quarter-end periods need earlier supplier contact."]),
        ],
        "primary_cta": ("Use the gift planner", "/gift-planner"),
        "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Corporate Christmas wine gifts", "/corporate-christmas-wine-gifts"), ("Supplier directory", "/suppliers")],
    },
    "staff-wine-gifts": {
        "title": "Staff Wine Gifts",
        "h1": "Staff wine gifts and employee recognition",
        "description": "Plan staff wine gifts and employee recognition wine gifts with practical guidance on budgets, preferences, alternatives and delivery.",
        "intro": "Staff wine gifts need more sensitivity than client gifts because preferences, alcohol suitability, religion, culture and workplace policy can vary across a team.",
        "sections": [
            ("Staff gifting use cases", ["Year-end thank-yous, milestone recognition and team celebration packs.", "Remote employee gifts where UK-wide delivery is needed.", "Team event follow-ups or optional tasting packs."]),
            ("Mixed preferences", ["Use broad-appeal styles rather than niche bottles.", "Consider choice-based routes or hampers where possible.", "Avoid implying alcohol is expected."]),
            ("Alcohol sensitivity and alternatives", ["Offer alcohol-free alternatives as a normal option.", "Check HR guidance and avoid pressure to drink.", "Consider dietary, cultural and health factors."]),
            ("Budget ranges", ["£15-£30 per person: modest bottle or alcohol-free option.", "£30-£60 per person: stronger bottle, small hamper or tasting pack.", "£60+ per person: premium hamper or hosted experience."]),
        ],
        "primary_cta": ("Use the gift planner", "/gift-planner"),
        "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Corporate wine tasting events", "/corporate-wine-tasting-events"), ("Supplier directory", "/suppliers")],
    },
    "corporate-christmas-wine-gifts": {
        "title": "Corporate Christmas Wine Gifts",
        "h1": "Corporate Christmas wine gifts",
        "description": "Plan corporate Christmas wine gifts for clients and staff, including budget bands, bulk delivery, supplier lead times and hamper options.",
        "intro": "Christmas wine gifting is mostly an operations problem: supplier lead times, clean recipient data, sensible budget bands and enough room for substitutions.",
        "sections": [
            ("Planning early", ["Start supplier conversations well before December.", "Confirm internal approval, budget owner and recipient list early.", "Allow time for gift notes, branding and address checks."]),
            ("Bulk delivery", ["Ask suppliers about CSV templates, address validation and failed-delivery reporting.", "Confirm UK coverage, age verification and business address handling.", "Plan for substitutions if stock changes."]),
            ("Budget bands", ["£20-£40: practical bottle or modest festive gift.", "£40-£75: small hamper, sparkling wine or stronger presentation.", "£75+: premium hamper, Champagne route or fine wine merchant."]),
            ("Supplier lead times", ["Ask for final order deadlines, branding proof dates and last safe dispatch date.", "Do not rely on website stock for bulk Christmas orders."]),
            ("Alternatives and hampers", ["Include alcohol-free alternatives.", "Hampers can work well for mixed preferences and staff gifting.", "Check dietary and workplace suitability."]),
        ],
        "primary_cta": ("Use the gift planner", "/gift-planner"),
        "related": [("Client wine gifts", "/client-wine-gifts"), ("Staff wine gifts", "/staff-wine-gifts"), ("Supplier directory", "/suppliers")],
    },
}


def public_site_url(request: Request) -> str:
    return CANONICAL_ORIGIN


def absolute_url(request: Request, path: str) -> str:
    return canonical_url_for_path(path)


def organisation_schema(request: Request) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": PRODUCT_NAME,
        "url": public_site_url(request),
        "description": "Corporate wine gifting and tasting event planning tool",
        "sameAs": [],
    }


def website_schema(request: Request) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": PRODUCT_NAME,
        "url": public_site_url(request),
        "description": DEFAULT_META_DESCRIPTION,
    }


def web_app_schema(request: Request) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": PRODUCT_NAME,
        "url": public_site_url(request),
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
        "description": "Plan UK corporate wine gifts and tasting events with supplier-ready planning outputs.",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP"},
    }


def premium_pack_product_schema(request: Request) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "ClientCellar Premium Brief Pack",
        "description": "One-off supplier-ready corporate gifting or wine tasting planning pack",
        "brand": {"@type": "Brand", "name": PRODUCT_NAME},
        "offers": {
            "@type": "Offer",
            "price": "29.99",
            "priceCurrency": "GBP",
            "availability": "https://schema.org/InStock",
            "url": absolute_url(request, "/premium-pack"),
        },
    }


def article_schema(request: Request, guide: dict, slug: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": guide["h1"],
        "description": guide["description"],
        "author": {"@type": "Organization", "name": PRODUCT_NAME},
        "publisher": {"@type": "Organization", "name": PRODUCT_NAME},
        "mainEntityOfPage": absolute_url(request, f"/guides/{slug}"),
    }


def breadcrumb_schema(request: Request, crumbs: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": absolute_url(request, path),
            }
            for index, (name, path) in enumerate(crumbs, start=1)
        ],
    }


def faq_schema(questions: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in questions
        ],
    }


def render_template(request: Request, template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    page_canonical_url = canonical_url_for_path(context.get("canonical_url") or request.url.path)
    title = context.get("title") or "ClientCellar"
    description = context.get("description") or DEFAULT_META_DESCRIPTION
    page_title = context.get("page_title") or (DEFAULT_PAGE_TITLE if title == "ClientCellar" else f"{title} | {PRODUCT_NAME}")
    structured_data = [organisation_schema(request), *context.get("structured_data", [])]
    context.setdefault("title", title)
    context.setdefault("description", description)
    context.setdefault("page_title", page_title)
    context.setdefault("meta_description", context.get("meta_description") or description)
    context.setdefault("og_title", context.get("og_title") or page_title)
    context.setdefault("og_description", context.get("og_description") or context["meta_description"])
    context.setdefault("og_type", context.get("og_type") or "website")
    context.setdefault("product", PRODUCT_NAME)
    context.setdefault("payments_enabled", payments_enabled())
    context.setdefault("canonical_url", page_canonical_url)
    context.setdefault(
        "supplier_link_config",
        {supplier_id: link.url for supplier_id, link in SUPPLIER_LINK_CONFIG.items() if link.active and link.url},
    )
    context.setdefault("structured_data", structured_data)
    context.setdefault("noindex", context.get("noindex") or request.url.path.startswith("/admin"))

    if not isinstance(template_name, str):
        print("Invalid template_name passed to render_template:", repr(template_name))
        template_name = "message.html"
        context = {
            "title": "Something went wrong",
            "page_title": f"Something went wrong | {PRODUCT_NAME}",
            "meta_description": "We could not load this page correctly.",
            "og_title": f"Something went wrong | {PRODUCT_NAME}",
            "og_description": "We could not load this page correctly.",
            "og_type": "website",
            "eyebrow": "Error",
            "body": "We could not load this page correctly. Please try again or contact us.",
            "primary_label": "Return home",
            "primary_href": "/",
            "structured_data": structured_data,
            "canonical_url": page_canonical_url,
            "noindex": True,
            **context,
        }

    context = {"request": request, **context}
    try:
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context=context,
            status_code=status_code,
        )
    except Exception as exc:
        print(f"Template rendering failed for {template_name!r}:", repr(exc))
        if template_name == "message.html":
            raise
        fallback_context = {
            "request": request,
            "title": "Something went wrong",
            "description": "We could not load this page correctly.",
            "page_title": f"Something went wrong | {PRODUCT_NAME}",
            "meta_description": "We could not load this page correctly.",
            "og_title": f"Something went wrong | {PRODUCT_NAME}",
            "og_description": "We could not load this page correctly.",
            "og_type": "website",
            "product": PRODUCT_NAME,
            "payments_enabled": payments_enabled(),
            "canonical_url": page_canonical_url,
            "structured_data": [organisation_schema(request)],
            "noindex": True,
            "eyebrow": "Error",
            "body": "We could not load this page correctly. Please try again or contact us.",
            "primary_label": "Return home",
            "primary_href": "/",
        }
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context=fallback_context,
            status_code=500,
        )


def render(request: Request, template: str, title: str, description: str | None = None, **context) -> HTMLResponse:
    return render_template(
        request,
        template,
        title=title,
        description=description or "Corporate wine gifts and tasting events made simple.",
        product=PRODUCT_NAME,
        payments_enabled=payments_enabled(),
        **context,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    message = "Please check the form and try again."
    errors = exc.errors()
    if errors:
        message = errors[0].get("msg", message)
    return JSONResponse(status_code=422, content={"ok": False, "message": message, "detail": errors})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(
        request,
        "index.html",
        "Corporate Wine Gifts and Tasting Events",
        "Plan corporate wine gifts and tasting events with UK budget guidance, supplier suggestions and optional copy-ready business documents.",
        structured_data=[website_schema(request), web_app_schema(request)],
    )


@app.get("/gift-planner", response_class=HTMLResponse)
def gift_planner(request: Request):
    return render(request, "gift_planner.html", "Corporate Wine Gift Planner", "Create a practical UK corporate wine gift plan with budget guidance and supplier enquiry copy.")


@app.get("/event-planner", response_class=HTMLResponse)
def event_planner(request: Request):
    return render(request, "event_planner.html", "Corporate Wine Tasting Event Planner", "Plan a corporate wine tasting event with budget guidance, event structure and supplier enquiry copy.")


@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return render(
        request,
        "pricing.html",
        "Pricing",
        "Compare the free ClientCellar planner with the £29.99 Premium Brief Pack.",
        structured_data=[premium_pack_product_schema(request)],
    )


@app.get("/example-premium-brief-pack", response_class=HTMLResponse)
def example_premium_brief_pack(request: Request):
    example_supplier_links = {
        "majestic": supplier_public_url("majestic"),
        "marks_spencer": supplier_public_url("marks-spencer-corporate"),
        "fortnum_mason": supplier_public_url("fortnum-mason"),
        "laithwaites": supplier_public_url("laithwaites"),
    }
    return render(
        request,
        "example_premium_brief_pack.html",
        "Example Premium Brief Pack",
        "See an example ClientCellar Premium Brief Pack with supplier-ready buying brief, enquiry email, budget breakdown, supplier quote comparison table and internal approval summary.",
        structured_data=[premium_pack_product_schema(request)],
        example_supplier_links=example_supplier_links,
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return render(
        request,
        "about.html",
        "About ClientCellar",
        "ClientCellar helps UK businesses plan corporate wine gifts, staff gifting and tasting events with practical copy-ready business documents.",
    )


@app.get("/sign-in", response_class=HTMLResponse)
def sign_in(request: Request):
    return render(
        request,
        "sign_in.html",
        "Sign in",
        "Sign in to ClientCellar where checkout details need to be linked to your email.",
        auth_configured=supabase_settings()["configured"],
    )


@app.get("/login", response_class=HTMLResponse)
def login_redirect():
    return RedirectResponse(url="/sign-in", status_code=302)


@app.get("/account", response_class=HTMLResponse)
def account(request: Request):
    return render(
        request,
        "account.html",
        "Account",
        "View your ClientCellar sign-in details.",
        auth_configured=supabase_settings()["configured"],
    )


@app.get("/logout", response_class=HTMLResponse)
def logout(request: Request):
    return render(
        request,
        "account.html",
        "Signed out",
        "Sign out of ClientCellar on this browser.",
        auth_configured=supabase_settings()["configured"],
        sign_out_on_load=True,
    )


@app.get("/premium-pack", response_class=HTMLResponse)
def premium_pack(request: Request):
    return render(
        request,
        "premium_pack.html",
        "Premium Brief Pack",
        "Turn a rough gift or event idea into supplier emails, quote comparison and internal approval documents.",
        structured_data=[premium_pack_product_schema(request)],
    )


@app.get("/corporate-wine-gifts", response_class=HTMLResponse)
def corporate_wine_gifts(request: Request):
    return render_seo_landing(request, "corporate-wine-gifts")


@app.get("/corporate-wine-tasting-events", response_class=HTMLResponse)
def corporate_wine_tasting_events(request: Request):
    return render_seo_landing(request, "corporate-wine-tasting-events")


@app.get("/client-wine-gifts", response_class=HTMLResponse)
def client_wine_gifts(request: Request):
    return render_seo_landing(request, "client-wine-gifts")


@app.get("/staff-wine-gifts", response_class=HTMLResponse)
def staff_wine_gifts(request: Request):
    return render_seo_landing(request, "staff-wine-gifts")


@app.get("/corporate-christmas-wine-gifts", response_class=HTMLResponse)
def corporate_christmas_wine_gifts(request: Request):
    return render_seo_landing(request, "corporate-christmas-wine-gifts")


@app.get("/checkout/success", response_class=HTMLResponse)
def checkout_success(request: Request):
    session_id = request.query_params.get("session_id")
    pack_token = None
    payment_verified = False
    payment_status = None
    verification_error = False
    customer_email = None
    missing_plan_details = False
    pack_email = None

    if session_id and payments_enabled():
        try:
            import stripe
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            session = stripe.checkout.Session.retrieve(session_id)
            metadata = stripe_obj_get(session, "metadata", {}) or {}
            customer_details = stripe_obj_get(session, "customer_details", {}) or {}
            pack_token = stripe_obj_get(metadata, "pack_token")
            payment_status = stripe_obj_get(session, "payment_status")
            customer_email = stripe_obj_get(customer_details, "email") or stripe_obj_get(session, "customer_email") or stripe_obj_get(metadata, "email")
            if payment_status == "paid":
                payment_verified = True
                if pack_token:
                    update_premium_pack_payment(
                        pack_token,
                        "paid",
                        stripe_session_id=session_id,
                        stripe_payment_intent=stripe_obj_get(session, "payment_intent"),
                        amount_total=stripe_obj_get(session, "amount_total"),
                        currency=stripe_obj_get(session, "currency"),
                        customer_email=customer_email,
                    )
                    pack = get_premium_pack(pack_token)
                    missing_plan_details = not bool(
                        pack and (pack.get("planner_input") or pack.get("planner_output") or pack.get("premium_preview"))
                    )
                    if not missing_plan_details and pack:
                        pack_email = send_pack_ready_email(request, pack)
                supabase_user_id = stripe_obj_get(metadata, "supabase_user_id")
                if supabase_user_id:
                    print("Activating premium for Supabase user", supabase_user_id)
                    update_supabase_profile_from_payment(
                        supabase_user_id,
                        {
                            "email": customer_email,
                            "plan": "premium",
                            "subscription_status": "active" if stripe_obj_get(session, "subscription") else "paid_one_off",
                            "stripe_customer_id": stripe_obj_get(session, "customer"),
                            "stripe_subscription_id": stripe_obj_get(session, "subscription"),
                        },
                    )
                else:
                    print("Stripe checkout completed without supabase_user_id metadata")
        except Exception:
            verification_error = True

    open_pack_url = f"/premium-pack/view/{pack_token}" if pack_token else None
    return render_template(
        request,
        "checkout_success.html",
        eyebrow="Billing",
        title="Your Premium Brief Pack is saved",
        payment_verified=payment_verified,
        pack_token=pack_token,
        open_pack_url=open_pack_url,
        payments_enabled=payments_enabled(),
        verification_error=verification_error,
        payment_status=payment_status,
        customer_email=customer_email,
        session_id=session_id,
        missing_plan_details=missing_plan_details,
        pack_email=pack_email,
        hide_account_status=True,
        noindex=True,
    )


@app.get("/checkout/cancelled", response_class=HTMLResponse)
def checkout_cancelled(request: Request):
    token = request.query_params.get("token")
    if token:
        pack = get_premium_pack(token)
        if pack and pack.get("payment_status") == "pending":
            update_premium_pack_payment(token, "cancelled")

    return render_template(
        request,
        "checkout_cancelled.html",
        eyebrow="Checkout",
        title="Checkout cancelled",
        description="No payment was taken. You can return to pricing or contact ClientCellar for support.",
        noindex=True,
    )


@app.get("/billing/success", response_class=HTMLResponse)
def billing_success(request: Request):
    return checkout_success(request)


@app.get("/billing/cancel", response_class=HTMLResponse)
def billing_cancel(request: Request):
    token = request.query_params.get("token")
    if token:
        pack = get_premium_pack(token)
        if pack and pack.get("payment_status") == "pending":
            update_premium_pack_payment(token, "cancelled")
    return render(
        request,
        "billing_cancel.html",
        "Checkout cancelled",
        "Checkout cancelled. No payment was taken.",
        noindex=True,
    )


@app.get("/my-packs", response_class=HTMLResponse)
def my_packs(request: Request):
    return render_template(
        request,
        "my_packs.html",
        title="My packs",
        description="Find saved ClientCellar Premium Brief Packs.",
        noindex=True,
    )


@app.get("/premium-pack/view/{pack_token}", response_class=HTMLResponse)
def premium_pack_view(request: Request, pack_token: str):
    """Serve a premium pack if payment is verified or payments are disabled."""
    pack = get_premium_pack(pack_token)

    if not pack:
        return render_template(
            request,
            "message.html",
            status_code=404,
            eyebrow="Premium Brief Pack",
            title="We couldn’t find this Premium Brief Pack.",
            body="The secure pack link may be incomplete or expired. Create a new plan or contact support if you have already paid.",
            primary_label="Create a new plan",
            primary_href="/gift-planner",
            secondary_label="Contact support",
            secondary_href="/contact?interest=premium-pack-support",
        )

    if payments_enabled() and pack.get("payment_status") != "paid":
        return render_template(
            request,
            "message.html",
            status_code=402,
            eyebrow="Premium Brief Pack",
            title="Payment required",
            body="This Premium Brief Pack requires payment. Please complete checkout first or contact us for support.",
            primary_label="View pricing",
            primary_href="/pricing",
            secondary_label="Contact support",
            secondary_href="/contact?interest=premium-pack-support",
        )

    preview = pack.get("premium_preview")
    if not preview and pack.get("planner_input") and pack.get("planner_output"):
        try:
            preview = make_premium_pack_preview(
                PremiumPackPreviewRequest(
                    pack_type=pack["pack_type"],
                    planner_input=pack["planner_input"],
                    planner_output=pack["planner_output"],
                )
            )
            update_premium_pack_preview(pack_token, preview)
        except Exception:
            preview = {}

    preview = normalise_premium_pack_view_preview(pack, preview)
    touch_premium_pack_access(pack_token)

    return render_template(
        request,
        "premium_pack_view.html",
        title="Premium Planning Pack",
        pack=pack,
        pack_token=pack_token,
        preview=preview or {},
        planner_output=pack.get("planner_output", {}),
        payment_verified=pack.get("payment_status") == "paid",
    )


@app.post("/api/premium-pack/{pack_token}/download")
def premium_pack_download_count(pack_token: str):
    pack = get_premium_pack(pack_token)
    if not pack:
        raise HTTPException(status_code=404, detail="Premium Brief Pack not found.")
    if payments_enabled() and pack.get("payment_status") != "paid":
        raise HTTPException(status_code=403, detail="Payment is required for this Premium Brief Pack.")
    increment_premium_pack_download(pack_token)
    return {"ok": True}


@app.post("/api/premium-packs/request-access")
def request_premium_pack_access(req: PackAccessRequest, request: Request):
    email = str(req.email).strip().lower()
    logger.info("REQUEST_ACCESS_START email=%s", email)
    logger.info(
        "REQUEST_ACCESS_EMAIL_CONFIG resend_api_key_present=%s email_from_present=%s",
        bool(os.getenv("RESEND_API_KEY")),
        bool(os.getenv("EMAIL_FROM")),
    )
    prepared = []
    if allow_pack_access_request(email):
        pack_counts = count_premium_packs_by_email(email)
        logger.info(
            "REQUEST_ACCESS_LOOKUP email=%s total_count=%s paid_only_count=%s",
            email,
            pack_counts["total_count"],
            pack_counts["paid_count"],
        )
        packs = fetch_paid_premium_packs_by_email(email)
        logger.info("REQUEST_ACCESS_PACK_COUNT count=%s email=%s", len(packs), email)
        prepared = send_pack_recovery_email(request, email, packs)
    else:
        logger.warning("REQUEST_ACCESS_THROTTLED email=%s", email)
    response = {
        "ok": True,
        "message": "If that email has saved packs, we’ll send a secure access link.",
    }
    return response


@app.get("/suppliers", response_class=HTMLResponse)
def supplier_directory(request: Request):
    active_suppliers = [supplier for supplier in SUPPLIERS if supplier.get("active", True)]
    return render(
        request,
        "suppliers.html",
        "Corporate wine gift and tasting event suppliers",
        "Shortlist UK wine gift, hamper and tasting suppliers by use case, budget and event type.",
        suppliers=active_suppliers,
        supplier_sections=supplier_directory_sections(),
    )


@app.get("/suppliers/join", response_class=HTMLResponse)
def suppliers_join(request: Request):
    return render(
        request,
        "suppliers_join.html",
        "Work with ClientCellar",
        "Apply to be considered for the ClientCellar supplier directory.",
    )


@app.get("/supplier-application", response_class=HTMLResponse)
def supplier_application(request: Request):
    return suppliers_join(request)


@app.get("/suppliers/{tracking_slug}", response_class=HTMLResponse)
def supplier_detail(request: Request, tracking_slug: str):
    supplier = supplier_by_tracking_slug(tracking_slug)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return render(
        request,
        "supplier_detail.html",
        supplier["name"],
        supplier["description"],
        supplier=supplier,
        real_supplier=is_real_supplier(supplier),
    )


@app.get("/out/supplier/{tracking_slug}")
def supplier_outbound(request: Request, tracking_slug: str, source_page: str | None = None):
    supplier = supplier_by_tracking_slug(tracking_slug)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    destination = supplier_destination_url(supplier)
    if not destination:
        return RedirectResponse(url="/contact?interest=supplier-type", status_code=302)
    save_supplier_click(
        supplier=supplier,
        destination_url=destination,
        source_page=source_page,
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
    )
    return RedirectResponse(url=destination, status_code=302)


@app.get("/admin/leads-basic", response_class=HTMLResponse)
def admin_leads_basic(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password:
        return render(
            request,
            "admin_leads.html",
            "Lead admin",
            enabled=False,
            authorised=False,
            leads=[],
            password="",
        )
    if supplied_password != admin_password:
        return render(
            request,
            "admin_leads.html",
            "Lead admin",
            enabled=True,
            authorised=False,
            leads=[],
            password="",
        )
    return render(
        request,
        "admin_leads.html",
        "Lead admin",
        enabled=True,
        authorised=True,
        leads=fetch_leads(limit=100),
        password=supplied_password,
    )


def fetch_premium_orders(limit: int = 100) -> list[dict]:
    init_leads_db()
    with get_db_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM premium_packs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **dict(row),
            "customer_email": dict(row).get("customer_email") or dict(row).get("email"),
        }
        for row in rows
    ]


@app.get("/admin/orders", response_class=HTMLResponse)
def admin_orders(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password:
        return render(
            request,
            "admin_orders.html",
            "Premium orders",
            enabled=False,
            authorised=False,
            orders=[],
            password="",
        )
    if supplied_password != admin_password:
        return render(
            request,
            "admin_orders.html",
            "Premium orders",
            enabled=True,
            authorised=False,
            orders=[],
            password="",
        )
    return render(
        request,
        "admin_orders.html",
        "Premium orders",
        enabled=True,
        authorised=True,
        orders=fetch_premium_orders(limit=200),
        password=supplied_password,
    )


@app.get("/admin/supplier-applications", response_class=HTMLResponse)
def admin_supplier_applications(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password:
        return render(
            request,
            "admin_supplier_applications.html",
            "Supplier applications",
            enabled=False,
            authorised=False,
            applications=[],
            password="",
        )
    if supplied_password != admin_password:
        return render(
            request,
            "admin_supplier_applications.html",
            "Supplier applications",
            enabled=True,
            authorised=False,
            applications=[],
            password="",
        )
    return render(
        request,
        "admin_supplier_applications.html",
        "Supplier applications",
        enabled=True,
        authorised=True,
        applications=fetch_supplier_applications(limit=100),
        password=supplied_password,
    )


@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request):
    questions = [
        {"q": "Do you sell wine directly?", "a": "No. ClientCellar provides planning guidance and supplier briefing tools. You buy directly from suppliers."},
        {"q": "Do you check live stock or prices?", "a": "No. We do not check live stock, live prices, delivery slots or supplier availability. The planner tells you what to confirm."},
        {"q": "What is the Premium Brief Pack?", "a": "A supplier-ready planning document with a full brief, approval note, supplier questions, message bank, risk checklist and decision scorecard."},
        {"q": "Can I use this for staff gifts?", "a": "Yes. The planner includes staff-friendly prompts, budget awareness and alcohol-free alternative reminders."},
        {"q": "Can suppliers pay to appear?", "a": "Supplier, referral, affiliate or sponsored placements may be added with clear disclosure. Fit should come before commercial relationship."},
    ]
    return render(
        request,
        "faq.html",
        "FAQ",
        "Plain answers about ClientCellar, corporate wine gifting, suppliers, payments and responsible workplace gifting.",
        structured_data=[faq_schema(questions)],
    )


@app.get("/contact", response_class=HTMLResponse)
def contact(request: Request):
    return render(request, "contact.html", "Contact")


@app.get("/guides", response_class=HTMLResponse)
def guides_index(request: Request):
    return render(
        request,
        "guides.html",
        "Corporate Wine Gift and Tasting Guides",
        "Practical UK guides for corporate wine gifts, hampers, Champagne gifts and wine tasting events.",
        guides=GUIDES,
    )


@app.get("/guides/corporate-champagne-gifts")
def corporate_champagne_guide_redirect():
    return RedirectResponse(url="/guides/champagne-gifts-for-clients", status_code=301)


def render_seo_landing(request: Request, slug: str):
    page = SEO_PAGES.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    return render(
        request,
        "seo_landing.html",
        page["title"],
        page["description"],
        page=page,
        slug=slug,
        structured_data=[
            breadcrumb_schema(request, [("Home", "/"), ("Guides", "/guides"), (page["h1"], f"/{slug}")])
        ],
    )


@app.get("/guides/{slug}", response_class=HTMLResponse)
def guide_detail(request: Request, slug: str):
    guide = GUIDES.get(slug)
    if not guide:
        return render_template(
            request,
            "guides.html",
            status_code=404,
            title="Guides",
            description="Practical ClientCellar guides.",
            product=PRODUCT_NAME,
            guides=GUIDES,
        )
    return render(
        request,
        "guide_detail.html",
        guide["title"],
        guide["description"],
        guide=guide,
        guides=GUIDES,
        slug=slug,
        og_type="article",
        structured_data=[
            article_schema(request, guide, slug),
            breadcrumb_schema(request, [("Home", "/"), ("Guides", "/guides"), (guide["h1"], f"/guides/{slug}")]),
        ],
    )


@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return render(request, "terms.html", "Terms of Use")


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return render(request, "privacy.html", "Privacy Policy")


@app.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request):
    return render(
        request,
        "privacy.html",
        "Privacy Policy",
        "Plain-English privacy policy for ClientCellar, a UK corporate gifting and event wine planning website.",
    )


@app.get("/affiliate-disclosure", response_class=HTMLResponse)
def affiliate_disclosure(request: Request):
    return render(request, "affiliate_disclosure.html", "Affiliate Disclosure")


@app.get("/editorial-policy", response_class=HTMLResponse)
def editorial_policy(request: Request):
    return render(
        request,
        "editorial_policy.html",
        "Editorial Policy",
        "How ClientCellar writes practical UK client gifting guidance and distinguishes editorial recommendations from commercial placements.",
    )


@app.get("/supplier-partnerships", response_class=HTMLResponse)
def supplier_partnerships(request: Request):
    return render(
        request,
        "supplier_partnerships.html",
        "Supplier Partnerships",
        "Work with ClientCellar on UK corporate wine gifting, hamper, event wine and non-alcoholic gifting partnerships.",
    )


@app.get("/network-readiness", response_class=HTMLResponse)
def network_readiness(request: Request):
    return render(
        request,
        "network_readiness.html",
        "ClientCellar Publisher Profile",
        "Publisher profile for suppliers and commercial partnership review teams.",
    )


@app.get("/responsible-drinking", response_class=HTMLResponse)
def responsible_drinking(request: Request):
    return render(request, "responsible_drinking.html", "Responsible Drinking")


@app.get("/copyright", response_class=HTMLResponse)
def copyright_page(request: Request):
    return render(request, "copyright.html", "Copyright")


@app.get("/cookies", response_class=HTMLResponse)
def cookies(request: Request):
    return render(request, "cookies.html", "Cookie Policy")


@app.get("/sitemap.xml")
def sitemap(request: Request):
    guide_urls = [f"/guides/{slug}" for slug in GUIDES if slug not in SITEMAP_EXCLUDED_GUIDE_SLUGS]
    urls = list(dict.fromkeys(SITEMAP_STATIC_ROUTES + guide_urls))
    lastmod = date.today().isoformat()
    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *[f"  <url><loc>{canonical_url_for_path(path)}</loc><lastmod>{lastmod}</lastmod></url>" for path in urls],
            "</urlset>",
        ]
    )
    return Response(content=body, media_type="application/xml")


@app.get("/robots.txt")
def robots(request: Request):
    return Response(content=f"User-agent: *\nAllow: /\n\nSitemap: {CANONICAL_ORIGIN}/sitemap.xml\n", media_type="text/plain")


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


@app.get("/api/leads/export.csv")
def export_leads_csv(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password or supplied_password != admin_password:
        raise HTTPException(status_code=403, detail="Lead export is not enabled or the password is incorrect.")

    output = io.StringIO()
    writer = csv.writer(output)
    columns = [
        "id",
        "created_at",
        "name",
        "email",
        "company",
        "phone",
        "interested_in",
        "recipient_count",
        "budget_per_recipient",
        "occasion",
        "deadline",
        "message",
        "consent_to_contact",
        "source_page",
    ]
    writer.writerow(columns)
    for lead in fetch_leads():
        writer.writerow([lead[column] for column in columns])

    headers = {"Content-Disposition": "attachment; filename=clientcellar-leads.csv"}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)


@app.get("/api/admin/summary")
def admin_summary(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password or supplied_password != admin_password:
        raise HTTPException(status_code=403, detail="Admin summary is not enabled or the password is incorrect.")

    init_leads_db()
    with get_db_connection() as connection:
        lead_count = connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        application_count = connection.execute("SELECT COUNT(*) FROM supplier_applications").fetchone()[0]
        click_count = connection.execute("SELECT COUNT(*) FROM supplier_clicks").fetchone()[0]
        premium_order_count = connection.execute("SELECT COUNT(*) FROM premium_packs").fetchone()[0]
        paid_order_count = connection.execute(
            "SELECT COUNT(*) FROM premium_packs WHERE payment_status = 'paid'"
        ).fetchone()[0]
        pending_order_count = connection.execute(
            "SELECT COUNT(*) FROM premium_packs WHERE payment_status = 'pending'"
        ).fetchone()[0]
        premium_revenue_total = connection.execute(
            "SELECT COALESCE(SUM(amount_total), 0) FROM premium_packs WHERE payment_status = 'paid'"
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT tracking_slug, COUNT(*) AS clicks
            FROM supplier_clicks
            GROUP BY tracking_slug
            ORDER BY clicks DESC
            LIMIT 5
            """
        ).fetchall()
    top_clicked = []
    for row in rows:
        supplier = supplier_by_tracking_slug(row["tracking_slug"])
        top_clicked.append({"name": supplier["name"] if supplier else row["tracking_slug"], "clicks": row["clicks"]})
    return {
        "lead_count": lead_count,
        "supplier_application_count": application_count,
        "supplier_click_count": click_count,
        "premium_order_count": premium_order_count,
        "paid_order_count": paid_order_count,
        "pending_order_count": pending_order_count,
        "premium_revenue_total": premium_revenue_total,
        "top_clicked_suppliers": top_clicked,
    }


@app.post("/api/gift-plan")
def gift_plan(req: GiftPlanRequest):
    return make_gift_plan(req)


@app.post("/api/event-plan")
def event_plan(req: EventPlanRequest):
    return make_event_plan(req)


@app.get("/api/auth-config")
def auth_config():
    settings = supabase_settings()
    return {
        "configured": settings["configured"],
        "supabaseUrl": settings["url"] if settings["configured"] else "",
        "supabaseAnonKey": settings["anon_key"] if settings["configured"] else "",
    }


@app.get("/api/premium-status")
def premium_status(request: Request):
    """Return account-linked premium status. Without verified auth, everyone is free."""
    auth_header = request.headers.get("authorization", "")
    access_token = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None
    user = verify_supabase_access_token(access_token)
    if not user:
        return {
            "loggedIn": False,
            "authenticated": False,
            "email": None,
            "plan": "free",
            "isPremium": False,
            "premium": False,
            "subscription_active": False,
        }

    try:
        profile = fetch_supabase_profile(user["id"], access_token or "")
    except HTTPException:
        profile = {}
    plan = (profile.get("plan") or "free").lower()
    subscription_status = (profile.get("subscription_status") or "").lower()
    premium_statuses = {"active", "trialing", "paid_one_off"}
    is_premium = plan == "premium" or subscription_status in premium_statuses
    return {
        "loggedIn": True,
        "authenticated": True,
        "userId": user["id"],
        "email": profile.get("email") or user.get("email"),
        "plan": "premium" if is_premium else "free",
        "isPremium": is_premium,
        "premium": is_premium,
        "subscription_active": subscription_status in premium_statuses,
        "subscription_status": subscription_status or None,
        "stripe_customer_id": profile.get("stripe_customer_id"),
        "stripe_subscription_id": profile.get("stripe_subscription_id"),
    }


@app.post("/api/premium-pack-preview")
def premium_pack_preview(req: PremiumPackPreviewRequest):
    raise HTTPException(
        status_code=403,
        detail="Premium Brief Pack features require a completed one-off purchase.",
    )


def create_checkout_session_response(req: CheckoutSessionRequest, request: Request):
    if not has_generated_plan_payload(req):
        planner_url = "/event-planner?message=create-plan-first" if req.pack_type == "event" else "/gift-planner?message=create-plan-first"
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Create a free plan first, then you can upgrade it to a Premium Brief Pack.",
                "redirect_url": planner_url,
            },
        )

    auth_header = request.headers.get("authorization", "")
    access_token = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None
    user = verify_supabase_access_token(access_token)
    customer_email = str(req.email or (user or {}).get("email") or "") or None
    if not customer_email:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Please enter an email before checkout so we can save your Premium Brief Pack link.",
                "requires_email": True,
            },
        )

    if not payments_enabled():
        return {
            "enabled": False,
            "message": "Payments are not enabled yet. Please register interest instead.",
        }

    try:
        import stripe
    except Exception:
        return {
            "enabled": False,
            "message": "Payments are not enabled yet. Please register interest instead.",
        }

    pack_token = generate_pack_token()
    premium_preview = req.premium_preview
    if not premium_preview:
        premium_preview = make_premium_pack_preview(
            PremiumPackPreviewRequest(
                pack_type=req.pack_type,
                planner_input=req.planner_input or {},
                planner_output=req.planner_output or {},
            )
        )
    checkout_metadata = {
        "supabase_user_id": (user or {}).get("id", ""),
        "email": customer_email or "",
        "product": "clientcellar_premium_brief_pack",
        "pack_type": req.pack_type,
        "pack_token": pack_token,
        "plan_id": pack_token,
    }
    if user:
        print("Creating checkout for Supabase user", user["id"])
    else:
        print("Creating one-off checkout without Supabase user metadata")
    save_premium_pack(
        pack_token=pack_token,
        pack_type=req.pack_type,
        customer_email=customer_email,
        payment_status="pending",
        planner_input=req.planner_input,
        planner_output=req.planner_output,
        premium_preview=premium_preview,
    )

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    session_data = {
        "mode": "payment",
        "line_items": [{"price": os.getenv("STRIPE_PRICE_ID"), "quantity": 1}],
        "success_url": f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base_url}/billing/cancel",
        "client_reference_id": pack_token,
        "metadata": checkout_metadata,
        "payment_intent_data": {
            "metadata": checkout_metadata,
        },
    }
    if customer_email:
        session_data["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**session_data)
    return {"enabled": True, "url": session.url, "checkout_url": session.url, "session_id": session.id, "pack_token": pack_token}


@app.post("/api/stripe/create-checkout-session")
def create_stripe_checkout_session(req: CheckoutSessionRequest, request: Request):
    return create_checkout_session_response(req, request)


@app.post("/api/create-checkout-session")
def create_checkout_session(req: CheckoutSessionRequest, request: Request):
    return create_checkout_session_response(req, request)


async def handle_stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse(
            status_code=400,
            content={"error": "Stripe webhook secret is not configured."},
        )

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header.")

    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

    event_type = stripe_obj_get(event, "type")
    data_obj = stripe_obj_get(stripe_obj_get(event, "data", {}), "object", {})
    metadata = stripe_obj_get(data_obj, "metadata", {}) or {}
    pack_token = stripe_obj_get(metadata, "pack_token")
    print("Stripe webhook event:", event_type)
    print("Stripe webhook pack_token:", pack_token)

    if event_type == "checkout.session.completed":
        payment_status = stripe_obj_get(data_obj, "payment_status")
        supabase_user_id = stripe_obj_get(metadata, "supabase_user_id")
        if pack_token and payment_status == "paid":
            customer_details = stripe_obj_get(data_obj, "customer_details", {}) or {}
            customer_email = (
                stripe_obj_get(customer_details, "email")
                or stripe_obj_get(data_obj, "customer_email")
                or stripe_obj_get(metadata, "email")
            )
            subscription_id = stripe_obj_get(data_obj, "subscription")
            update_premium_pack_payment(
                pack_token,
                "paid",
                stripe_session_id=stripe_obj_get(data_obj, "id"),
                stripe_payment_intent=stripe_obj_get(data_obj, "payment_intent"),
                amount_total=stripe_obj_get(data_obj, "amount_total"),
                currency=stripe_obj_get(data_obj, "currency"),
                customer_email=customer_email,
            )
            pack = get_premium_pack(pack_token)
            if pack:
                send_pack_ready_email(request, pack)
            if supabase_user_id:
                update_supabase_profile_from_payment(
                    supabase_user_id,
                    {
                        "email": customer_email,
                        "plan": "premium",
                        "subscription_status": "active" if subscription_id else "paid_one_off",
                        "stripe_customer_id": stripe_obj_get(data_obj, "customer"),
                        "stripe_subscription_id": subscription_id,
                    },
                )
                print("Premium activated for Supabase user:", supabase_user_id)
            else:
                print("Saved paid Premium Brief Pack without Supabase user metadata")
        elif not pack_token:
            print("Stripe webhook warning: checkout.session.completed missing pack_token")
            subscription_id = stripe_obj_get(data_obj, "subscription")
            customer_details = stripe_obj_get(data_obj, "customer_details", {}) or {}
            print("Activating premium for Supabase user", supabase_user_id)
            update_supabase_profile_from_payment(
                supabase_user_id,
                {
                    "email": stripe_obj_get(customer_details, "email") or stripe_obj_get(data_obj, "customer_email") or stripe_obj_get(metadata, "email"),
                    "plan": "premium",
                    "subscription_status": "active" if subscription_id else "paid_one_off",
                    "stripe_customer_id": stripe_obj_get(data_obj, "customer"),
                    "stripe_subscription_id": subscription_id,
                },
            )
    elif event_type == "checkout.session.expired":
        if pack_token:
            update_premium_pack_payment(pack_token, "cancelled")
    elif event_type == "customer.subscription.deleted":
        subscription_id = stripe_obj_get(data_obj, "id")
        update_supabase_profile_by_subscription(
            subscription_id,
            {
                "plan": "free",
                "subscription_status": "cancelled",
            },
        )
        print("Subscription cancelled for Stripe subscription:", subscription_id)
    elif event_type == "payment_intent.payment_failed":
        if pack_token:
            update_premium_pack_payment(
                pack_token,
                "failed",
                stripe_payment_intent=stripe_obj_get(data_obj, "id"),
                customer_email=stripe_obj_get(data_obj, "receipt_email") or stripe_obj_get(stripe_obj_get(data_obj, "metadata", {}), "customer_email"),
            )
    elif event_type == "invoice.payment_failed":
        subscription_id = stripe_obj_get(data_obj, "subscription")
        if subscription_id:
            update_supabase_profile_by_subscription(
                subscription_id,
                {"subscription_status": "past_due"},
            )
            print("Subscription invoice payment failed:", subscription_id)

    return {"received": True}


@app.post("/api/stripe/webhook")
async def stripe_webhook_api(request: Request):
    return await handle_stripe_webhook(request)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    return await handle_stripe_webhook(request)


@app.post("/api/lead")
def create_lead(req: LeadRequest):
    save_lead(req)
    return {"ok": True, "message": "Thanks — your enquiry has been saved."}


@app.post("/api/supplier-application")
def create_supplier_application(req: SupplierApplicationRequest):
    save_supplier_application(req)
    return {"ok": True, "message": "Thanks — your supplier application has been saved."}


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
