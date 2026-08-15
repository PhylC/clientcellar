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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

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
    has_live_affiliate_links,
    supplier_affiliate_url as configured_supplier_affiliate_url,
    supplier_url as configured_supplier_url,
)
from data.gift_recommendations import (
    gift_recommendation_routes,
    gift_recommendation_shortlist,
    gift_supplier_comparison_rows,
)
from data.suppliers import (
    SUPPLIER_ENTRIES,
    featured_supplier_directory_entries,
    supplier_directory_entries,
)

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
GUIDE_IMAGE_DIR = BASE_DIR / "public" / "images" / "clientcellar" / "guides"
GUIDE_IMAGE_URL_PREFIX = "/images/clientcellar/guides"
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
app.mount("/images", StaticFiles(directory=BASE_DIR / "public" / "images"), name="images")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
logger.info(
    "RESEND_ENABLED=%s EMAIL_FROM_SET=%s",
    bool(os.getenv("RESEND_API_KEY")),
    bool(os.getenv("EMAIL_FROM")),
)


SEO_REDIRECTS = {
    "/privacy": "/privacy-policy",
    "/best-wine-gifts-for-clients": "/guides/best-client-wine-gifts",
    "/guides/client-wine-gifts": "/guides/best-client-wine-gifts",
    "/corporate-wine-gifts-uk": "/corporate-wine-gifts",
    "/guides/christmas-wine-gifts-for-clients": "/guides/christmas-corporate-wine-gifts",
    "/guides/wine-gifts-for-christmas": "/guides/christmas-corporate-wine-gifts",
    "/guides/thank-you-wine-gifts": "/guides/client-thank-you-wine-gifts",
    "/guides/wine-gifts-for-thank-you": "/guides/client-thank-you-wine-gifts",
    "/wine-for-corporate-events": "/event-wine-planning-uk",
    "/guides/wine-tasting-corporate-event": "/corporate-wine-tasting-events",
    "/guides/wine-gift-baskets-uk": "/guides/wine-gift-hampers-uk",
    "/guides/luxury-wine-gifts-for-clients": "/guides/luxury-corporate-wine-gifts",
    "/staff-wine-gifts-uk": "/staff-wine-gifts",
    "/supplier-application": "/submit-supplier",
}

SITEMAP_STATIC_ROUTES = [
    "/",
    "/about",
    "/affiliate-disclosure",
    "/contact",
    "/corporate-wine-gift-suppliers-uk",
    "/corporate-hamper-suppliers-uk",
    "/client-gift-suppliers-uk",
    "/christmas-client-gift-suppliers",
    "/client-wine-gifts",
    "/client-christmas-gifts-uk",
    "/corporate-christmas-wine-gifts",
    "/corporate-gifting-ideas-uk",
    "/corporate-hampers-uk",
    "/corporate-wine-gifts",
    "/corporate-wine-tasting-events",
    "/editorial-policy",
    "/event-planner",
    "/event-wine-planning-uk",
    "/example-premium-brief-pack",
    "/example-premium-event-pack",
    "/faq",
    "/gift-planner",
    "/guides",
    "/premium-client-gifts-uk",
    "/premium-pack",
    "/pricing",
    "/privacy-policy",
    "/responsible-drinking",
    "/staff-wine-gifts",
    "/submit-supplier",
    "/supplier-directory",
    "/supplier-partnerships",
    "/suppliers",
    "/terms",
    "/thank-you-gifts-for-clients",
    "/uk-wine-gift-supplier-comparison",
    "/wine-gift-suppliers-for-businesses",
]
SITEMAP_GUIDE_SLUGS = [
    "best-client-wine-gifts",
    "best-wine-accessories-for-gifts",
    "best-wine-gifts-under-100",
    "best-wine-gifts-under-25",
    "best-wine-gifts-under-50",
    "business-gift-wine-etiquette",
    "champagne-gifts-for-clients",
    "christmas-corporate-wine-gifts",
    "client-gift-policy-checklist",
    "client-gifting-etiquette-uk",
    "client-thank-you-wine-gifts",
    "corporate-event-wine-planning",
    "corporate-gift-ideas-for-clients",
    "corporate-gifting-recipient-csv-template",
    "corporate-wine-gifts-uk",
    "corporate-wine-gifts-under-100",
    "corporate-wine-gifts-under-50",
    "corporate-wine-hampers",
    "corporate-wine-tasting-london",
    "english-sparkling-corporate-gifts",
    "food-and-wine-hampers",
    "how-much-to-spend-on-client-gifts",
    "luxury-corporate-wine-gifts",
    "luxury-wine-hampers-uk",
    "non-alcoholic-client-gifts",
    "personalised-wine-gifts",
    "red-wine-gifts-for-clients",
    "staff-wine-gifts",
    "virtual-wine-tasting-for-teams",
    "white-wine-gifts-for-clients",
    "wine-gift-hampers-uk",
    "wine-gifts-for-accountancy-firms",
    "wine-gifts-for-agencies",
    "wine-gifts-for-customers",
    "wine-gifts-for-events",
    "wine-gifts-for-law-firms",
    "wine-gifts-for-new-business",
    "wine-gifts-for-sales-teams",
    "wine-tasting-team-building",
]


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
    redirect_destination = SEO_REDIRECTS.get(clean_path)
    should_redirect_host = host == WWW_HOST or is_render_host(host)
    should_redirect_scheme = host in {CANONICAL_HOST, WWW_HOST} and scheme == "http"
    should_redirect_path = path != clean_path
    if redirect_destination or should_redirect_host or should_redirect_scheme or should_redirect_path:
        query = f"?{request.url.query}" if request.url.query else ""
        destination_path = redirect_destination or clean_path
        return RedirectResponse(f"{CANONICAL_ORIGIN}{destination_path}{query}", status_code=301)
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


def safe_analytics_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text:
        return None
    return text[:limit]


def safe_analytics_path(value: Any) -> str | None:
    text = safe_analytics_text(value, 300)
    if not text:
        return None
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme or parsed.netloc:
        path = parsed.path or "/"
    else:
        path = text.split("?", 1)[0].split("#", 1)[0] or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return path[:300]


def safe_analytics_metadata(metadata: dict[str, Any] | None, client_timestamp: str | None = None) -> dict:
    safe: dict[str, Any] = {}
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if key not in ANALYTICS_METADATA_ALLOWLIST:
                continue
            if isinstance(value, bool) or value is None:
                safe[key] = value
            elif isinstance(value, (int, float)):
                safe[key] = value
            else:
                safe[key] = safe_analytics_text(value, 500)
    if client_timestamp:
        safe["client_timestamp"] = safe_analytics_text(client_timestamp, 80)
    return safe


def analytics_device_type(user_agent: str | None = None) -> str | None:
    user_agent = (user_agent or "").lower()
    if "mobile" in user_agent or "iphone" in user_agent or "android" in user_agent:
        return "mobile"
    if "ipad" in user_agent or "tablet" in user_agent:
        return "tablet"
    if user_agent:
        return "desktop"
    return None


def build_analytics_payload(
    event_name: str,
    request: Request | None = None,
    *,
    page_path: str | None = None,
    referrer: str | None = None,
    device_type: str | None = None,
    viewport_width: int | None = None,
    session_id: str | None = None,
    report_type: str | None = None,
    supplier_name: str | None = None,
    supplier_url: str | None = None,
    checkout_session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict | None:
    if event_name not in ANALYTICS_EVENT_ALLOWLIST:
        return None
    user_agent = request.headers.get("user-agent") if request else None
    request_path = request.url.path if request else None
    return {
        "event_name": event_name,
        "session_id": safe_analytics_text(session_id, 120),
        "page_path": safe_analytics_path(page_path or request_path),
        "referrer": safe_analytics_text(referrer or (request.headers.get("referer") if request else None), 500),
        "device_type": safe_analytics_text(device_type or analytics_device_type(user_agent), 40),
        "viewport_width": viewport_width if isinstance(viewport_width, int) and 0 <= viewport_width <= 10000 else None,
        "user_agent": safe_analytics_text(user_agent, 500),
        "report_type": safe_analytics_text(report_type, 20),
        "supplier_name": safe_analytics_text(supplier_name, 160),
        "supplier_url": safe_analytics_text(supplier_url, 800),
        "checkout_session_id": safe_analytics_text(checkout_session_id, 240),
        "metadata": safe_analytics_metadata(metadata, timestamp),
    }


def store_analytics_event(payload: dict | None) -> bool:
    if not payload:
        return False
    settings = supabase_settings()
    if not settings["service_configured"]:
        return False
    try:
        admin = get_supabase_admin()
        if admin is not None:
            admin.table("analytics_events").insert(payload).execute()
            return True
    except Exception as error:
        print("Supabase analytics insert failed; trying REST fallback:", str(error))
    try:
        _supabase_json_request(
            f"{settings['url']}/rest/v1/analytics_events",
            method="POST",
            headers={
                "apikey": settings["service_role_key"],
                "Authorization": f"Bearer {settings['service_role_key']}",
                "Prefer": "return=minimal",
            },
            payload=payload,
            timeout=4,
        )
        return True
    except Exception as error:
        print("Supabase analytics REST insert failed:", str(error))
        return False


def track_server_event(event_name: str, request: Request | None = None, **kwargs) -> None:
    try:
        store_analytics_event(build_analytics_payload(event_name, request, **kwargs))
    except Exception as error:
        print("Analytics tracking failed:", str(error))


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
            WHERE pack_token = ? OR access_token = ?
            """,
            (now, now, pack_token, pack_token),
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
            WHERE pack_token = ? OR access_token = ?
            """,
            (now, pack_token, pack_token),
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


ANALYTICS_EVENT_ALLOWLIST = {
    "page_view",
    "nav_click",
    "contact_click",
    "supplier_click",
    "gift_planner_started",
    "gift_free_report_generated",
    "gift_supplier_clicked",
    "gift_upgrade_clicked",
    "gift_checkout_started",
    "gift_premium_viewed",
    "event_planner_started",
    "event_free_report_generated",
    "event_supplier_clicked",
    "event_upgrade_clicked",
    "event_checkout_started",
    "event_premium_viewed",
    "example_gift_premium_viewed",
    "example_event_premium_viewed",
    "example_upgrade_clicked",
    "checkout_session_created",
    "checkout_success_page_viewed",
    "stripe_webhook_completed",
    "premium_access_granted",
    "premium_access_failed",
}

ANALYTICS_METADATA_ALLOWLIST = {
    "link_text",
    "link_url",
    "source",
    "source_page",
    "status",
    "error",
    "pack_token",
    "payment_status",
    "stripe_event_type",
    "payment_verified",
    "is_example",
    "client_timestamp",
}


class AnalyticsEventRequest(BaseModel):
    event_name: str = Field(min_length=1, max_length=80)
    page_path: str | None = Field(default=None, max_length=300)
    referrer: str | None = Field(default=None, max_length=500)
    device_type: str | None = Field(default=None, max_length=40)
    viewport_width: int | None = Field(default=None, ge=0, le=10000)
    user_agent: str | None = Field(default=None, max_length=500)
    session_id: str | None = Field(default=None, max_length=120)
    report_type: str | None = Field(default=None, max_length=20)
    supplier_name: str | None = Field(default=None, max_length=160)
    supplier_url: str | None = Field(default=None, max_length=800)
    checkout_session_id: str | None = Field(default=None, max_length=240)
    timestamp: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] | None = None


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


def supplier_has_commercial_term(supplier: dict, term: str) -> bool:
    target = term.lower()
    values = [
        supplier.get("category"),
        supplier.get("notes"),
        supplier.get("search_suggestion"),
        *supplier.get("best_for", []),
        *supplier.get("use_cases", []),
        *supplier.get("link_category_tags", []),
    ]
    return any(target in str(value).lower() for value in values if value)


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
        "best_for": row.get("advisory_best_for") or row.get("best_for_advisory") or row.get("best_for") or profile["best_for"],
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
            {"label": "Recommended route", "value": "Start with Majestic Commercial for the operational event conversation, then benchmark against Majestic Corporate Gifts, Virgin Wines Corporate, Laithwaites and Waitrose Cellar."},
            {"label": "Budget sweet spot", "value": "Indicative: £45-£95 per attendee is usually enough for a credible business tasting or drinks-led event before venue, food and service costs."},
            {"label": "Attendee strategy", "value": "Separate standard attendees, VIP/client-facing guests and alcohol-free attendees before asking suppliers for options."},
            {"label": "Timing", "value": "Begin supplier contact 3-6 weeks before the event; longer for Christmas, virtual packs, branded materials or multi-address delivery."},
            {"label": "Main risk", "value": "Choosing a supplier before confirming quantities, venue rules, delivery ownership, chilling/glassware, alcohol-free options and substitutions."},
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
            "Use Majestic Commercial as the first event wine route where quantities, delivery planning or office-event support matter.",
            "Use Majestic Corporate Gifts or Laithwaites for a more straightforward wine-gift or staff-reward style event order.",
            "Use Virgin Wines Corporate when the event needs approachable mixed-case options rather than a formal fine-wine feel.",
            "Use Waitrose Cellar as a budget-safe mainstream benchmark before committing to a more managed route.",
            "Confirm delivery window, chilling, glassware, venue corkage, substitutions and alcohol-free options before payment.",
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
    if pack_type == "gift":
        return gift_recommendation_shortlist()

    def find_row(*terms: str) -> dict | None:
        for row in rows:
            label = " ".join([str(row.get("supplier") or ""), str(row.get("best_for") or ""), str(row.get("supplier_type") or "")]).lower()
            if any(term in label for term in terms):
                return row
        return None

    if pack_type == "event":
        overall = find_row("majestic commercial") or rows[0]
        fallback = find_row("waitrose") or find_row("virgin") or (rows[1] if len(rows) > 1 else rows[0])
        vip = find_row("laithwaites") or find_row("majestic corporate") or overall
        wine_only = find_row("majestic corporate") or find_row("virgin") or overall
        approachable = find_row("virgin") or fallback
        return [
            {"rank": "Best overall", "supplier": overall.get("supplier") or overall.get("supplier_type"), "reason": "Best first call when event quantities, delivery planning and business order support need to be handled together."},
            {"rank": "Best budget-safe fallback", "supplier": fallback.get("supplier") or fallback.get("supplier_type"), "reason": "Good benchmark if the event can be self-managed and you mainly need recognised UK wine gifts or bottles."},
            {"rank": "Best VIP/premium option", "supplier": vip.get("supplier") or vip.get("supplier_type"), "reason": "Use where presentation, corporate gifting polish and a more premium wine route matter."},
            {"rank": "Best wine-only alternative", "supplier": wine_only.get("supplier") or wine_only.get("supplier_type"), "reason": "Useful if the event is closer to staff rewards, client gifting or simple wine distribution than hosted tasting."},
            {"rank": "Best approachable staff route", "supplier": approachable.get("supplier") or approachable.get("supplier_type"), "reason": "Good for friendly mixed-case options, staff rewards and less formal corporate gifting routes."},
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
    for item in shortlist:
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
                "contact_label": f"View {display_name}" if "local independent" not in normalise_supplier_label(display_name) else "Find local wine merchants",
                "contactLabel": f"View {display_name}" if "local independent" not in normalise_supplier_label(display_name) else "Find local wine merchants",
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
            "The lead route is chosen for operational confidence: quantities, delivery planning, substitutions and business-order support.",
            "Fallback routes stay visible so the buyer can switch between managed support, mainstream retail and approachable mixed-case routes.",
            "VIP and premium routes are separated so higher spend is used only where presentation or client-facing value justifies it.",
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
    if "event" in purpose or "commercial" in purpose or "partnership" in purpose:
        return "Check event support"
    if "corporate wine gifts" in purpose:
        return "View corporate wine gifts"
    if "corporate gifts" in purpose or "corporate gifting" in purpose:
        return "View corporate gifts"
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
            "Premium retailer",
            "Better for formal client gifts, Champagne, premium presentation or higher perceived value.",
            ["fortnum-mason", "vintage-wine-gifts", "waitrose-cellar", "majestic"],
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
            "Majestic Commercial",
            "Best for larger events, office celebrations and business orders where range, quantity and delivery planning matter.",
            ["majestic-commercial"],
            "Ask about delivery windows, quantities, substitutions, chilling, glassware, returns and event support.",
            "/event-planner",
        ),
        supplier_route_card(
            "Majestic Corporate Gifts",
            "Best for client gifting, staff rewards and straightforward corporate wine options.",
            ["majestic"],
            "Ask about bulk order support, gift notes, VAT invoices, delivery tracking and substitutions.",
            "/event-planner",
        ),
        supplier_route_card(
            "Virgin Wines Corporate",
            "Best for approachable corporate gifting, staff rewards, branded gifts and mixed-case options.",
            ["virgin-wines"],
            "Ask about branded gifts, mixed-case support, staff reward options, delivery timing and substitutions.",
            "/event-planner",
        ),
        supplier_route_card(
            "Laithwaites Corporate Wine Gifts",
            "Best for established corporate wine gifts, premium presentation and bulk gifting support.",
            ["laithwaites"],
            "Ask about corporate order handling, premium presentation, VAT invoices, lead times and bulk gifting support.",
            "/event-planner",
        ),
        supplier_route_card(
            "Waitrose Cellar",
            "Best for recognised UK retail wine gifts and mainstream premium options.",
            ["waitrose-cellar"],
            "Ask about delivery timing, substitutions, case availability, gift options and VAT invoice availability.",
            "/event-planner",
        ),
    ]
    if req.format in {"virtual", "hybrid"}:
        routes.append(supplier_route_card(
            "Virtual tasting pack route",
            "Useful when attendees need packs delivered before a remote or hybrid session.",
            ["virgin-wines", "laithwaites"],
            "Ask about attendee address handling, delivery lead times, late packs and alcohol-free alternatives.",
            "/event-planner",
        ))
    return routes[:5]


def event_supplier_comparison_rows() -> list[dict]:
    return [
        {
            "supplier_id": "majestic-commercial",
            "supplier": "Majestic Commercial",
            "supplier_type": "Event wine and commercial order support",
            "best_for": "Larger events, office celebrations and business orders where range, quantity and delivery planning matter.",
            "best_for_tags": ["Best overall", "Events", "Operations"],
            "typical_spend": "Indicative: strongest around £45-£120 per attendee when fulfilment confidence matters.",
            "minimum_order": "Ask early about event order thresholds, case quantities and whether account support applies.",
            "branding_personalisation": "Better for practical business ordering than bespoke branding; ask about gift notes or event materials if needed.",
            "turnaround": "Allow 3-6 weeks for events, longer around Christmas or when delivery windows are fixed.",
            "multi_address_delivery": "Ask whether they can support venue delivery, office delivery or attendee-pack fulfilment by file upload.",
            "ease_score": "8/10",
            "hidden_watchouts": "Operationally strong, but still confirm chilling, glassware, returns and substitutions before committing.",
            "recommendation": "Use as the first supplier conversation for larger or business-critical event wine planning.",
            "budget_fit": "Indicative: useful when fulfilment confidence and operational support matter more than the lowest bottle price.",
            "strengths": "Strong first route for event wine quantities, office celebrations and corporate event conversations.",
            "watchouts": "Ask about delivery windows, substitutions, chilling, glassware, returns and whether event support fits the format.",
            "questions_to_ask": "Can you support the attendee count, event date, delivery window, substitutions and any glassware or chilling needs?",
        },
        {
            "supplier_id": "majestic",
            "supplier": "Majestic Corporate Gifts",
            "supplier_type": "Corporate wine gifting",
            "best_for": "Client gifting, staff rewards and straightforward corporate wine options.",
            "best_for_tags": ["Wine only", "Corporate", "Scalable"],
            "typical_spend": "Indicative: strongest around £35-£95 per attendee or recipient for practical corporate wine options.",
            "minimum_order": "Ask about bulk order thresholds, case ordering and whether corporate account support is available.",
            "branding_personalisation": "Confirm gift notes, simple personalisation and whether attendee or recipient data can be uploaded cleanly.",
            "turnaround": "Allow 2-4 weeks for straightforward corporate wine orders; longer for seasonal peaks.",
            "multi_address_delivery": "Ask whether single-venue, office and multiple-address delivery are handled differently.",
            "ease_score": "8/10",
            "hidden_watchouts": "Good practical route, but may feel more functional than premium unless the range is chosen carefully.",
            "recommendation": "Use as the wine-only benchmark or for staff/client orders that do not need a hosted experience.",
            "budget_fit": "Indicative: strong benchmark for mainstream corporate wine gifting and repeat business orders.",
            "strengths": "Good practical comparison route for business wine gifts and staff reward orders.",
            "watchouts": "Confirm gift notes, VAT invoices, multi-address handling, delivery tracking and substitutions.",
            "questions_to_ask": "Can you support gift messages, VAT invoices, bulk order handling and delivery tracking for this brief?",
        },
        {
            "supplier_id": "virgin-wines",
            "supplier": "Virgin Wines Corporate",
            "supplier_type": "Corporate gifts and mixed cases",
            "best_for": "Approachable corporate gifting, staff rewards, branded gifts and mixed-case options.",
            "best_for_tags": ["Staff rewards", "Approachable", "Mixed cases"],
            "typical_spend": "Indicative: strongest around £30-£85 per attendee or recipient for approachable mixed-case options.",
            "minimum_order": "Ask whether corporate gifting support, branded options and delivery handling fit the attendee count.",
            "branding_personalisation": "Useful to ask about branded gifts, notes and packaging where the event doubles as staff recognition.",
            "turnaround": "Allow 2-4 weeks, with extra time for branded or seasonal work.",
            "multi_address_delivery": "Confirm whether they can handle one venue, one office or many individual addresses.",
            "ease_score": "7/10",
            "hidden_watchouts": "Can feel informal for VIP client entertainment unless presentation is specified clearly.",
            "recommendation": "Use as the friendly staff-reward or mixed-case alternative, not the sole VIP route.",
            "budget_fit": "Indicative: useful where a friendly corporate gift route is more important than boutique curation.",
            "strengths": "Good alternative for mixed-case corporate gifts and staff reward options.",
            "watchouts": "Confirm branding, substitutions, delivery timing and whether options feel appropriate for the audience.",
            "questions_to_ask": "Can you provide corporate gift options, delivery timing, substitution rules and branded gift support?",
        },
        {
            "supplier_id": "laithwaites",
            "supplier": "Laithwaites Corporate Wine Gifts",
            "supplier_type": "Corporate wine gifts",
            "best_for": "Established corporate wine gifts, premium presentation and bulk gifting support.",
            "best_for_tags": ["Premium", "Corporate gifts", "Presentation"],
            "typical_spend": "Indicative: strongest around £45-£120 per attendee or recipient where presentation matters.",
            "minimum_order": "Ask about minimum order quantities, seasonal cut-offs and corporate quote handling.",
            "branding_personalisation": "Strong route to test for polished presentation, gift notes and corporate-order support.",
            "turnaround": "Allow 3-5 weeks for premium presentation or Christmas-period work.",
            "multi_address_delivery": "Ask whether multiple delivery addresses and delivery tracking are available for the brief.",
            "ease_score": "7/10",
            "hidden_watchouts": "Premium presentation can be undermined by late substitutions or unclear delivery cut-offs.",
            "recommendation": "Use as the premium corporate wine-gift comparison route for client-facing events or senior attendees.",
            "budget_fit": "Indicative: useful where presentation and corporate order support are important.",
            "strengths": "Strong polished wine-gift comparison route for corporate buyers.",
            "watchouts": "Confirm minimum order quantities, presentation options, VAT invoice support and seasonal cut-offs.",
            "questions_to_ask": "Can you support bulk gifting, premium presentation, VAT invoices, delivery timing and substitutions?",
        },
        {
            "supplier_id": "waitrose-cellar",
            "supplier": "Waitrose Cellar",
            "supplier_type": "Recognised UK retail wine gifts",
            "best_for": "Recognised UK retail wine gifts and mainstream premium options.",
            "best_for_tags": ["Budget-safe", "Mainstream", "Benchmark"],
            "typical_spend": "Indicative: strongest around £20-£65 per attendee where the buyer can self-manage ordering.",
            "minimum_order": "Usually more retail-led; check case availability, quantity limits and invoice requirements.",
            "branding_personalisation": "Expect limited corporate personalisation; use where recognisable wine gifts matter more than branding.",
            "turnaround": "Allow 1-3 weeks and check delivery slots before assuming event timing will work.",
            "multi_address_delivery": "May be less suited to complex multi-address fulfilment; confirm before relying on it.",
            "ease_score": "6/10",
            "hidden_watchouts": "Retail checkout can be simple for small orders but awkward for large or complex event logistics.",
            "recommendation": "Use as the budget-safe benchmark or self-managed fallback, not the lead route for complex events.",
            "budget_fit": "Indicative: useful as a mainstream retail benchmark for simple self-managed buying.",
            "strengths": "Good reference point for recognisable wine gifts and straightforward UK retail options.",
            "watchouts": "Confirm case availability, substitutions, delivery timing and whether retail checkout supports the required order size.",
            "questions_to_ask": "Can you support the quantity, delivery timing, substitutions and VAT invoice needs for this order?",
        },
    ]


def supplier_directory_sections() -> list[dict]:
    section_ids = {
        "Wine merchants": ["majestic", "laithwaites", "virgin-wines", "waitrose-cellar"],
        "Hampers and corporate gifting": ["fortnum-mason", "marks-spencer-corporate", "waitrose-cellar", "john-lewis-hampers"],
        "Event wine and larger orders": ["majestic-commercial", "majestic", "virgin-wines", "laithwaites", "waitrose-cellar"],
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
    sparkling_fit = supplier["category"] in {"champagne_sparkling", "english_sparkling"} or supplier_has_commercial_term(
        supplier,
        "champagne",
    )
    if req.gift_style == "sparkling" and sparkling_fit:
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
    for supplier in items:
        if not is_real_supplier(supplier):
            continue
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
        if len(shortlist) >= 5:
            break
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
        "Majestic Commercial",
        "Majestic Corporate Gifts",
        "Virgin Wines Corporate",
        "Laithwaites Corporate Wine Gifts",
        "Waitrose Cellar",
    ]
    if req.format in {"virtual", "hybrid"}:
        supplier_routes.append("Virtual tasting pack route")
    supplier_routes = list(dict.fromkeys(supplier_routes))
    recommendation_summary = [
        "Best overall route: Majestic Commercial for event quantities, delivery planning and business order support.",
        "Premium option: Laithwaites Corporate Wine Gifts where presentation and a more polished wine-gift route matter.",
        "Budget-conscious option: Waitrose Cellar as a recognised UK retail benchmark if the event can be self-managed.",
        "Wine-only alternative: Majestic Corporate Gifts for straightforward corporate wine options or staff rewards.",
        "Approachable staff route: Virgin Wines Corporate for friendly mixed-case or branded gift-style options.",
    ]
    event_planning_considerations = [
        f"Plan around {req.attendee_count} expected attendees, not invitees, and keep an alcohol-free route visible from the start.",
        "Use modest pours and a clear finish time so the event remains workplace-safe and client-appropriate.",
        "Ask suppliers to separate wine/packs, host fees, delivery, VAT, food, venue costs and optional extras in writing.",
    ]
    delivery_logistics_reminders = [
        "Confirm whether delivery is to one venue, one office or individual attendee addresses.",
        "Ask for delivery windows, tracking, failed-delivery handling and substitution approval before payment.",
        "For virtual or hybrid events, collect attendee addresses early and set a deadline for late additions.",
    ]
    glassware_chilling_reminders = [
        "Confirm who provides glassware, chilling space, ice, disposal and service support.",
        "If the venue controls drinks service, check corkage, minimum spend and service charges before buying externally.",
        "For office events, assign someone to receive delivery and manage storage before attendees arrive.",
    ]
    alcohol_free_considerations = [
        "Ask for alcohol-free sparkling, beer or adult soft drink alternatives that feel intentional rather than an afterthought.",
        "Keep alcohol-free choices in the main attendee communication so people do not have to disclose preferences publicly.",
    ]
    event_timing_considerations = [
        "Start supplier conversations 3-6 weeks before the event, longer for December, branded items or virtual packs.",
        "Set internal approval before the supplier cut-off date, not on the event week.",
        "Send attendee instructions after supplier confirmation, with start time, finish time, food details and responsible-drinking expectations.",
    ]
    event_etiquette_tips = [
        "Keep the format guided, paced and optional enough for mixed wine knowledge levels.",
        "For client entertainment, prioritise polish and conversation over novelty or heavy alcohol consumption.",
        "Avoid making wine knowledge a test; a beginner-friendly tone is usually safer for business events.",
    ]
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
        "event_recommendation_summary": recommendation_summary,
        "event_planning_considerations": event_planning_considerations,
        "delivery_logistics_reminders": delivery_logistics_reminders,
        "glassware_chilling_reminders": glassware_chilling_reminders,
        "alcohol_free_considerations": alcohol_free_considerations,
        "event_timing_considerations": event_timing_considerations,
        "event_etiquette_tips": event_etiquette_tips,
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
        "supplier_links_note": "Use the supplier buttons as planning starting points. ClientCellar does not confirm stock, pricing, delivery, availability or supplier quotes.",
        "what_to_avoid": avoid,
        "supplier_enquiry_email": {"subject": subject, "body": body},
        "internal_approval_summary": internal_approval_summary,
        "internal_invite_copy": invite,
        "next_steps": [
            "Confirm budget owner, date options, attendee count and any dietary or alcohol-free requirements.",
            "Open with Majestic Commercial, then benchmark against one corporate wine route and one retail fallback.",
            "Ask shortlisted suppliers for itemised pricing, VAT, availability, delivery, substitutions and event support details.",
            "Confirm lead times, cancellation terms, venue corkage, chilling/glassware ownership and alcohol-free handling in writing.",
            "Choose the route with the clearest operational ownership, not just the lowest bottle price.",
            "Share joining instructions, start time, finish time, food details and responsible-drinking expectations.",
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
        if is_gift:
            return gift_supplier_comparison_rows()
        return event_supplier_comparison_rows()

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
                "supplier_id": "majestic-commercial" if is_event else "majestic",
                "supplier": "Majestic Commercial" if is_event else "Majestic Corporate Gifts",
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
                "supplier_id": "virgin-wines" if is_event else "marks-spencer-corporate",
                "supplier": "Virgin Wines Corporate" if is_event else "M&S Hampers",
                "supplier_type": "Corporate wine gifts and staff rewards" if is_event else "Corporate hamper supplier",
                "product_package": "Corporate gifts or mixed-case route" if is_event else "Wine hamper or alternative hamper",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask about branded gifts, message options and packaging" if is_event else "Gift message and packaging options",
                "lead_time": "Begin supplier contact 2-3 weeks before dispatch; longer in seasonal peaks.",
                "pros": "Approachable corporate gifting route for staff rewards, branded gifts and mixed-case options." if is_event else "Can combine wine with food, packaging and gift messaging.",
                "risks": "Confirm delivery timing, substitutions, branding options and whether the format fits the event use case." if is_event else "Check allergens, substitutions, breakage and delivery coverage.",
                "decision": "Use as a practical alternative to benchmark corporate gift and event-adjacent options." if is_event else "Useful fallback if single-bottle gifting feels too narrow.",
                "best_for": "Staff rewards, approachable corporate gifts and mixed-case options" if is_event else "Reducing taste risk and improving presentation",
                "budget_fit": "Good mainstream corporate comparison route." if is_event else "Useful when one bottle may feel too narrow.",
                "strengths": "Approachable corporate gifting route for staff rewards, branded gifts and mixed-case options." if is_event else "Can combine wine with food, packaging and gift messaging.",
                "watchouts": "Confirm delivery timing, substitutions, branding options and whether the format fits the event use case." if is_event else "Check allergens, substitutions, breakage and delivery coverage.",
                "questions_to_ask": "Can you support the required quantity, timing, gift format, delivery needs and alcohol-free alternatives?" if is_event else "Can you provide alcohol-free or food-only alternatives for unsuitable recipients?",
            },
            {
                "supplier_id": "laithwaites" if is_event else "local-independent-wine-merchant",
                "supplier": "Laithwaites Corporate Wine Gifts" if is_event else "Local independent wine merchant",
                "supplier_type": "Corporate wine gifts" if is_event else "Local independent wine merchant",
                "product_package": "Corporate wine gift route" if is_event else "Merchant-led wine gift route",
                "unit_price": "Indicative: request written unit pricing with VAT treatment.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask about presentation, gift notes and corporate order support" if is_event else "Likely limited; confirm directly",
                "lead_time": "Begin supplier contact 1-3 weeks before dispatch and keep a backup option.",
                "pros": "Established corporate wine gifting route with presentation-led options." if is_event else "Advice-led recommendations and more personal bottle selection.",
                "risks": "Confirm bulk handling, substitutions, delivery cut-offs and VAT invoice support." if is_event else "May have lighter multi-address delivery and corporate admin tooling.",
                "decision": "Use as a polished wine-gift comparison route for corporate buyers." if is_event else "Best reserved for VIP or advice-led recipients.",
                "best_for": "Established corporate wine gifts and premium presentation" if is_event else "VIP recipients and more personal recommendations",
                "budget_fit": "Useful when presentation and corporate support matter." if is_event else "Often useful for higher-touch comparison.",
                "strengths": "Established corporate wine gifting route with presentation-led options." if is_event else "Advice-led recommendations and more personal bottle selection.",
                "watchouts": "Confirm bulk handling, substitutions, delivery cut-offs and VAT invoice support." if is_event else "May have lighter multi-address delivery and corporate admin tooling.",
                "questions_to_ask": "Can you support business quantities, VAT invoices, delivery timing, gift messages and substitutions?" if is_event else "Can you support business orders, VAT receipts, multiple addresses and message inserts?",
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
    if is_event:
        preview["supplier_comparison"] = event_supplier_comparison_rows()
    else:
        preview["supplier_comparison"] = gift_supplier_comparison_rows()
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
    "ClientCellar recommendations are editorially selected. Some supplier links may be affiliate or sponsored links where available, "
    "which means ClientCellar may earn a commission if you choose to buy through them at no extra cost to you. "
    "Our aim is to keep recommendations useful, relevant and transparent."
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
        "name": "Laithwaites Corporate Wine Gifts",
        "url": configured_supplier_url("laithwaites"),
        "note": "Corporate wine gifts page for established business gifting, presentation and bulk enquiries.",
        "url_purpose": "Corporate wine gifts page",
        "url_checked_date": "2026-05-10",
        "is_affiliate": bool(configured_supplier_affiliate_url("laithwaites")),
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


def enhanced_guide(
    *,
    title: str,
    h1: str,
    description: str,
    intro: str,
    hero_bullets: list[str],
    opening_heading: str,
    opening: list[str],
    best_fit_table: dict,
    article_sections: list[dict],
    faqs: list[dict],
    related: list[str],
    cta: str,
    cta_heading: str,
    cta_text: str,
    cta_url: str = "/gift-planner",
    merchant_links: list[dict] | None = None,
) -> dict:
    hero_summary = []
    for item in hero_bullets:
        label, _, text = item.partition(":")
        hero_summary.append({"label": label.strip() or "Note", "text": text.strip() or item})
    return {
        "enhanced": True,
        "title": title,
        "h1": h1,
        "description": description,
        "intro": intro,
        "hero_bullets": hero_bullets,
        "hero_summary": hero_summary,
        "opening_heading": opening_heading,
        "opening": opening,
        "best_fit_heading": "Best fit comparison",
        "best_fit_table": best_fit_table,
        "article_sections": article_sections,
        "audience": hero_bullets,
        "budget": [],
        "best_for": [],
        "approaches": [],
        "considerations": [],
        "avoid": [],
        "checklist": [],
        "faqs": faqs,
        "cta": cta,
        "cta_url": cta_url,
        "cta_heading": cta_heading,
        "cta_text": cta_text,
        "rail_heading": "Turn this into a brief",
        "rail_text": "Use the free planner to turn the recipient, occasion and budget into a practical supplier direction.",
        "related": related,
        "affiliate": True,
        "affiliate_disclosure": PUBLISHER_DISCLOSURE,
        "merchant_links": merchant_links or DEFAULT_MERCHANT_LINKS,
    }


GUIDES.update(
    {
        "corporate-wine-gifts-uk": enhanced_guide(
            title="Corporate Wine Gifts UK: Thoughtful Client Gift Ideas",
            h1="Corporate Wine Gifts UK: How to Send Something That Feels Thoughtful, Not Lazy",
            description="A practical UK guide to choosing corporate wine gifts that feel thoughtful, appropriate and useful — from mixed cases to Champagne, hampers and team gifts.",
            intro="Wine still works as a corporate gift, but only when it feels considered. This guide explains how to choose a bottle, case or hamper that suits the client, the occasion and the relationship — without looking like a rushed spreadsheet exercise.",
            hero_bullets=[
                "Best for: client thank-yous, Christmas gifts, project milestones and senior relationships",
                "Typical budget: £40–£150, depending on relationship and context",
                "Avoid: one random bottle for a whole team, over-packaged weak wine, gifts with no note",
            ],
            opening_heading="The bit people usually get wrong",
            opening=[
                "The best corporate wine gift is not always the most expensive bottle. It is the one that feels like someone has actually thought about the recipient.",
                "For most UK client gifts, that means choosing something safe, polished and easy to enjoy: a good mixed wine case, a Champagne or English sparkling wine gift, or a food-and-wine hamper with clear provenance.",
                "Where people get it wrong is treating wine gifting like a box-ticking exercise. A random bottle of red in a wooden box may technically be a gift, but it rarely feels personal. The goal is not to show off your wine knowledge. The goal is to make the recipient feel valued without making things awkward.",
            ],
            best_fit_table={
                "headers": ["Situation", "Good choice", "Why it works", "Watch out for"],
                "rows": [
                    ["Senior client", "Champagne, English sparkling or premium mixed case", "Polished without being too personal", "Avoid looking flashy or excessive"],
                    ["Client team", "Mixed case or food-and-wine hamper", "Easier to share", "One bottle creates awkwardness"],
                    ["Project thank-you", "Sparkling wine or curated case", "Connects to a milestone", "Add a proper note"],
                    ["Christmas gift", "Seasonal case or hamper", "Useful and timely", "Order early and avoid generic hampers"],
                ],
            },
            article_sections=[
                {
                    "id": "why-wine-works",
                    "heading": "Why wine still works as a corporate gift",
                    "paragraphs": [
                        "Wine can feel more personal than branded merchandise and easier to share than many luxury gifts. It works at home, in the office, after a project, or as part of a team celebration.",
                        "But poor wine with shiny packaging feels lazy. Thoughtful beats expensive, every time. A gift should not create a problem for the person receiving it.",
                    ],
                    "bullets": ["More personal than merchandise.", "Easier to share than many luxury gifts.", "Useful across home, office, celebration and team settings.", "Poor wine with glossy packaging can work against you."],
                    "editorial_note": "The safest gift is often not the showiest one. A good mixed case with a proper note usually beats a flashy bottle chosen in a hurry.",
                },
                {
                    "id": "budget",
                    "heading": "How much should you spend?",
                    "paragraphs": ["The sweet spot for many UK corporate wine gifts is £50–£100. Below that, choose carefully and avoid overblown packaging. Above that, think about whether the gift still feels appropriate."],
                    "table": {
                        "headers": ["Budget", "Best use", "Advice"],
                        "rows": [
                            ["£25–£40", "Small thank-you", "Keep it simple and honest; do not pretend it is luxury"],
                            ["£40–£75", "Good individual client gift", "Strong range for a bottle, pair or small hamper"],
                            ["£75–£150", "Senior client or warmer relationship", "Consider a proper case or premium hamper"],
                            ["£150+", "Key account or team gift", "Check policies and make sure it feels appropriate"],
                        ],
                    },
                },
                {
                    "id": "styles",
                    "heading": "Red, white, sparkling or mixed case?",
                    "paragraphs": [
                        "A mixed case is usually safest when taste is unknown. Sparkling works when the moment is celebratory. Red can be riskier unless you know they like it, and white is useful for summer or lighter gifting.",
                        "Non-alcoholic alternatives matter. If you are sending to a mixed workplace group, make the alternative feel just as considered as the wine option.",
                    ],
                },
                {
                    "id": "note",
                    "heading": "The note matters more than people think",
                    "paragraphs": ["This is where a perfectly decent gift becomes a proper client gesture. Keep it specific, human and free of sales language."],
                    "messages": [
                        {"label": "Avoid", "text": "Please accept this gift as a token of our appreciation."},
                        {"label": "Better", "text": "Thanks again for your support on the project this year. We really enjoyed working with you and hope this gives you something nice to open over Christmas."},
                        {"label": "Better", "text": "A small thank-you for helping get the launch over the line. We really appreciated the pace, patience and good humour from your team."},
                    ],
                    "editorial_note": "A specific note can make even a modest gift feel thoughtful. Generic wording makes even a good bottle feel like admin.",
                },
                {
                    "id": "mistakes",
                    "heading": "Common mistakes",
                    "bullets": [
                        "Sending one bottle to a whole team.",
                        "Choosing wine you personally like instead of something broadly useful.",
                        "Overdoing the packaging so the contents feel weak.",
                        "Leaving delivery too late.",
                        "Forgetting alcohol policies and acceptance limits.",
                    ],
                    "note": "If you are unsure, choose a safer supplier route and ask for alternatives before ordering.",
                },
            ],
            faqs=[
                {"q": "What is a good corporate wine gift in the UK?", "a": "A mixed case, sparkling wine gift, Champagne route or food-and-wine hamper can all work. The best choice depends on recipient suitability, budget, relationship and delivery practicalities."},
                {"q": "How much should I spend on a client wine gift?", "a": "Many UK business buyers sit around £50–£100 for a polished client gift, but internal policy and relationship context matter more than a universal number."},
                {"q": "Is wine still appropriate as a corporate gift?", "a": "Yes, when alcohol is suitable for the recipient and the gift is proportionate. Keep alcohol-free or hamper alternatives available where preferences are unclear."},
                {"q": "Is Champagne better than wine for corporate gifting?", "a": "Champagne can signal celebration, but English sparkling, a mixed case or a hamper may be more appropriate for some clients."},
                {"q": "Should I send one bottle or a case?", "a": "One bottle can work for an individual. For teams or shared offices, a case or hamper usually feels less awkward."},
            ],
            related=["client-wine-gifts", "best-wine-gifts-under-50", "christmas-corporate-wine-gifts"],
            cta="Build my wine gift brief",
            cta_heading="Need a corporate wine gift that does not feel generic?",
            cta_text="Use ClientCellar to build a quick wine gift brief. Tell us who the gift is for, your budget and the occasion, and we will help you narrow the options and supplier direction.",
        ),
        "client-wine-gifts": enhanced_guide(
            title="Client Wine Gifts: How to Choose a Better Bottle, Case or Hamper",
            h1="Client Wine Gifts That Feel Personal Without Getting Weird",
            description="How to choose client wine gifts that feel personal, polished and appropriate — including ideas by budget, relationship type and occasion.",
            intro="A good client wine gift should feel thoughtful, not overfamiliar. This guide helps you choose something that suits the relationship — whether you are thanking a long-term client, marking a deal, or sending a small end-of-year gift.",
            hero_bullets=[
                "Best for: relationship-building, thank-yous and account management",
                "Typical budget: £35–£120",
                "Avoid: gifts that feel too intimate, too cheap, or too obviously bulk-bought",
            ],
            opening_heading="Start with the relationship, not the bottle",
            opening=[
                "The best client wine gifts usually sit in the middle ground: generous, but not excessive; personal, but not too familiar; interesting, but not risky.",
                "If you know the client well, choose around their taste or the moment. If you do not, choose around usefulness: sparkling wine, a balanced mixed case, or a wine-and-food gift that can be shared.",
                "The note is what makes it feel like a client gift rather than a transaction.",
            ],
            best_fit_table={
                "headers": ["Relationship", "Best gift style", "Why"],
                "rows": [
                    ["New client", "Smart bottle or small mixed pair", "Thoughtful without overdoing it"],
                    ["Long-term client", "Mixed case or premium hamper", "Recognises the relationship"],
                    ["Senior stakeholder", "Champagne or English sparkling", "Polished and easy to understand"],
                    ["Client team", "Mixed case or hamper", "Shareable and less awkward"],
                    ["Warm prospect", "Modest thank-you gift", "Avoid anything that feels like inducement"],
                ],
            },
            article_sections=[
                {
                    "id": "relationship-first",
                    "heading": "Start with the relationship, not the wine",
                    "paragraphs": ["Do not overthink the grape variety before you know the role the gift has to play. A new client, a long-standing client and a senior stakeholder need different levels of warmth."],
                    "bullets": ["New client: safer, polished, not too expensive.", "Long-standing client: more personal and better matched to the moment.", "Senior stakeholder: elegant and simple.", "Wider team: shareable.", "Prospect: be careful; avoid anything that feels like pressure."],
                },
                {
                    "id": "less-generic",
                    "heading": "Make it feel less generic",
                    "paragraphs": ["Small details do most of the work. Reference the project or milestone, choose a supplier route with a story, and add a proper note."],
                    "bullets": ["Avoid mass-market hamper language.", "Choose packaging that feels current, not corporate-catalogue dated.", "Use a note that sounds like a person wrote it."],
                    "editorial_note": "A client gift should feel like it came from the relationship, not the marketing cupboard. The note is usually where that feeling is made.",
                },
                {
                    "id": "when-not",
                    "heading": "When not to send wine",
                    "paragraphs": ["Wine is not always the right answer. If alcohol is inappropriate, policies are strict, the relationship is too early, or the timing could look like pressure before a decision, pick another route."],
                    "bullets": ["Food hamper.", "Premium tea or coffee.", "Non-alcoholic sparkling.", "Local produce.", "A choice-based gift where the recipient can select an option."],
                },
                {
                    "id": "messages",
                    "heading": "Better message examples",
                    "messages": [
                        {"label": "Project thank-you", "text": "Thank you again for the energy and clarity your team brought to the project. We really enjoyed working with you."},
                        {"label": "End-of-year", "text": "A small thank-you for your support this year. We hope you get a proper pause over the Christmas break."},
                        {"label": "Long-term account", "text": "We really value the relationship and appreciate the trust you have placed in us over the years."},
                        {"label": "Team gift", "text": "A thank-you for the whole team. We appreciated the collaboration and hope this gives you something to share."},
                    ],
                    "editorial_note": "If you cannot say why you are sending the gift in one warm sentence, pause before ordering.",
                },
            ],
            faqs=[
                {"q": "What wine should I send to a client?", "a": "If you know their taste, choose around it. If not, sparkling wine, a balanced mixed case or a wine-and-food hamper is usually safer."},
                {"q": "How much should I spend on a client wine gift?", "a": "A practical range is often £35–£120, depending on relationship value, policy and occasion."},
                {"q": "Is it appropriate to send wine to a client?", "a": "It can be, but check alcohol suitability, timing and any gift acceptance policies first."},
                {"q": "What should I write in a client gift note?", "a": "Mention the relationship or moment briefly. Keep it warm, specific and free of sales pressure."},
                {"q": "What can I send if I am not sure they drink alcohol?", "a": "Choose a food hamper, premium tea or coffee, non-alcoholic sparkling, or another equal-quality alternative."},
            ],
            related=["corporate-wine-gifts-uk", "client-thank-you-wine-gifts", "client-gifting-etiquette-uk"],
            cta="Plan a client wine gift",
            cta_heading="Not sure what to send a client?",
            cta_text="Build a ClientCellar gift brief and get a clearer recommendation based on the relationship, budget and occasion.",
        ),
        "best-wine-gifts-under-50": enhanced_guide(
            title="Best Wine Gifts Under £50: Smart Ideas That Still Feel Generous",
            h1="Best Wine Gifts Under £50 That Do Not Feel Like an Afterthought",
            description="Wine gift ideas under £50 that still feel thoughtful — including sparkling wine, mixed pairs, small hampers and client-safe options.",
            intro="£50 is a good wine gifting budget if you use it properly. The trick is not to pretend you are buying luxury. The trick is to choose something focused, well-presented and genuinely enjoyable.",
            hero_bullets=[
                "Best for: thank-yous, smaller client gifts, birthdays, host gifts and team gestures",
                "Typical budget: £30–£50",
                "Avoid: fake luxury packaging, weak wine in a heavy box, novelty gifts",
            ],
            opening_heading="What £50 can actually do well",
            opening=[
                "Under £50, the best wine gifts are usually a good bottle of sparkling wine, a carefully chosen red or white, a two-bottle gift set, or a small wine-and-food hamper.",
                "Avoid anything that looks like it is trying too hard to be premium. At this budget, simple and well-chosen beats glossy and over-packaged.",
                "If the gift is for a client, keep it safe and polished. If it is for a friend or host, you can be a little more playful.",
            ],
            best_fit_table={
                "headers": ["Gift idea", "Best for", "Why it works"],
                "rows": [
                    ["English sparkling wine", "Celebrations", "Feels special and current"],
                    ["Two-bottle red/white pair", "Safe gifting", "Gives choice without overspending"],
                    ["Small wine-and-cheese hamper", "More complete gift", "Feels like an evening, not just a bottle"],
                    ["Independent merchant pick", "More personal", "Less generic than supermarket gifting"],
                    ["Good Rioja or Rhône red", "Winter gifts", "Familiar, food-friendly, reliable"],
                    ["Crisp white wine gift", "Summer gifting", "Easy to enjoy and less heavy"],
                ],
            },
            article_sections=[
                {
                    "id": "realistically-buy",
                    "heading": "What £50 can realistically buy",
                    "paragraphs": ["£50 can buy one very decent bottle, two respectable bottles, a small but tasteful hamper, or a sparkling wine gift. It does not usually buy a genuinely premium large hamper."],
                    "editorial_note": "Under £50, restraint helps. Choose one clear idea and execute it well.",
                },
                {
                    "id": "avoid",
                    "heading": "What to avoid under £50",
                    "bullets": ["Giant hampers with too many cheap fillers.", "Wooden boxes that cost more than the wine deserves.", "Novelty wine accessories.", "Ultra-obscure bottles unless you know the person.", "Misleading luxury labels."],
                    "note": "At this price, confidence comes from restraint. Bigger is not always better.",
                },
                {
                    "id": "recipient",
                    "heading": "Best under £50 by recipient",
                    "table": {
                        "headers": ["Recipient", "Best choice"],
                        "rows": [
                            ["Client", "Sparkling, two-bottle gift or polished small hamper"],
                            ["Friend", "More personal bottle or fun mixed pair"],
                            ["Host", "Sparkling, white wine or food-friendly red"],
                            ["Team member", "Small hamper or bottle with note"],
                            ["Wine enthusiast", "Independent merchant recommendation"],
                        ],
                    },
                    "editorial_note": "For client gifting under £50, the best option is usually focused rather than large.",
                },
            ],
            faqs=[
                {"q": "Is £50 enough for a good wine gift?", "a": "Yes. It is enough for a strong bottle, a useful pair, sparkling wine or a compact hamper if you avoid overblown packaging."},
                {"q": "What is the best wine gift under £50?", "a": "For business gifting, sparkling wine, a red/white pair or a compact wine-and-food gift is usually safer than a niche bottle."},
                {"q": "Should I buy one bottle or two bottles under £50?", "a": "One bottle gives quality. Two bottles give choice. For unknown tastes, a pair can be more forgiving."},
                {"q": "Are wine hampers under £50 worth it?", "a": "Some are, but check the actual contents list. Avoid hampers padded with small filler items."},
                {"q": "What should I avoid when buying wine gifts under £50?", "a": "Avoid fake luxury packaging, novelty accessories, weak wine in heavy boxes and gifts that pretend to be more premium than they are."},
            ],
            related=["corporate-wine-gifts-uk", "client-wine-gifts", "wine-gift-hampers-uk"],
            cta="Find a wine gift under £50",
            cta_heading="Want a wine gift under £50 that still feels thoughtful?",
            cta_text="Use ClientCellar to create a quick gift brief and narrow your options by budget, recipient and occasion.",
        ),
        "christmas-corporate-wine-gifts": enhanced_guide(
            title="Christmas Corporate Wine Gifts: Better Ideas for UK Clients and Teams",
            h1="Christmas Corporate Wine Gifts That Do Not Feel Like Everyone Got the Same Thing",
            description="A practical guide to Christmas corporate wine gifts for UK clients, teams and suppliers — including budget advice, timing, messages and safer gift ideas.",
            intro="Christmas corporate gifting is where good intentions often turn into forgettable hampers. This guide helps you choose wine gifts that feel timely, useful and a little more considered.",
            hero_bullets=[
                "Best for: end-of-year client thank-yous, account teams, suppliers and senior contacts",
                "Typical budget: £40–£150",
                "Avoid: late orders, generic hampers, gifts with no message",
            ],
            opening_heading="The Christmas gifting trap",
            opening=[
                "The best Christmas corporate wine gifts are easy to understand, easy to share, and clearly connected to the season.",
                "For individual clients, Champagne, English sparkling wine or a smart mixed pair works well. For teams, a mixed case or food-and-wine hamper is usually better. For senior relationships, choose polish over size.",
                "The mistake is sending something that feels like it came from a procurement list with no thought behind it.",
            ],
            best_fit_table={
                "headers": ["Recipient", "Best option", "Why"],
                "rows": [
                    ["Senior client", "Champagne or English sparkling", "Classic and polished"],
                    ["Client team", "Mixed case or hamper", "Shareable"],
                    ["Supplier partner", "Thoughtful bottle pair", "Warm but not excessive"],
                    ["Remote contact", "Direct-to-home gift", "More reliable than office delivery"],
                    ["Large account", "Curated case", "Feels more generous"],
                ],
            },
            article_sections=[
                {
                    "id": "not-just-wine",
                    "heading": "Christmas gifting is not just about the wine",
                    "paragraphs": ["Timing matters. Message matters. Delivery address matters. Team versus individual matters. Some offices close early, and a lovely gift arriving at an empty reception desk is not a lovely gift anymore."],
                    "editorial_note": "Christmas gifts fail when they arrive late, land in an empty office, or feel detached from the relationship.",
                },
                {
                    "id": "when-to-order",
                    "heading": "When to order",
                    "paragraphs": ["Start planning in November if you can, especially for larger lists or branded notes. Avoid leaving it until the final delivery week, and confirm whether gifts should go to office or home addresses."],
                    "bullets": ["Ask suppliers about their own order cut-off dates.", "Confirm address data before committing.", "Build in a fallback for substitutions.", "Do not assume a normal delivery slot will still be available."],
                },
                {
                    "id": "messages",
                    "heading": "Message examples",
                    "messages": [
                        {"label": "Formal client", "text": "Thank you for your partnership this year. We wish you and your team a restful Christmas and a strong start to the new year."},
                        {"label": "Warmer client", "text": "It has been a real pleasure working together this year. A small festive thank-you from all of us."},
                        {"label": "Team thank-you", "text": "A Christmas thank-you for the whole team. We appreciated the collaboration, pace and good humour this year."},
                        {"label": "Supplier or partner", "text": "Thank you for your support and reliability this year. We hope you enjoy this over the festive break."},
                    ],
                    "editorial_note": "The best Christmas notes are short, specific and seasonal without sounding like a mail merge.",
                },
                {
                    "id": "mistakes",
                    "heading": "Avoid these Christmas mistakes",
                    "bullets": ["Sending alcohol to someone who does not drink.", "Sending to an empty office.", "Too much branding.", "Too many cheap hamper fillers.", "Not checking gift policies."],
                },
            ],
            faqs=[
                {"q": "What are good Christmas wine gifts for clients?", "a": "Champagne, English sparkling, a smart mixed pair, a seasonal case or a food-and-wine hamper can all work when matched to the recipient."},
                {"q": "When should I order corporate Christmas wine gifts?", "a": "Start supplier conversations well before December for larger orders. Confirm the supplier’s current cut-off dates directly."},
                {"q": "Is Champagne a good corporate Christmas gift?", "a": "It can be, especially for senior or celebratory relationships, but sparkling wine, hampers or mixed cases may be more practical."},
                {"q": "What should I send to a client team at Christmas?", "a": "A mixed case or hamper is usually more shareable than one bottle addressed to a whole team."},
                {"q": "What should I write in a Christmas client gift message?", "a": "Thank them for the partnership or project, keep it warm, and avoid heavy sales language."},
            ],
            related=["corporate-wine-gifts-uk", "client-wine-gifts", "wine-gift-hampers-uk"],
            cta="Plan Christmas wine gifts",
            cta_heading="Planning Christmas wine gifts for clients?",
            cta_text="Build a ClientCellar gift brief and get a clearer plan for who you are buying for, what to spend and what kind of supplier to use.",
        ),
        "wine-gift-hampers-uk": enhanced_guide(
            title="Wine Gift Hampers UK: How to Choose One That Is Actually Worth Sending",
            h1="Wine Gift Hampers UK: How to Choose One That Is Actually Worth Sending",
            description="A practical UK guide to choosing wine gift hampers that feel generous rather than generic — including what to look for, what to avoid and who they suit best.",
            intro="Wine hampers can be excellent gifts, but they can also be padded with things nobody really wants. This guide helps you spot the difference between a hamper that feels generous and one that just looks big in a photo.",
            hero_bullets=[
                "Best for: client teams, Christmas gifts, host gifts and shared occasions",
                "Typical budget: £45–£150",
                "Avoid: cheap filler products, weak wine, oversized packaging",
            ],
            opening_heading="Bigger is not always better",
            opening=[
                "A good wine hamper should feel like a complete, enjoyable gift: wine you would actually want to open, food that makes sense with it, and packaging that feels polished without becoming the main event.",
                "The best hampers usually have fewer, better items. The worst ones look impressive online but rely on cheap filler products, tiny jars and average wine.",
                "If you are buying for a client or team, choose something easy to share and not too quirky.",
            ],
            best_fit_table={
                "headers": ["Occasion", "Best hamper style", "Why"],
                "rows": [
                    ["Client thank-you", "Wine plus savoury snacks", "Polished and useful"],
                    ["Christmas", "Wine, cheese, crackers and sweet items", "Seasonal and shareable"],
                    ["Team gift", "Larger mixed hamper", "Easier to split"],
                    ["Host gift", "Smaller wine-and-food hamper", "Feels generous but not excessive"],
                    ["Senior client", "Premium but restrained hamper", "Elegant rather than bulky"],
                ],
            },
            article_sections=[
                {
                    "id": "what-makes-good",
                    "heading": "What makes a good wine hamper?",
                    "paragraphs": ["Look beyond the hero photo. Wine quality, food pairing, quantity versus quality, packaging, delivery reliability and clear dietary information all matter."],
                    "bullets": ["Wine you would actually want to open.", "Food that makes sense with the bottle.", "Clear allergen and dietary information.", "Packaging that protects the gift rather than stealing the budget.", "Suitability for one person versus a team."],
                    "editorial_note": "The contents list matters more than the basket size. A smaller hamper with better items usually feels more generous.",
                },
                {
                    "id": "filler-problem",
                    "heading": "The filler problem",
                    "paragraphs": ["Big hampers can be misleading. More items does not always mean better, especially if the contents list is full of tiny jars, generic biscuits, cheap chocolate and weak wine."],
                    "note": "Always read the actual contents list. A smaller hamper with better items is usually the more generous gift.",
                },
                {
                    "id": "hamper-vs-case",
                    "heading": "Wine hamper vs mixed wine case",
                    "paragraphs": ["A hamper is more of an experience. A mixed case is better if the recipient mainly cares about wine. Hampers are better for sharing; cases are better for wine enthusiasts."],
                    "bullets": ["Choose a hamper when taste is unknown or the gift needs to be shared.", "Choose a mixed case when the recipient is wine-friendly and likely to enjoy the bottles.", "For corporate gifts, hampers can be safer if individual preferences are unclear."],
                    "editorial_note": "If the recipient mainly cares about wine, a mixed case may beat a hamper. If the gift needs to be shared, the hamper has the edge.",
                },
                {
                    "id": "check-before-buying",
                    "heading": "What to check before buying",
                    "bullets": ["Delivery date and supplier cut-off.", "Whether it can go to home or office.", "Whether a gift message is included.", "Alcohol policy and suitability.", "Dietary restrictions and allergens.", "Exact contents and substitution rules."],
                },
            ],
            faqs=[
                {"q": "Are wine gift hampers worth it?", "a": "They can be, if the wine and food are genuinely useful. Avoid hampers that rely on size and filler products."},
                {"q": "What should be in a good wine hamper?", "a": "A good hamper should include drinkable wine, sensible food pairings, clear contents, useful packaging and any dietary information the recipient needs."},
                {"q": "How much should I spend on a wine hamper?", "a": "Many useful wine hampers sit around £45–£150, depending on recipient, occasion and presentation level."},
                {"q": "Are wine hampers good corporate gifts?", "a": "Yes, especially for teams or unknown preferences, but check alcohol suitability and gift policies first."},
                {"q": "Is a wine hamper better than a mixed case?", "a": "A hamper is better for sharing and mixed tastes. A mixed case is better for someone who mainly values the wine."},
            ],
            related=["corporate-wine-gifts-uk", "client-wine-gifts", "best-wine-gifts-under-50"],
            cta="Build my wine gift brief",
            cta_heading="Need a wine hamper that does not feel generic?",
            cta_text="Use ClientCellar to create a quick gift brief and compare whether a hamper, mixed case or single bottle is the better fit.",
        ),
    }
)

GUIDES.update(
    {
        "best-client-wine-gifts": enhanced_guide(
            title="Best Client Wine Gifts: Ideas That Feel Thoughtful, Not Transactional",
            h1="Best Client Wine Gifts: Ideas That Feel Thoughtful, Not Transactional",
            description="Relationship-led client wine gift ideas for UK businesses, including budgets, note examples, policy checks and safer alternatives.",
            intro="Client gifts sit in a slightly awkward space: they need to be generous enough to mean something, but not so grand that they feel like a sales tactic. Wine can work well, as long as the choice fits the relationship.",
            hero_bullets=["Best for: account teams, founders, agencies and professional services firms", "Typical budget: £35–£150", "Avoid: gifts that feel too cheap, too flashy, too personal or too bulk-bought"],
            opening_heading="The awkward bit nobody says out loud",
            opening=[
                "A client wine gift can fail in four different ways before it is even opened: it can look cheap, look excessive, feel too personal, or feel as if everyone on a spreadsheet got the same thing.",
                "The safest gifts are not bland. They are appropriate. They match the relationship, carry a short human note, and do not make the recipient wonder whether they are allowed to accept it.",
            ],
            best_fit_table={"headers": ["Relationship", "Good route", "Why it fits"], "rows": [["New client", "Smart bottle or small pair", "Warm without overdoing it"], ["Long-standing client", "Mixed case or premium hamper", "Acknowledges the relationship"], ["Senior stakeholder", "Champagne or English sparkling", "Polished and easy to understand"], ["Client team", "Mixed case or shareable hamper", "Avoids the one-bottle problem"], ["Warm prospect", "Modest thank-you", "Keeps the tone careful"]]},
            article_sections=[
                {"id": "relationship", "heading": "Choose by relationship, not by shelf appeal", "paragraphs": ["For a newer client, keep the gift restrained. For a long-standing client, you can show more thought. For a team, make it shareable. For a prospect, be careful with timing and value."], "editorial_note": "There is a fine line between generous and awkward. If the gift needs explaining, it may be the wrong gift."},
                {"id": "budget", "heading": "Budget guidance that does not pretend every client is the same", "table": {"headers": ["Budget", "Best use", "Watch"], "rows": [["£25–£40", "Small thank-you", "Presentation and note matter"], ["£40–£75", "Solid client gift", "Good range for pairs, sparkling or compact hampers"], ["£75–£150", "Priority relationship", "Check policy and make the note specific"], ["£150+", "Key account or team", "Document the reason and approval"]]}},
                {"id": "note", "heading": "What to write on the card", "paragraphs": ["The note should sound like it came from a person who knows why the gift is being sent."], "messages": [{"label": "Project close", "text": "Thank you for the collaboration and pace on the project. We really appreciated working with your team."}, {"label": "Long-term client", "text": "A small thank-you for your continued trust and support. We really value the relationship."}, {"label": "Christmas", "text": "Wishing you and the team a restful Christmas. Thank you for being such a valued client this year."}]},
                {"id": "avoid", "heading": "What I would avoid", "bullets": ["A trophy bottle unless you know the recipient loves wine.", "A large hamper padded with filler.", "Anything sent during a sensitive procurement decision.", "Generic notes that sound like a template."], "note": "If you are unsure, choose a smaller, better-considered gift and write a clearer note."},
            ],
            faqs=[
                {"q": "What is the best client wine gift?", "a": "For unknown tastes, sparkling wine, a mixed case or a wine-and-food hamper is usually safer than a niche bottle."},
                {"q": "How much should I spend on a client wine gift?", "a": "Many UK businesses use £40–£100 for polished client gifts, with higher budgets reserved for priority relationships and policy-approved occasions."},
                {"q": "Should I send wine to a client team?", "a": "A mixed case or hamper is usually better than one bottle if the gift is for a team."},
                {"q": "What should I write in a client gift note?", "a": "Mention the project, relationship or moment briefly. Keep it warm, specific and not sales-led."},
                {"q": "What if I am not sure they drink alcohol?", "a": "Use a hamper, alcohol-free sparkling, coffee, tea or another equal-quality alternative."},
            ],
            related=["client-wine-gifts", "corporate-wine-gifts-uk", "client-gifting-etiquette-uk"],
            cta="Plan a client gift",
            cta_heading="Want a client gift that feels considered?",
            cta_text="Use the gift planner to turn recipient type, budget and occasion into a practical supplier direction.",
        ),
        "best-wine-gifts-under-25": enhanced_guide(
            title="Best Wine Gifts Under £25: Small Gifts That Still Feel Considered",
            h1="Best Wine Gifts Under £25: Small Gifts That Still Feel Considered",
            description="Honest wine gift ideas under £25, including single bottles, small thank-yous, host gifts and what to avoid.",
            intro="£25 is not a luxury budget. That is fine. The mistake is pretending it is. Used well, it can still buy a useful bottle, a small thank-you, or a simple host gift that feels considered.",
            hero_bullets=["Best for: modest thank-yous, host gifts and small team gestures", "Typical budget: £15–£25 before delivery", "Avoid: novelty sets, fake-premium boxes and weak wine in heavy packaging"],
            opening_heading="Be honest about the budget",
            opening=["At this level, the gift works when it is simple. One good bottle beats a cheap three-piece set with accessories nobody wants.", "For client gifting, £25 can be acceptable for a small thank-you, but the note and presentation need to carry some of the weight."],
            best_fit_table={"headers": ["Use case", "Best choice", "Avoid"], "rows": [["Host gift", "Sparkling or crisp white", "Novelty labels"], ["Small client thank-you", "Classic single bottle", "Pretending it is luxury"], ["Team gesture", "Simple bottle plus note", "Alcohol-only if preferences are unknown"], ["Friend or colleague", "More personal style", "Over-packaged cheap sets"]]},
            article_sections=[
                {"id": "can-buy", "heading": "What £25 can and cannot buy", "paragraphs": ["It can buy a decent single bottle, a small sparkling option, or a straightforward supermarket pick. It usually cannot buy a convincing premium gift once delivery and packaging are included."], "editorial_note": "The safest option is not always the cheapest-looking one. Keep it simple and choose something drinkable."},
                {"id": "supermarket", "heading": "When supermarket wine is acceptable", "paragraphs": ["Supermarket wine is acceptable when the gift is informal, the bottle is well chosen, and you are not trying to make it look like a premium corporate gesture."], "bullets": ["Choose familiar, food-friendly styles.", "Avoid novelty labels.", "Add a proper note if it is a business thank-you."]},
                {"id": "avoid", "heading": "What to avoid", "bullets": ["Bad mini bottle sets.", "Novelty glasses.", "Packaging that costs more than it should.", "Obscure bottles for people whose taste you do not know."], "note": "Small gifts can be charming. Small gifts pretending to be grand usually are not."},
            ],
            faqs=[
                {"q": "Is £25 enough for a wine gift?", "a": "Yes, for a simple bottle or modest thank-you. It is not usually enough for a premium corporate gift once delivery is included."},
                {"q": "Should I buy a gift set under £25?", "a": "Usually only if the wine is decent. Avoid sets where the accessories are doing too much of the selling."},
                {"q": "Can I send a client wine gift under £25?", "a": "It can work for a small gesture, but make the note thoughtful and avoid making the gift look more premium than it is."},
                {"q": "What wine style is safest under £25?", "a": "Sparkling, a classic red, or a crisp white usually works better than a niche bottle."},
            ],
            related=["best-wine-gifts-under-50", "client-wine-gifts", "corporate-wine-gifts-uk"],
            cta="Plan a modest wine gift",
            cta_heading="Need a small gift that still feels thoughtful?",
            cta_text="Use ClientCellar to shape a simple wine gift brief around budget, recipient and occasion.",
        ),
        "best-wine-gifts-under-100": enhanced_guide(
            title="Best Wine Gifts Under £100: Where Wine Gifting Gets Interesting",
            h1="Best Wine Gifts Under £100: Where Wine Gifting Gets Interesting",
            description="How to spend up to £100 well on wine gifts, from premium bottles and mixed cases to hampers and Champagne routes.",
            intro="£100 is a genuinely useful wine gifting budget. It gives you room for a strong bottle, a more interesting pair, a compact case or a hamper that does not rely on filler.",
            hero_bullets=["Best for: priority clients, senior stakeholders and polished Christmas gifts", "Typical budget: £60–£100", "Avoid: expensive-looking gifts with weak contents"],
            opening_heading="Spend the money where the recipient will notice",
            opening=["At this budget, you can choose between depth and breadth: one better bottle, a small mixed case, or a food-and-wine gift that feels complete.", "The wrong move is buying size. The right move is buying confidence: better contents, cleaner presentation and fewer compromises."],
            best_fit_table={"headers": ["Route", "Best for", "Watch"], "rows": [["Premium bottle", "Known wine-friendly recipient", "Taste risk"], ["Mixed case", "Unknown taste but wine-friendly", "Delivery weight"], ["Hamper", "Shared gift or broader appeal", "Filler contents"], ["Champagne", "Celebration or senior contact", "Can feel obvious or showy"]]},
            article_sections=[
                {"id": "one-or-many", "heading": "One premium bottle, mixed case or hamper?", "paragraphs": ["Choose one bottle when you know the recipient will appreciate it. Choose a mixed case when you want safer variety. Choose a hamper when the gift needs to be shared or wine taste is uncertain."], "editorial_note": "This is where people tend to waste money: buying packaging and status instead of usefulness."},
                {"id": "use-cases", "heading": "Best use cases under £100", "bullets": ["Senior client thank-you.", "Christmas gift for a priority account.", "Deal or project milestone.", "Warm referral thank-you.", "Compact team gift." ]},
                {"id": "champagne", "heading": "When to choose Champagne", "paragraphs": ["Champagne works when the moment is celebratory and the relationship can carry the signal. English sparkling or a premium mixed case can feel more thoughtful when Champagne feels too automatic."]},
            ],
            faqs=[
                {"q": "What is the best wine gift under £100?", "a": "A premium bottle, mixed case, English sparkling gift or compact hamper can all work. Choose based on recipient and occasion."},
                {"q": "Is £100 too much for a client gift?", "a": "It depends on policy and relationship context. Higher-value gifts should be proportionate and easy to justify."},
                {"q": "Should I choose Champagne under £100?", "a": "Champagne is good for celebration, but sparkling wine, mixed cases and hampers may be better for some recipients."},
                {"q": "Is a hamper better than wine under £100?", "a": "A hamper is better for sharing; wine is better where the recipient is known to enjoy it."},
            ],
            related=["premium-client-gifts-uk", "luxury-corporate-wine-gifts", "wine-gift-hampers-uk"],
            cta="Plan a premium wine gift",
            cta_heading="Want to spend under £100 well?",
            cta_text="Use the planner to compare bottle, case and hamper routes before you contact suppliers.",
        ),
        "corporate-gift-ideas-for-clients": enhanced_guide(
            title="Corporate Gift Ideas for Clients That Do Not Feel Like Branded Filler",
            h1="Corporate Gift Ideas for Clients That Do Not Feel Like Branded Filler",
            description="Practical UK client gift ideas, including wine, hampers, coffee, experiences, non-alcoholic options and when each route works.",
            intro="Not every client gift needs to be wine. The useful question is: what will feel appropriate, easy to receive and connected to the relationship?",
            hero_bullets=["Best for: teams comparing gift routes before ordering", "Typical budget: £25–£150", "Avoid: branded filler that solves your marketing problem, not the client’s"],
            opening_heading="Start with usefulness",
            opening=["A good client gift should not create work for the person receiving it. That rules out more options than people think.", "Wine fits nicely when the recipient is likely to enjoy it. Hampers, coffee, tea, experiences and alcohol-free gifts can be better when suitability is unclear."],
            best_fit_table={"headers": ["Gift route", "Best when", "Watch"], "rows": [["Wine or sparkling", "Wine-friendly client or celebration", "Alcohol suitability"], ["Food hamper", "Mixed preferences or teams", "Dietary needs"], ["Coffee or tea", "Alcohol is uncertain", "Can feel small if under-presented"], ["Experience", "Closer relationship", "Scheduling friction"], ["Charity-linked gift", "Values-led relationship", "Avoid performative wording"]]},
            article_sections=[
                {"id": "where-wine-fits", "heading": "Where wine fits well", "paragraphs": ["Wine works for client thank-yous, Christmas gifts and milestone moments when the relationship and policy context are clear."], "editorial_note": "ClientCellar is strongest for wine-led gifts, but the best advice sometimes is to choose the non-wine route."},
                {"id": "by-client-type", "heading": "What to choose by client type", "table": {"headers": ["Client type", "Good option"], "rows": [["New client", "Modest polished gift"], ["Long-term account", "Wine, hamper or local gift"], ["Senior stakeholder", "Premium but restrained"], ["Client team", "Shareable hamper or case"], ["Policy-sensitive client", "Food, coffee, tea or no gift"]]}},
                {"id": "avoid", "heading": "What to avoid", "bullets": ["Logo-heavy gifts with no recipient value.", "Alcohol as a default for everyone.", "Overly personal gifts.", "Anything that feels tied to a decision."]},
            ],
            faqs=[
                {"q": "What are good corporate gift ideas for clients?", "a": "Wine, sparkling wine, hampers, premium coffee or tea, experiences and non-alcoholic gifts can all work when matched to the client."},
                {"q": "Are branded gifts a good idea?", "a": "Sometimes, but avoid gifts that feel like promotional filler rather than a thank-you."},
                {"q": "When is wine a good client gift?", "a": "When alcohol is suitable, the relationship is warm enough and the gift is proportionate."},
                {"q": "What should I send if alcohol is unsuitable?", "a": "Food hampers, coffee, tea, alcohol-free sparkling or local produce can be safer."},
            ],
            related=["client-wine-gifts", "corporate-wine-gifts-uk", "non-alcoholic-client-gifts"],
            cta="Compare client gift routes",
            cta_heading="Want a clearer client gift direction?",
            cta_text="Use the planner to turn a broad gift idea into a practical buying route.",
        ),
        "wine-gifts-for-customers": enhanced_guide(
            title="Wine Gifts for Customers: When It Works and When It Does Not",
            h1="Wine Gifts for Customers: When It Works, When It Does Not, and How to Keep It Appropriate",
            description="Guidance for sending wine gifts to customers at scale, including suitability, data, delivery, personalisation and alternatives.",
            intro="Customer gifting is not the same as client gifting. Scale changes the risk: address data, alcohol suitability, delivery exceptions and message tone all matter more.",
            hero_bullets=["Best for: VIP customers, loyalty gestures and small high-value cohorts", "Typical budget: £20–£75 for broad campaigns", "Avoid: alcohol-only campaigns where preferences are unknown"],
            opening_heading="Scale makes everything less forgiving",
            opening=["A bottle sent to one known client is a relationship gesture. A hundred bottles sent to customers is an operation.", "Before choosing wine, check whether the audience is known, whether alcohol is appropriate, and whether delivery data is clean enough to use."],
            best_fit_table={"headers": ["Customer group", "Gift route", "Why"], "rows": [["VIP customers", "Wine, sparkling or hamper", "Relationship value justifies care"], ["Broad customer list", "Choice-based or non-alcohol option", "Safer at scale"], ["Lapsed customers", "Usually avoid wine", "Can feel like pressure"], ["Event attendees", "Follow-up gift or tasting pack", "Context makes it relevant"]]},
            article_sections=[
                {"id": "client-vs-customer", "heading": "Client gifts and customer gifts are different", "paragraphs": ["Client gifts are usually relationship-led. Customer gifts often involve lists, segmentation and operational risk. Treat them differently."], "editorial_note": "If you are buying at scale, do not let the gift create a delivery or privacy problem."},
                {"id": "checks", "heading": "What to check before sending", "bullets": ["Alcohol suitability.", "Consent or appropriate basis for delivery data.", "Home versus business address.", "Failed-delivery handling.", "Alternative gift route.", "Message tone and personalisation."]},
                {"id": "tiers", "heading": "Smaller gifts versus key customer gifts", "paragraphs": ["For broad customer lists, keep the gift modest or choice-led. For VIP customers, a better wine gift or hamper can make sense if the relationship supports it."]},
            ],
            faqs=[
                {"q": "Can businesses send wine gifts to customers?", "a": "Sometimes, but alcohol suitability, delivery data, privacy and message tone need careful review."},
                {"q": "How is a customer gift different from a client gift?", "a": "Customer gifts are often larger-scale and less relationship-specific, so operational and suitability checks matter more."},
                {"q": "What is a safer alternative to wine for customers?", "a": "Choice-based gifts, food hampers, coffee, tea or alcohol-free options may be safer."},
                {"q": "Should customer gifts be personalised?", "a": "Light personalisation can help, but avoid anything that feels intrusive or overfamiliar."},
            ],
            related=["corporate-gift-ideas-for-clients", "client-wine-gifts", "client-gift-policy-checklist"],
            cta="Plan customer wine gifts",
            cta_heading="Thinking about wine gifts for customers?",
            cta_text="Use ClientCellar to shape the route and questions before you contact suppliers.",
        ),
        "luxury-corporate-wine-gifts": enhanced_guide(
            title="Luxury Corporate Wine Gifts: How to Look Generous Without Looking Ridiculous",
            h1="Luxury Corporate Wine Gifts: How to Look Generous Without Looking Ridiculous",
            description="A practical guide to premium and luxury corporate wine gifts, including when to choose Champagne, fine wine, hampers and restrained alternatives.",
            intro="Luxury gifting has more room to impress, and more room to go wrong. The point is not to shout. The point is to make the recipient feel properly considered.",
            hero_bullets=["Best for: senior clients, key accounts and major milestones", "Typical budget: £100–£250+", "Avoid: trophy bottles, showy packaging and gifts that breach policy"],
            opening_heading="Restraint can look more premium than excess",
            opening=["There is a difference between generous and theatrical. A luxury wine gift should feel confident, not desperate to prove its value.", "If the recipient knows wine, choose with care. If they do not, presentation, provenance and ease of enjoyment matter more than rarity."],
            best_fit_table={"headers": ["Route", "Use it when", "Risk"], "rows": [["Champagne", "Celebration is the message", "Can feel obvious"], ["Fine wine", "Taste is known", "May feel too niche"], ["Premium hamper", "Gift will be shared", "Filler risk"], ["Independent merchant case", "Advice matters", "Delivery/admin support may vary"]]},
            article_sections=[
                {"id": "appropriate", "heading": "When luxury is appropriate", "paragraphs": ["Luxury makes sense for long-standing relationships, major milestones and senior contacts where policy allows it. It is less suitable around live negotiations or uncertain gift acceptance rules."], "editorial_note": "The more expensive the gift, the clearer the business reason should be."},
                {"id": "routes", "heading": "Champagne, fine wine or premium hamper?", "bullets": ["Choose Champagne for celebration.", "Choose fine wine for known enthusiasts.", "Choose a premium hamper for shared appeal.", "Choose an advice-led merchant when personal fit matters."]},
                {"id": "avoid", "heading": "What I would avoid", "bullets": ["Trophy bottles chosen for price alone.", "Huge packaging with modest contents.", "Anything that creates policy discomfort.", "Gifts without an itemised invoice or approval trail."]},
            ],
            faqs=[
                {"q": "What counts as a luxury corporate wine gift?", "a": "Usually a premium bottle, Champagne, fine wine, advice-led case or high-quality hamper where presentation and suitability are strong."},
                {"q": "When is a luxury wine gift appropriate?", "a": "For senior relationships, major milestones or key accounts where policy and timing are appropriate."},
                {"q": "Is fine wine a good corporate gift?", "a": "It can be if the recipient is known to appreciate wine. Otherwise, sparkling or a premium hamper may be safer."},
                {"q": "Should luxury gifts be approved internally?", "a": "Yes, meaningful-value gifts should be checked against internal policies and recorded."},
            ],
            related=["premium-client-gifts-uk", "best-wine-gifts-under-100", "client-gift-policy-checklist"],
            cta="Plan a luxury wine gift",
            cta_heading="Need a premium gift that still feels appropriate?",
            cta_text="Use the planner to shape a clear brief before approaching suppliers.",
        ),
        "thank-you-wine-gifts": enhanced_guide(
            title="Thank You Wine Gifts: Better Ways to Say Thanks Than a Random Bottle",
            h1="Thank You Wine Gifts: Better Ways to Say Thanks Than a Random Bottle",
            description="Warm, practical thank-you wine gift guidance for projects, referrals, hosts, teams, suppliers and partners.",
            intro="A thank-you gift does not need to be grand. It needs to feel connected to the thing you are thanking someone for.",
            hero_bullets=["Best for: project endings, referrals, hosts, partners and team thank-yous", "Typical budget: £25–£100", "Avoid: a random bottle with a generic note"],
            opening_heading="The note does more work than the bottle",
            opening=["Most bad thank-you wine gifts are not bad because of the wine. They are bad because they feel vague.", "A clear note, a suitable bottle or pair, and sensible delivery timing can make a modest gift feel genuinely warm."],
            best_fit_table={"headers": ["Moment", "Good gift", "Message angle"], "rows": [["Project thank-you", "Sparkling or mixed pair", "Appreciate the work"], ["Referral", "Smart bottle or hamper", "Thank them for trust"], ["Host", "Sparkling or food-friendly bottle", "Thank them for hospitality"], ["Team", "Mixed case or hamper", "Make it shareable"], ["Supplier/partner", "Bottle pair", "Acknowledge reliability"]]},
            article_sections=[
                {"id": "routes", "heading": "Bottle, pair, hamper or case?", "paragraphs": ["A single bottle works for a small gesture. A pair gives choice. A hamper feels more complete. A case is better when the gift is for a team."], "editorial_note": "A good gift should not create a problem for the person receiving it."},
                {"id": "messages", "heading": "Message examples", "messages": [{"label": "Project", "text": "Thank you for helping get the project over the line. We appreciated the collaboration and pace."}, {"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."}, {"label": "Host", "text": "Thank you again for hosting. We hope this gives you something nice to open afterwards."}, {"label": "Team", "text": "A thank-you for the whole team. We appreciated the energy and care you brought to the work."}]},
                {"id": "avoid", "heading": "What to avoid", "bullets": ["Sending during sensitive commercial decisions.", "Making the gift too expensive for the moment.", "Using vague appreciation language.", "Ignoring alcohol suitability."]},
            ],
            faqs=[
                {"q": "What is a good thank-you wine gift?", "a": "A sparkling bottle, red/white pair, compact hamper or mixed case can work if it fits the recipient and occasion."},
                {"q": "How much should I spend on a thank-you wine gift?", "a": "Many thank-you gifts sit between £25 and £100, depending on relationship and policy."},
                {"q": "What should I write in the note?", "a": "Reference the specific help, project, referral or hospitality. Keep it short and warm."},
                {"q": "Is wine suitable for every thank-you?", "a": "No. Use alternatives when alcohol suitability is unclear."},
            ],
            related=["client-wine-gifts", "wine-gifts-for-thank-you", "corporate-wine-gifts-uk"],
            cta="Plan a thank-you wine gift",
            cta_heading="Want the thank-you to feel more personal?",
            cta_text="Use the planner to match the gift route to the relationship and occasion.",
        ),
        "business-gift-wine-etiquette": enhanced_guide(
            title="Business Gift Wine Etiquette: How to Send Wine Without Making It Awkward",
            h1="Business Gift Wine Etiquette: How to Send Wine Without Making It Awkward",
            description="Clear UK business wine gifting etiquette covering value, timing, alcohol suitability, policies, notes and when not to send wine.",
            intro="Wine can be a perfectly good business gift. It can also be the wrong gift at the wrong time. The etiquette is mostly about proportion, timing and not making assumptions.",
            hero_bullets=["Best for: policy-aware client and partner gifting", "Typical budget: depends on relationship and internal policy", "Avoid: gifts that feel like pressure or ignore alcohol suitability"],
            opening_heading="There is a fine line between thoughtful and awkward",
            opening=["This is not legal advice, but it is sensible to check internal gift policies where the value is meaningful or the relationship is commercially sensitive.", "A good wine gift should be easy to accept, easy to explain, and proportionate to the relationship."],
            best_fit_table={"headers": ["Question", "Safer answer", "Why"], "rows": [["When to send?", "After a milestone or thank-you moment", "Avoids pressure"], ["Where to send?", "Office unless home is appropriate and agreed", "Reduces awkwardness"], ["What value?", "Policy-aware and proportionate", "Keeps it defensible"], ["What if unsure?", "Use non-alcohol or no gift", "Avoids assumptions"]]},
            article_sections=[
                {"id": "policy", "heading": "A note on company policies", "paragraphs": ["Check your own rules and, where possible, the recipient organisation’s acceptance limits. This matters more for regulated, public sector or procurement-sensitive relationships."], "editorial_note": "If the gift would be hard to explain in an email, do not send it yet."},
                {"id": "sensitivity", "heading": "Alcohol suitability and sensitivity", "paragraphs": ["Do not assume someone drinks. Health, religion, recovery, pregnancy, personal preference and company culture can all make alcohol unsuitable without the recipient wanting to explain why."], "bullets": ["Offer alternatives.", "Avoid singling people out.", "Use equal-value non-alcohol options."]},
                {"id": "timing", "heading": "When not to send wine", "bullets": ["During active procurement.", "Before a decision or renewal.", "Where acceptance rules are unclear.", "To someone whose preferences are unknown and alternatives are not available."]},
            ],
            faqs=[
                {"q": "Is it appropriate to send wine as a business gift?", "a": "Sometimes, if it is proportionate, policy-aware and suitable for the recipient."},
                {"q": "Should wine gifts be sent to home or office?", "a": "Office delivery is often safer unless home delivery is appropriate, expected and handled carefully."},
                {"q": "Is this legal advice?", "a": "No. It is practical planning guidance. Use your own legal, procurement or compliance advice where needed."},
                {"q": "What if I do not know whether they drink?", "a": "Choose an alcohol-free or food-led alternative."},
            ],
            related=["client-gifting-etiquette-uk", "client-gift-policy-checklist", "corporate-wine-gifts-uk"],
            cta="Create a policy-aware gift plan",
            cta_heading="Want to avoid an awkward gift?",
            cta_text="Use ClientCellar to shape a more careful gift route before buying.",
        ),
        "corporate-event-wine-planning": enhanced_guide(
            title="Corporate Event Wine Planning: How Much to Buy and What to Serve",
            h1="Corporate Event Wine Planning: How Much to Buy and What to Serve",
            description="Practical corporate event wine planning guidance for receptions, dinners, team celebrations and client events.",
            intro="Event wine planning is part hospitality, part logistics. The right answer depends on format, guest count, food, venue rules and how much you want people to drink.",
            hero_bullets=["Best for: receptions, dinners, client events and team celebrations", "Typical budget: plan per guest, then confirm with suppliers", "Avoid: exact quantity promises without venue or supplier input"],
            opening_heading="Plan ranges, not fantasy precision",
            opening=["Wine quantity guidance should be treated as a planning range, not a guarantee. Guests, food, timings and transport all change consumption.", "The sensible move is to estimate, then ask the supplier or venue to sanity-check the mix."],
            best_fit_table={"headers": ["Event", "Wine route", "Watch"], "rows": [["Reception", "Sparkling plus white/red", "Short service window"], ["Dinner", "Food-led red/white split", "Menu matters"], ["Client event", "Polished but restrained", "Do not make it too boozy"], ["Team celebration", "Inclusive mix", "Alcohol-free options"]]},
            article_sections=[
                {"id": "quantities", "heading": "Quantity planning without pretending it is exact", "paragraphs": ["Start with guest count, event length and whether wine is the main event or part of a broader reception. Then discuss case quantities and sale-or-return with suppliers where available."], "editorial_note": "For events, the operational questions are as important as the bottle choice."},
                {"id": "mix", "heading": "Red, white, sparkling and alcohol-free", "bullets": ["Sparkling works for arrivals and celebrations.", "White often moves faster at receptions.", "Red suits dinners and colder months.", "Alcohol-free options should feel adult, not like an afterthought."]},
                {"id": "supplier-questions", "heading": "Questions to ask suppliers", "bullets": ["Can you supply the quantity by the event date?", "Can you advise on the red/white/sparkling mix?", "Can you deliver to the venue?", "Do you offer sale-or-return?", "What substitutions may be made?"]},
            ],
            faqs=[
                {"q": "How much wine should I buy for a corporate event?", "a": "Use guest count, event length, food and format to create a planning estimate, then confirm with your supplier or venue."},
                {"q": "What wine should be served at a business reception?", "a": "A simple mix of sparkling, white, red and alcohol-free drinks usually works better than niche choices."},
                {"q": "Should corporate events include alcohol-free options?", "a": "Yes. Inclusive event planning should include adult alcohol-free alternatives."},
                {"q": "Can ClientCellar supply event wine?", "a": "No. ClientCellar provides planning guidance and supplier-route recommendations."},
            ],
            related=["event-wine-planning-uk", "wine-for-corporate-events", "wine-tasting-corporate-event"],
            cta="Plan a wine event",
            cta_heading="Planning wine for a corporate event?",
            cta_text="Use the event planner to estimate quantities, supplier questions and logistics.",
            cta_url="/event-planner",
        ),
        "wine-tasting-corporate-event": enhanced_guide(
            title="Wine Tasting Corporate Events: How to Make It Fun Without Making It Forced",
            h1="Wine Tasting Corporate Events: How to Make It Fun Without Making It Forced",
            description="Ideas for corporate wine tasting events, including hosted tastings, blind tasting, food pairing, team building and inclusive formats.",
            intro="A corporate wine tasting should not feel like a lecture or a drinking contest. Done well, it gives people something to talk about without making anyone perform expertise.",
            hero_bullets=["Best for: team socials, client entertainment and hosted tasting events", "Typical budget: depends on host, wine, food and delivery", "Avoid: wine snobbery, compulsory drinking and formats with no pace"],
            opening_heading="Keep it structured, not stiff",
            opening=["The best tastings have a simple shape: a host, a theme, a few wines, enough food or water, and space for people who know nothing about wine to enjoy themselves.", "The danger is choosing a format that feels clever to the organiser but awkward for everyone else."],
            best_fit_table={"headers": ["Format", "Best for", "Why"], "rows": [["Hosted tasting", "Client-safe events", "Keeps pace and tone"], ["Blind tasting", "Team energy", "Fun without too much knowledge"], ["Regional theme", "More editorial feel", "Easy story"], ["Food pairing", "Premium events", "Feels complete"], ["Virtual tasting", "Remote teams", "Delivery matters"]]},
            article_sections=[
                {"id": "formats", "heading": "Formats that usually work", "bullets": ["Hosted tasting with a relaxed expert.", "Blind tasting with simple scoring.", "Regional theme such as Spain, Italy or English sparkling.", "Wine and cheese pairing.", "Remote tasting packs for distributed teams."], "editorial_note": "Avoid making people prove they know wine. The event should give them confidence, not homework."},
                {"id": "group-size", "heading": "Group size and budget", "paragraphs": ["Small groups can go deeper. Larger groups need a simpler theme and stronger hosting. Remote groups need more lead time because delivery becomes the event risk."]},
                {"id": "inclusive", "heading": "Make it inclusive", "bullets": ["Offer alcohol-free alternatives.", "Do not make drinking compulsory.", "Keep pour sizes modest.", "Include food and water.", "Choose a host who can read the room."]},
            ],
            faqs=[
                {"q": "Are wine tastings good corporate events?", "a": "They can be, if they are hosted well, inclusive and not too heavy on wine knowledge."},
                {"q": "What format works best for a team wine tasting?", "a": "A relaxed hosted tasting, blind tasting or food-pairing format usually works well."},
                {"q": "Can wine tastings work remotely?", "a": "Yes, but delivery lead times, address handling and alcohol-free alternatives need planning."},
                {"q": "How do you avoid making a wine tasting feel forced?", "a": "Keep the structure simple, the tone relaxed, and avoid making attendees perform expertise."},
            ],
            related=["virtual-wine-tasting-for-teams", "wine-tasting-team-building", "corporate-event-wine-planning"],
            cta="Plan a wine event",
            cta_heading="Want a tasting that people actually enjoy?",
            cta_text="Use the event planner to shape format, supplier questions and event logistics.",
            cta_url="/event-planner",
        ),
    }
)

GUIDES.update(
    {
        "corporate-wine-gifts-uk": enhanced_guide(
            title="Corporate Wine Gifts UK: Thoughtful Client Gift Ideas",
            h1="Corporate Wine Gifts UK: How to Send Something That Feels Thoughtful, Not Lazy",
            description="A practical UK guide to choosing corporate wine gifts that feel thoughtful, appropriate and useful, from mixed cases to Champagne, hampers and team gifts.",
            intro="Corporate wine gifting is easy to do badly because it looks simple from the outside. Pick a bottle, add a box, send it before Christmas. Done. Except that is exactly why so many client gifts feel forgettable.",
            hero_bullets=[
                "Best for: client thank-yous, Christmas gifts, project milestones and senior relationships",
                "Typical budget: £40-£150, depending on relationship and context",
                "Avoid: one random bottle for a whole team, over-packaged weak wine, gifts with no note",
            ],
            opening_heading="The judgement matters more than the bottle",
            opening=[
                "The point is not to prove you know wine. The point is to make the recipient feel considered. That starts with three questions: who is receiving it, why are you sending it, and should the gift be shared?",
                "A £35 bottle with a proper note can feel better than a £90 gift chosen in a rush. A mixed case can be smarter than Champagne if the gift is for a team. A hamper can be useful if taste is unknown, but only if the contents are worth eating and drinking.",
            ],
            best_fit_table={
                "headers": ["Situation", "Better route", "Editorial view"],
                "rows": [
                    ["Senior client", "Champagne, English sparkling or premium mixed case", "Keep it polished, not theatrical."],
                    ["Client team", "Mixed case or food-and-wine hamper", "One bottle for a team creates awkwardness."],
                    ["Project thank-you", "Sparkling wine or a small case", "Connect the gift to the milestone in the note."],
                    ["Unclear preferences", "Hamper or alcohol-free alternative", "Do not make alcohol the only way to accept the gift."],
                ],
            },
            article_sections=[
                {
                    "id": "why-it-goes-wrong",
                    "heading": "This is where corporate gifting quietly goes wrong",
                    "paragraphs": [
                        "Most bad wine gifts fail before the cork is pulled. They are sent to the wrong person, at the wrong moment, with a message that sounds like procurement approved it five minutes before dispatch.",
                        "Wine still works because it is useful, shareable and easier to understand than many luxury gifts. But it needs a reason. If the gift is really for a whole team, send something the team can share. If it is for a senior relationship, choose restraint. If alcohol suitability is unclear, do not force the recipient into an awkward thank-you.",
                    ],
                    "editorial_note": "The safest option is often the one that looks least exciting on a spreadsheet: a good mixed case, a proper note and a supplier who can deliver reliably.",
                },
                {
                    "id": "budget-judgement",
                    "heading": "Spend enough to look considered, not enough to look strange",
                    "paragraphs": [
                        "For many UK client gifts, £50-£100 is the useful middle. Below that, focus on one good idea rather than fake luxury. Above that, make sure the relationship, policy and occasion can carry the spend.",
                        "If the gift is for a key account or a team, a higher budget can make sense. If it is a small thank-you after a tidy piece of work, modest and specific is often better.",
                    ],
                    "table": {
                        "headers": ["Budget", "Best use", "How to think about it"],
                        "rows": [
                            ["£25-£40", "Small thank-you", "Keep it honest and avoid grand packaging."],
                            ["£40-£75", "Good individual gift", "Strong range for a bottle, pair or compact hamper."],
                            ["£75-£150", "Warmer relationship", "Use for senior clients, cases or premium hampers."],
                            ["£150+", "Key account or team", "Check approval and make the reason clear."],
                        ],
                    },
                },
                {
                    "id": "note",
                    "heading": "The note does more work than people think",
                    "paragraphs": ["A good note turns wine from a transaction into a relationship gesture. Keep it short, specific and human."],
                    "messages": [
                        {"label": "Avoid", "text": "Please accept this gift as a token of our appreciation."},
                        {"label": "Better", "text": "Thanks again for your support on the project this year. We really enjoyed working with you and hope this gives you something nice to open over Christmas."},
                        {"label": "Better", "text": "A small thank-you for helping get the launch over the line. We really appreciated the pace, patience and good humour from your team."},
                    ],
                },
            ],
            faqs=[
                {"q": "What is a good corporate wine gift in the UK?", "a": "A mixed case, sparkling wine gift, Champagne route or food-and-wine hamper can all work. The best choice depends on recipient suitability, budget, relationship and delivery practicalities."},
                {"q": "How much should I spend on a client wine gift?", "a": "Many UK business buyers sit around £50-£100 for a polished client gift, but internal policy and relationship context matter more than a universal number."},
                {"q": "Is wine still appropriate as a corporate gift?", "a": "Yes, when alcohol is suitable for the recipient and the gift is proportionate. Keep alcohol-free or hamper alternatives available where preferences are unclear."},
                {"q": "Is Champagne better than wine for corporate gifting?", "a": "Champagne can signal celebration, but English sparkling, a mixed case or a hamper may be more appropriate for some clients."},
                {"q": "Should I send one bottle or a case?", "a": "One bottle can work for an individual. For teams or shared offices, a case or hamper usually feels less awkward."},
            ],
            related=["client-wine-gifts", "best-wine-gifts-under-50", "christmas-corporate-wine-gifts"],
            cta="Build my wine gift brief",
            cta_heading="Need a corporate wine gift that does not feel generic?",
            cta_text="Use ClientCellar to build a quick wine gift brief. Tell us who the gift is for, your budget and the occasion, and we will help you narrow the options and supplier direction.",
        ),
        "client-wine-gifts": enhanced_guide(
            title="Client Wine Gifts: How to Choose a Better Bottle, Case or Hamper",
            h1="Client Wine Gifts That Feel Personal Without Getting Weird",
            description="How to choose client wine gifts that feel personal, polished and appropriate, including ideas by budget, relationship type and occasion.",
            intro="A client wine gift is really a small relationship decision wearing gift wrap. It should feel warm, but not overfamiliar; generous, but not loaded; personal, but not strange.",
            hero_bullets=[
                "Best for: relationship-building, thank-yous and account management",
                "Typical budget: £35-£120",
                "Avoid: gifts that feel too intimate, too cheap, or too obviously bulk-bought",
            ],
            opening_heading="Think like an account director",
            opening=[
                "A new client does not need the same gift as someone who has trusted you for five years. A senior stakeholder does not need the same gift as a wider project team. That sounds obvious, but it is where many client gifts drift into awkward territory.",
                "The gift should read as appreciation, not pressure. If there is a live decision, procurement process or renewal in the background, be more careful. A client gift should not feel like a bribe, a flex, or an apology.",
            ],
            best_fit_table={
                "headers": ["Client relationship", "Safer gift route", "Tone to aim for"],
                "rows": [
                    ["New client", "Smart bottle or small pair", "Warm but restrained"],
                    ["Long-standing client", "Mixed case or premium hamper", "Specific and appreciative"],
                    ["Senior contact", "Sparkling or elegant bottle", "Calm and polished"],
                    ["Client team", "Shareable case or hamper", "Inclusive and practical"],
                    ["Warm prospect", "Modest thank-you only", "Careful, never persuasive"],
                ],
            },
            article_sections=[
                {
                    "id": "client-dynamics",
                    "heading": "The awkward bit",
                    "paragraphs": [
                        "Client gifts work best when they are connected to something real: a project ending, a difficult milestone, a year of support, an introduction, a referral. Without that reason, even a good bottle can feel oddly hollow.",
                        "For a long-standing client, you can afford more warmth. For a newer relationship, keep it simpler. For a whole team, do not send a single bottle and leave someone else to decide who gets it.",
                    ],
                    "editorial_note": "If you cannot explain why you are sending the gift in one sentence, pause before ordering.",
                },
                {
                    "id": "wording",
                    "heading": "Subtle wording helps",
                    "paragraphs": ["The note should sound like a person wrote it, not a CRM sequence. Mention the work, the relationship or the moment. Avoid anything that sounds like you are trying to buy goodwill."],
                    "messages": [
                        {"label": "Project thank-you", "text": "Thank you again for the energy and clarity your team brought to the project. We really enjoyed working with you."},
                        {"label": "End-of-year", "text": "A small thank-you for your support this year. We hope you get a proper pause over the Christmas break."},
                        {"label": "Long-term account", "text": "We really value the relationship and appreciate the trust you have placed in us over the years."},
                        {"label": "Team gift", "text": "A thank-you for the whole team. We appreciated the collaboration and hope this gives you something to share."},
                    ],
                },
                {
                    "id": "wrong-answer",
                    "heading": "When wine is the wrong answer",
                    "paragraphs": [
                        "Wine is not always the right gift. Alcohol may be unsuitable, policies may be strict, or the relationship may be too early. In those cases, a food hamper, premium tea or coffee, alcohol-free sparkling or a choice-based gift can be more thoughtful than forcing the wine route.",
                    ],
                },
            ],
            faqs=[
                {"q": "What wine should I send to a client?", "a": "If you know their taste, choose around it. If not, sparkling wine, a balanced mixed case or a wine-and-food hamper is usually safer."},
                {"q": "How much should I spend on a client wine gift?", "a": "A practical range is often £35-£120, depending on relationship value, policy and occasion."},
                {"q": "Is it appropriate to send wine to a client?", "a": "It can be, but check alcohol suitability, timing and any gift acceptance policies first."},
                {"q": "What should I write in a client gift note?", "a": "Mention the relationship or moment briefly. Keep it warm, specific and free of sales pressure."},
                {"q": "What can I send if I am not sure they drink alcohol?", "a": "Choose a food hamper, premium tea or coffee, non-alcoholic sparkling, or another equal-quality alternative."},
            ],
            related=["corporate-wine-gifts-uk", "thank-you-wine-gifts", "business-gift-wine-etiquette"],
            cta="Plan a client wine gift",
            cta_heading="Not sure what to send a client?",
            cta_text="Build a ClientCellar gift brief and get a clearer recommendation based on the relationship, budget and occasion.",
        ),
        "best-wine-gifts-under-50": enhanced_guide(
            title="Best Wine Gifts Under £50: Smart Ideas That Still Feel Generous",
            h1="Best Wine Gifts Under £50 That Do Not Feel Like an Afterthought",
            description="Wine gift ideas under £50 that still feel thoughtful, including sparkling wine, mixed pairs, small hampers and client-safe options.",
            intro="£50 is enough for a good wine gift, but not enough to fake luxury. That is the line to keep in mind.",
            hero_bullets=[
                "Best for: thank-yous, smaller client gifts, birthdays, host gifts and team gestures",
                "Typical budget: £30-£50",
                "Avoid: fake luxury packaging, weak wine in a heavy box, novelty gifts",
            ],
            opening_heading="Do not buy the packaging",
            opening=[
                "At this budget, simple wins. A good bottle, a clean two-bottle pair, a small sparkling gift or a compact wine-and-food hamper can all work. A giant hamper full of filler usually does not.",
                "The more a gift shouts about being luxury under £50, the more carefully you should read the contents list.",
            ],
            best_fit_table={
                "headers": ["Gift route", "Why it works", "Buyer judgement"],
                "rows": [
                    ["English sparkling", "Feels celebratory without a huge budget", "Good for milestones and Christmas."],
                    ["Two-bottle pair", "Gives choice", "Safer than one risky bottle."],
                    ["Small hamper", "Feels complete", "Only if the food is not filler."],
                    ["Independent merchant pick", "Feels less generic", "Best when you can ask for advice."],
                ],
            },
            article_sections=[
                {
                    "id": "what-works",
                    "heading": "Where £50 works hard",
                    "paragraphs": [
                        "A focused gift under £50 can feel generous because it knows what it is. A sparkling bottle says celebration. A red-and-white pair says choice. A compact hamper says evening-in, as long as the food and wine are both doing real work.",
                        "What does not work is fake heft: a wooden box, novelty accessories or a hamper that looks big online but arrives as average wine and tiny jars.",
                    ],
                    "editorial_note": "A £45 gift chosen cleanly often beats a £49.99 gift trying to look like £100.",
                },
                {
                    "id": "recipient",
                    "heading": "Match the level of risk",
                    "table": {
                        "headers": ["Recipient", "Safer choice"],
                        "rows": [
                            ["Client", "Sparkling, two-bottle gift or polished small hamper"],
                            ["Host", "Sparkling, white wine or food-friendly red"],
                            ["Team member", "Small hamper or bottle with a real note"],
                            ["Wine enthusiast", "Independent merchant recommendation"],
                        ],
                    },
                },
                {
                    "id": "avoid",
                    "heading": "Leave these on the shelf",
                    "paragraphs": [
                        "Novelty wine accessories rarely make the gift better. Over-packaged cheap wine feels cynical. Ultra-obscure bottles are fun only when you know the person will enjoy the risk.",
                    ],
                },
            ],
            faqs=[
                {"q": "Is £50 enough for a good wine gift?", "a": "Yes. It is enough for a strong bottle, a useful pair, sparkling wine or a compact hamper if you avoid overblown packaging."},
                {"q": "What is the best wine gift under £50?", "a": "For business gifting, sparkling wine, a red/white pair or a compact wine-and-food gift is usually safer than a niche bottle."},
                {"q": "Should I buy one bottle or two bottles under £50?", "a": "One bottle gives quality. Two bottles give choice. For unknown tastes, a pair can be more forgiving."},
                {"q": "Are wine hampers under £50 worth it?", "a": "Some are, but check the actual contents list. Avoid hampers padded with small filler items."},
                {"q": "What should I avoid when buying wine gifts under £50?", "a": "Avoid fake luxury packaging, novelty accessories, weak wine in heavy boxes and gifts that pretend to be more premium than they are."},
            ],
            related=["best-wine-gifts-under-25", "best-wine-gifts-under-100", "wine-gift-hampers-uk"],
            cta="Find a wine gift under £50",
            cta_heading="Want a wine gift under £50 that still feels thoughtful?",
            cta_text="Use ClientCellar to create a quick gift brief and narrow your options by budget, recipient and occasion.",
        ),
        "christmas-corporate-wine-gifts": enhanced_guide(
            title="Christmas Corporate Wine Gifts: Better Ideas for UK Clients and Teams",
            h1="Christmas Corporate Wine Gifts That Do Not Feel Like Everyone Got the Same Thing",
            description="A practical guide to Christmas corporate wine gifts for UK clients, teams and suppliers, including budget advice, timing, messages and safer gift ideas.",
            intro="December has a way of making thoughtful people send forgettable gifts. The inbox is full, offices are half empty, suppliers are busy, and suddenly a beige hamper feels like a strategy.",
            hero_bullets=[
                "Best for: end-of-year client thank-yous, account teams, suppliers and senior contacts",
                "Typical budget: £40-£150",
                "Avoid: late orders, generic hampers, gifts with no message",
            ],
            opening_heading="The December problem",
            opening=[
                "Christmas gifting works when it feels timely and specific. It fails when it feels like everyone on the list received the same thing because someone needed the task closed before the break.",
                "A smaller thoughtful gift can beat a large beige hamper. A short message can make a simple bottle feel warmer. And delivery planning matters more than people admit: a lovely gift arriving at an empty office is not a lovely gift anymore.",
            ],
            best_fit_table={
                "headers": ["Recipient", "Stronger Christmas route", "Why"],
                "rows": [
                    ["Senior client", "Champagne or English sparkling", "Classic without needing much explanation."],
                    ["Client team", "Mixed case or proper hamper", "Shareable and less awkward."],
                    ["Remote contact", "Direct-to-home gift", "Only if address handling is appropriate."],
                    ["Supplier or partner", "Thoughtful bottle pair", "Warm without looking excessive."],
                ],
            },
            article_sections=[
                {
                    "id": "timing",
                    "heading": "The office delivery problem",
                    "paragraphs": [
                        "Christmas gifts often go wrong in the boring places: address lists, office closures, substitutions and cut-off dates. Start earlier than feels necessary, especially for larger lists or anything branded.",
                        "Ask suppliers about delivery windows and substitutions before you fall in love with the gift. If half the recipients are remote, confirm whether home delivery is appropriate and how failed deliveries are handled.",
                    ],
                },
                {
                    "id": "message",
                    "heading": "The message makes it seasonal",
                    "paragraphs": ["The note does not need to be elaborate. It just needs to sound like the relationship exists."],
                    "messages": [
                        {"label": "Formal client", "text": "Thank you for your partnership this year. We wish you and your team a restful Christmas and a strong start to the new year."},
                        {"label": "Warmer client", "text": "It has been a real pleasure working together this year. A small festive thank-you from all of us."},
                        {"label": "Team thank-you", "text": "A Christmas thank-you for the whole team. We appreciated the collaboration, pace and good humour this year."},
                    ],
                    "editorial_note": "Generic Christmas gifts are not always bad. Generic Christmas gifts with generic messages are the problem.",
                },
                {
                    "id": "hamper-warning",
                    "heading": "Do not let the hamper do all the thinking",
                    "paragraphs": [
                        "Hampers are popular because they feel safe, and sometimes they are. But a large hamper filled with weak biscuits, tiny jars and average wine can feel less generous than a better-edited smaller gift.",
                    ],
                },
            ],
            faqs=[
                {"q": "What are good Christmas wine gifts for clients?", "a": "Champagne, English sparkling, a smart mixed pair, a seasonal case or a food-and-wine hamper can all work when matched to the recipient."},
                {"q": "When should I order corporate Christmas wine gifts?", "a": "Start supplier conversations well before December for larger orders. Confirm the supplier’s current cut-off dates directly."},
                {"q": "Is Champagne a good corporate Christmas gift?", "a": "It can be, especially for senior or celebratory relationships, but sparkling wine, hampers or mixed cases may be more practical."},
                {"q": "What should I send to a client team at Christmas?", "a": "A mixed case or hamper is usually more shareable than one bottle addressed to a whole team."},
                {"q": "What should I write in a Christmas client gift message?", "a": "Thank them for the partnership or project, keep it warm, and avoid heavy sales language."},
            ],
            related=["corporate-wine-gifts-uk", "client-wine-gifts", "wine-gift-hampers-uk"],
            cta="Plan Christmas wine gifts",
            cta_heading="Planning Christmas wine gifts for clients?",
            cta_text="Build a ClientCellar gift brief and get a clearer plan for who you are buying for, what to spend and what kind of supplier to use.",
        ),
        "wine-gift-hampers-uk": enhanced_guide(
            title="Wine Gift Hampers UK: How to Choose One That Is Actually Worth Sending",
            h1="Wine Gift Hampers UK: How to Choose One That Is Actually Worth Sending",
            description="A practical UK guide to choosing wine gift hampers that feel generous rather than generic, including what to look for, what to avoid and who they suit best.",
            intro="Most bad hampers are built to look better in a product photo than they feel in real life. Big basket, lots of straw, tiny jars, average biscuits, forgettable wine.",
            hero_bullets=[
                "Best for: client teams, Christmas gifts, host gifts and shared occasions",
                "Typical budget: £45-£150",
                "Avoid: cheap filler products, weak wine, oversized packaging",
            ],
            opening_heading="Do not buy the biggest hamper",
            opening=[
                "A bigger hamper is not automatically a better hamper. The best ones have fewer, better items: wine you would actually open, food that makes sense with it, and packaging that protects the gift rather than becoming the gift.",
                "If you are buying for a client or team, the hamper should be easy to share and not too quirky. It should not ask the recipient to pretend to be excited about six tiny jars of chutney.",
            ],
            best_fit_table={
                "headers": ["Occasion", "Better hamper style", "Watch for"],
                "rows": [
                    ["Client thank-you", "Wine plus savoury snacks", "Overly themed filler."],
                    ["Christmas", "Wine, cheese, crackers and sweet items", "Generic festive bulk."],
                    ["Team gift", "Larger mixed hamper", "Dietary and alcohol suitability."],
                    ["Senior client", "Premium but restrained hamper", "Huge packaging with modest contents."],
                ],
            },
            article_sections=[
                {
                    "id": "filler",
                    "heading": "The filler problem",
                    "paragraphs": [
                        "Hamper photography can be misleading. More items does not always mean more value. Tiny jars, generic biscuits and cheap chocolate can make a hamper look abundant while quietly reducing the quality of the gift.",
                        "Read the contents list like a buyer, not a browser. If the wine is vague and the food reads like padding, keep looking.",
                    ],
                    "editorial_note": "Do not buy the packaging. Buy the gift.",
                },
                {
                    "id": "case-or-hamper",
                    "heading": "Hamper or mixed case?",
                    "paragraphs": [
                        "A hamper is better when the gift needs to feel like an experience or be shared by a team. A mixed case is better when the recipient mainly cares about wine. If taste is unknown, a hamper can be safer, but only when the contents are genuinely useful.",
                    ],
                },
                {
                    "id": "checks",
                    "heading": "The checks that matter",
                    "paragraphs": [
                        "Before ordering, confirm delivery date, exact contents, gift message options, alcohol contents, dietary information, substitutions and whether the supplier can provide the invoice you need.",
                    ],
                },
            ],
            faqs=[
                {"q": "Are wine gift hampers worth it?", "a": "They can be if the contents are strong and useful. Avoid hampers padded with low-value filler products."},
                {"q": "What should be in a good wine hamper?", "a": "Good wine, food that pairs sensibly with it, clear contents, strong packaging and enough information about allergens or substitutions."},
                {"q": "How much should I spend on a wine hamper?", "a": "Many decent corporate wine hampers sit around £45-£150, depending on size, recipient and presentation."},
                {"q": "Are wine hampers good corporate gifts?", "a": "Yes, especially for teams or mixed preferences, but alcohol suitability and dietary needs should be checked."},
                {"q": "Is a wine hamper better than a mixed case?", "a": "A hamper is better for sharing and broader appeal. A mixed case is better for someone who mainly enjoys wine."},
            ],
            related=["corporate-wine-gifts-uk", "christmas-corporate-wine-gifts", "best-wine-gifts-under-50"],
            cta="Build my wine gift brief",
            cta_heading="Need a wine hamper that does not feel generic?",
            cta_text="Use ClientCellar to create a quick gift brief and compare whether a hamper, mixed case or single bottle is the better fit.",
        ),
        "best-client-wine-gifts": enhanced_guide(
            title="Best Client Wine Gifts: Ideas That Feel Thoughtful, Not Transactional",
            h1="Best Client Wine Gifts: Ideas That Feel Thoughtful, Not Transactional",
            description="Relationship-led client wine gift ideas for UK businesses, including budgets, note examples, policy checks and safer alternatives.",
            intro="This page is for the moment when you know you should send something, but you do not want the gift to feel like a line item in account management.",
            hero_bullets=[
                "Best for: account teams, founders, agencies and professional services firms",
                "Typical budget: £35-£150",
                "Avoid: gifts that feel too cheap, too flashy, too personal or too bulk-bought",
            ],
            opening_heading="If I were buying for...",
            opening=[
                "For a new client, I would stay polished and modest: a smart bottle, a pair or a compact hamper. For a long-standing client, I would make the gift a little more specific. For a senior relationship, I would choose restraint over size.",
                "The safest choice is usually the one that matches the relationship rather than the biggest one in the supplier catalogue.",
            ],
            best_fit_table={
                "headers": ["If you are buying for", "First route to consider", "Why"],
                "rows": [
                    ["A new client", "Bottle pair or small hamper", "Warm without being too much."],
                    ["A long-term client", "Mixed case or premium hamper", "Recognises the relationship."],
                    ["A senior stakeholder", "Sparkling or elegant wine gift", "Clear and polished."],
                    ["A project team", "Shareable case or hamper", "Avoids making one person distribute one bottle."],
                ],
            },
            article_sections=[
                {
                    "id": "shopping-judgement",
                    "heading": "The safest choice here is...",
                    "paragraphs": [
                        "If taste is unknown, choose usefulness. Sparkling wine, a red-and-white pair, a balanced mixed case or a food-and-wine gift gives the recipient room to enjoy the gift without needing to share your exact preferences.",
                        "I would avoid trophy bottles unless you know the person cares about wine. They can look impressive, but they can also feel like you bought the price tag.",
                    ],
                    "editorial_note": "A client gift should not feel like homework. If the recipient needs specialist knowledge to enjoy it, make sure they actually have that interest.",
                },
                {
                    "id": "messages",
                    "heading": "A note that does not sound transactional",
                    "messages": [
                        {"label": "Safe and warm", "text": "A small thank-you for your support this year. We have really enjoyed working with you."},
                        {"label": "Project-led", "text": "Thank you for helping make the project such a constructive one. We appreciated the collaboration."},
                        {"label": "Team-led", "text": "Something for the team to share. Thank you for the pace, patience and good humour."},
                    ],
                },
                {
                    "id": "policy",
                    "heading": "One careful sentence on policy",
                    "paragraphs": [
                        "If the gift value is meaningful or the relationship is commercially sensitive, check your internal policy before ordering. It is much easier to adjust the gift before it ships than explain it afterwards.",
                    ],
                },
            ],
            faqs=[
                {"q": "What is the best client wine gift?", "a": "For unknown tastes, sparkling wine, a mixed case or a wine-and-food hamper is usually safer than a niche bottle."},
                {"q": "How much should I spend on a client wine gift?", "a": "Many UK businesses use £40-£100 for polished client gifts, with higher budgets reserved for priority relationships and policy-approved occasions."},
                {"q": "Should I send wine to a client team?", "a": "A mixed case or hamper is usually better than one bottle if the gift is for a team."},
                {"q": "What should I write in a client gift note?", "a": "Mention the project, relationship or moment briefly. Keep it warm, specific and not sales-led."},
                {"q": "What if I am not sure they drink alcohol?", "a": "Use a hamper, alcohol-free sparkling, coffee, tea or another equal-quality alternative."},
            ],
            related=["client-wine-gifts", "corporate-wine-gifts-uk", "business-gift-wine-etiquette"],
            cta="Plan a client gift",
            cta_heading="Want a client gift that feels considered?",
            cta_text="Use the gift planner to turn recipient type, budget and occasion into a practical supplier direction.",
        ),
        "best-wine-gifts-under-25": enhanced_guide(
            title="Best Wine Gifts Under £25: Small Gifts That Still Feel Considered",
            h1="Best Wine Gifts Under £25: Small Gifts That Still Feel Considered",
            description="Honest wine gift ideas under £25, including single bottles, small thank-yous, host gifts and what to avoid.",
            intro="Under £25 is not luxury, and pretending otherwise is where these gifts go wrong. That does not mean the gift has to feel cheap.",
            hero_bullets=[
                "Best for: modest thank-yous, host gifts and small team gestures",
                "Typical budget: £15-£25 before delivery",
                "Avoid: novelty sets, fake-premium boxes and weak wine in heavy packaging",
            ],
            opening_heading="One good bottle beats a fake hamper",
            opening=[
                "This is the budget where honesty matters. Buy one decent thing. Add a proper note. Do not stretch the money across wine, glasses, corkscrew, box, ribbon and three snack items that nobody asked for.",
                "Supermarket wine is fine if it is chosen well. A simple bottle can feel thoughtful. A fake-premium gift set usually feels like you bought the packaging and hoped nobody would notice.",
            ],
            best_fit_table={
                "headers": ["Use case", "Better choice", "Skip"],
                "rows": [
                    ["Host gift", "Sparkling or crisp white", "Novelty labels."],
                    ["Small thank-you", "Classic single bottle", "Trying to make it look luxury."],
                    ["Colleague gesture", "Bottle with a good note", "Alcohol if preferences are unknown."],
                    ["Friend", "Something personal", "Generic gift set."],
                ],
            },
            article_sections=[
                {
                    "id": "honest-budget",
                    "heading": "The £25 rule",
                    "paragraphs": [
                        "At £25, you are buying a gesture as much as a gift. That is not a bad thing. It just means the message and appropriateness matter more.",
                        "For client gifting, this can work as a small thank-you, but be careful. If the relationship is important, either spend a little more or keep the gift modest and sincere.",
                    ],
                },
                {
                    "id": "avoid",
                    "heading": "The usual traps",
                    "paragraphs": [
                        "Bad mini sets, novelty glasses and heavy boxes are usually a sign the contents are doing less work than the presentation. Keep the spend in the wine, not the theatre around it.",
                    ],
                    "editorial_note": "Small gifts can be charming. Small gifts pretending to be grand usually are not.",
                },
            ],
            faqs=[
                {"q": "Is £25 enough for a wine gift?", "a": "Yes, for a simple bottle or modest thank-you. It is not usually enough for a premium corporate gift once delivery is included."},
                {"q": "Should I buy a gift set under £25?", "a": "Usually only if the wine is decent. Avoid sets where the accessories are doing too much of the selling."},
                {"q": "Can I send a client wine gift under £25?", "a": "It can work for a small gesture, but make the note thoughtful and avoid making the gift look more premium than it is."},
                {"q": "What wine style is safest under £25?", "a": "Sparkling, a classic red, or a crisp white usually works better than a niche bottle."},
            ],
            related=["best-wine-gifts-under-50", "client-wine-gifts", "corporate-wine-gifts-uk"],
            cta="Plan a modest wine gift",
            cta_heading="Need a small gift that still feels thoughtful?",
            cta_text="Use ClientCellar to shape a simple wine gift brief around budget, recipient and occasion.",
        ),
        "best-wine-gifts-under-100": enhanced_guide(
            title="Best Wine Gifts Under £100: Where Wine Gifting Gets Interesting",
            h1="Best Wine Gifts Under £100: Where Wine Gifting Gets Interesting",
            description="How to spend up to £100 well on wine gifts, from premium bottles and mixed cases to hampers and Champagne routes.",
            intro="£100 is where wine gifting gets interesting, because you have enough budget to choose properly. You also have enough budget to waste it.",
            hero_bullets=[
                "Best for: priority clients, senior stakeholders and polished Christmas gifts",
                "Typical budget: £60-£100",
                "Avoid: expensive-looking gifts with weak contents",
            ],
            opening_heading="This is a trade-off budget",
            opening=[
                "You can buy one excellent bottle, two strong bottles, a proper mixed case, a compact hamper or a Champagne-led gift. The best choice depends less on the price and more on what the recipient will actually understand and enjoy.",
                "If taste is known, one better bottle can be lovely. If taste is unknown, a mixed case or hamper may be wiser. If the moment is celebratory, Champagne makes sense, but it is not automatically the cleverest option.",
            ],
            best_fit_table={
                "headers": ["Route", "Best when", "Judgement"],
                "rows": [
                    ["One excellent bottle", "Taste is known", "High quality, higher risk."],
                    ["Two strong bottles", "You want choice", "Useful and less showy."],
                    ["Mixed case", "Wine-friendly recipient", "Often the smartest business route."],
                    ["Compact hamper", "Gift may be shared", "Check for filler."],
                    ["Champagne", "Celebration is the point", "Classic, but predictable."],
                ],
            },
            article_sections=[
                {
                    "id": "where-to-spend",
                    "heading": "Where to spend the money",
                    "paragraphs": [
                        "Spend it on contents, supplier reliability and presentation that does not shout. Do not spend it on a giant box that makes modest contents look apologetic.",
                        "Independent merchants can be excellent at this budget if you want advice. Mainstream suppliers can be better if you need practical delivery, invoicing and repeatability.",
                    ],
                    "editorial_note": "Premium is not the same as loud. The best £100 gifts usually feel calm.",
                },
                {
                    "id": "champagne",
                    "heading": "A note on Champagne",
                    "paragraphs": [
                        "Champagne is useful shorthand for celebration, but shorthand can become lazy. If the relationship or occasion calls for it, use it. If not, English sparkling, a mixed case or a better-edited hamper may feel more considered.",
                    ],
                },
            ],
            faqs=[
                {"q": "What is the best wine gift under £100?", "a": "A premium bottle, mixed case, English sparkling gift or compact hamper can all work. Choose based on recipient and occasion."},
                {"q": "Is £100 too much for a client gift?", "a": "It depends on policy and relationship context. Higher-value gifts should be proportionate and easy to justify."},
                {"q": "Should I choose Champagne under £100?", "a": "Champagne is good for celebration, but sparkling wine, mixed cases and hampers may be better for some recipients."},
                {"q": "Is a hamper better than wine under £100?", "a": "A hamper is better for sharing; wine is better where the recipient is known to enjoy it."},
            ],
            related=["luxury-corporate-wine-gifts", "best-wine-gifts-under-50", "wine-gift-hampers-uk"],
            cta="Plan a premium wine gift",
            cta_heading="Want to spend under £100 well?",
            cta_text="Use the planner to compare bottle, case and hamper routes before you contact suppliers.",
        ),
        "corporate-gift-ideas-for-clients": enhanced_guide(
            title="Corporate Gift Ideas for Clients That Do Not Feel Like Branded Filler",
            h1="Corporate Gift Ideas for Clients That Do Not Feel Like Branded Filler",
            description="Practical UK client gift ideas, including wine, hampers, coffee, experiences, non-alcoholic options and when each route works.",
            intro="Most corporate gifts are forgettable because they solve the sender’s problem, not the recipient’s. They tick a box, carry a logo and ask the client to be grateful.",
            hero_bullets=[
                "Best for: teams comparing gift routes before ordering",
                "Typical budget: £25-£150",
                "Avoid: branded filler that solves your marketing problem, not the client’s",
            ],
            opening_heading="Useful beats branded",
            opening=[
                "Wine is a good answer when the relationship, occasion and recipient make it suitable. It is not the only answer. Food, coffee, tea, alcohol-free drinks, experiences and charity-linked gifts can all be better in the right context.",
                "A gift should feel like it belongs in the relationship. If it mainly advertises your company, it is probably not a gift.",
            ],
            best_fit_table={
                "headers": ["Gift type", "Where it works", "Where it does not"],
                "rows": [
                    ["Wine or sparkling", "Thank-yous, milestones, Christmas", "Unknown alcohol suitability."],
                    ["Food hamper", "Teams and mixed preferences", "Dietary needs ignored."],
                    ["Coffee or tea", "Alcohol is uncertain", "Can feel too small without care."],
                    ["Experience", "Closer relationships", "Scheduling friction."],
                    ["Charity-linked gift", "Values-led relationships", "Performative wording."],
                ],
            },
            article_sections=[
                {
                    "id": "gift-routes",
                    "heading": "What gifts are actually useful?",
                    "paragraphs": [
                        "Useful does not mean boring. It means the recipient can enjoy the gift without work. A bottle they can open, a hamper they can share, coffee they will actually drink, or an experience that does not require six emails to arrange.",
                        "Wine fits naturally for client thank-yous, Christmas gifts and celebratory moments. It is weaker when alcohol suitability is unknown or the timing could look commercially sensitive.",
                    ],
                    "editorial_note": "ClientCellar is strongest for wine-led gifts, but wine is not always the answer. That is part of giving sensible advice.",
                },
                {
                    "id": "filler",
                    "heading": "Avoid branded filler",
                    "paragraphs": [
                        "The more a gift looks like leftover campaign merchandise, the less it feels like appreciation. If you want to include a brand touch, keep it subtle: a note, a small card, or packaging that does not overwhelm the gift.",
                    ],
                },
            ],
            faqs=[
                {"q": "What are good corporate gift ideas for clients?", "a": "Wine, sparkling, hampers, coffee, tea, alcohol-free drinks, experiences and charity-linked gifts can all work when matched to the relationship."},
                {"q": "Are wine gifts good for clients?", "a": "They can be, as long as alcohol is suitable and the value is proportionate."},
                {"q": "What should I avoid in client gifting?", "a": "Avoid branded filler, over-personal gifts, weak hampers and anything that creates policy discomfort."},
                {"q": "What if I do not know the client well?", "a": "Choose a safer mainstream route such as a modest hamper, sparkling gift, coffee or alcohol-free option."},
            ],
            related=["best-client-wine-gifts", "client-wine-gifts", "business-gift-wine-etiquette"],
            cta="Plan a client gift",
            cta_heading="Need a gift route that fits the client?",
            cta_text="Use the planner to shape a practical brief around recipient, budget and occasion.",
        ),
        "wine-gifts-for-customers": enhanced_guide(
            title="Wine Gifts for Customers: When It Works, When It Does Not, and How to Keep It Appropriate",
            h1="Wine Gifts for Customers: When It Works, When It Does Not, and How to Keep It Appropriate",
            description="Sensible guidance for customer wine gifts, including scale, suitability, delivery, personalisation and alternatives.",
            intro="Customer gifting is different from client gifting because scale changes everything. A gift that feels thoughtful for ten close clients can become operationally awkward for hundreds of customers.",
            hero_bullets=[
                "Best for: VIP customers, loyalty moments and carefully managed customer campaigns",
                "Typical budget: varies by customer tier and fulfilment model",
                "Avoid: alcohol-only campaigns where suitability and delivery data are uncertain",
            ],
            opening_heading="Scale makes everything less forgiving",
            opening=[
                "At customer scale, the quiet details matter: address quality, delivery permissions, failed deliveries, alcohol sensitivity, personalisation and customer data handling. This is not legal advice, but it is sensible to be careful before sending anything physical or alcohol-led.",
                "For broad campaigns, a choice-based or non-alcoholic route may be safer. For VIP customers, a more considered wine gift can work if the relationship supports it.",
            ],
            best_fit_table={
                "headers": ["Customer group", "Better route", "Reason"],
                "rows": [
                    ["VIP customers", "Premium wine, hamper or choice-led gift", "Relationship can support more thought."],
                    ["Broad customer list", "Choice-based or non-alcoholic option", "Lower suitability risk."],
                    ["Renewal thank-you", "Modest bottle or hamper", "Keep it appreciative, not persuasive."],
                    ["Local customers", "Regional merchant route", "Can feel less generic."],
                ],
            },
            article_sections=[
                {
                    "id": "difference",
                    "heading": "Client gift or customer campaign?",
                    "paragraphs": [
                        "A client gift is usually relationship-led. A customer gift is often campaign-led. That means the gift has to survive more edge cases: people who do not drink, people at different addresses, people with dietary needs, and people who may not expect a gift at all.",
                        "Personalisation helps only when it feels appropriate. A light note is good. Anything that feels too intimate, overfamiliar or data-heavy is not.",
                    ],
                },
                {
                    "id": "operational",
                    "heading": "The operational questions are not boring",
                    "paragraphs": [
                        "They are the gift. Ask how addresses are handled, what happens when delivery fails, whether alternatives are available, and whether the supplier can support the campaign cleanly.",
                    ],
                    "editorial_note": "If the gift creates a problem for the recipient, it is not a good gift.",
                },
            ],
            faqs=[
                {"q": "Can businesses send wine gifts to customers?", "a": "Sometimes, but alcohol suitability, delivery data, privacy and message tone need careful review."},
                {"q": "How is a customer gift different from a client gift?", "a": "Customer gifts are often larger-scale and less relationship-specific, so operational and suitability checks matter more."},
                {"q": "What is a safer alternative to wine for customers?", "a": "Choice-based gifts, food hampers, coffee, tea or alcohol-free options may be safer."},
                {"q": "Should customer gifts be personalised?", "a": "Light personalisation can help, but avoid anything that feels intrusive or overfamiliar."},
            ],
            related=["corporate-gift-ideas-for-clients", "client-wine-gifts", "business-gift-wine-etiquette"],
            cta="Plan customer wine gifts",
            cta_heading="Thinking about wine gifts for customers?",
            cta_text="Use ClientCellar to shape the route and questions before you contact suppliers.",
        ),
        "luxury-corporate-wine-gifts": enhanced_guide(
            title="Luxury Corporate Wine Gifts: How to Look Generous Without Looking Ridiculous",
            h1="Luxury Corporate Wine Gifts: How to Look Generous Without Looking Ridiculous",
            description="A practical guide to premium and luxury corporate wine gifts, including when to choose Champagne, fine wine, hampers and restrained alternatives.",
            intro="Luxury corporate gifting is where people can accidentally look least thoughtful. Spend more, shout louder, add a huge box, and somehow the gift becomes less elegant.",
            hero_bullets=[
                "Best for: senior clients, key accounts and major milestones",
                "Typical budget: £100-£250+",
                "Avoid: trophy bottles, showy packaging and gifts that breach policy",
            ],
            opening_heading="Calm looks more premium than loud",
            opening=[
                "Expensive does not automatically mean appropriate. Trophy bottles can be risky unless you know the recipient cares. Huge hampers can feel like theatre. A smaller elegant gift, chosen for the relationship, often lands better.",
                "Luxury should feel easy to accept. If it creates policy discomfort, looks like a flex or arrives without a clear reason, it has missed the point.",
            ],
            best_fit_table={
                "headers": ["Luxury route", "When it works", "Where it goes wrong"],
                "rows": [
                    ["Champagne", "Celebration is the message", "Too predictable if used automatically."],
                    ["Fine wine", "Taste is known", "Risky for non-enthusiasts."],
                    ["Premium hamper", "Gift will be shared", "Filler dressed as luxury."],
                    ["Independent merchant case", "Advice matters", "Operational support may vary."],
                ],
            },
            article_sections=[
                {
                    "id": "restraint",
                    "heading": "Restraint is not underspending",
                    "paragraphs": [
                        "For senior clients and key accounts, the best luxury gifts usually have a reason: a major milestone, a long relationship, a significant thank-you. Without that reason, the spend can feel awkward.",
                        "If you choose fine wine, make sure the recipient will appreciate it. If you choose Champagne, make sure celebration is the right signal. If you choose a hamper, read the contents like a sceptic.",
                    ],
                    "editorial_note": "The more expensive the gift, the clearer the business reason should be.",
                },
                {
                    "id": "approval",
                    "heading": "The approval trail matters",
                    "paragraphs": [
                        "Meaningful-value gifts should be easy to justify internally. Confirm policy, VAT invoice availability, delivery handling and substitutions before you commit.",
                    ],
                },
            ],
            faqs=[
                {"q": "What counts as a luxury corporate wine gift?", "a": "Usually a premium bottle, Champagne, fine wine, advice-led case or high-quality hamper where presentation and suitability are strong."},
                {"q": "When is a luxury wine gift appropriate?", "a": "For senior relationships, major milestones or key accounts where policy and timing are appropriate."},
                {"q": "Is fine wine a good corporate gift?", "a": "It can be if the recipient is known to appreciate wine. Otherwise, sparkling or a premium hamper may be safer."},
                {"q": "Should luxury gifts be approved internally?", "a": "Yes, meaningful-value gifts should be checked against internal policies and recorded."},
            ],
            related=["best-wine-gifts-under-100", "best-client-wine-gifts", "business-gift-wine-etiquette"],
            cta="Plan a luxury wine gift",
            cta_heading="Need a premium gift that still feels appropriate?",
            cta_text="Use the planner to shape a clear brief before approaching suppliers.",
        ),
        "thank-you-wine-gifts": enhanced_guide(
            title="Thank You Wine Gifts: Better Ways to Say Thanks Than a Random Bottle",
            h1="Thank You Wine Gifts: Better Ways to Say Thanks Than a Random Bottle",
            description="Warm, practical thank-you wine gift guidance for projects, referrals, hosts, teams, suppliers and partners.",
            intro="A thank-you gift is not really about wine. It is about making the thanks feel visible.",
            hero_bullets=[
                "Best for: project endings, referrals, hosts, partners and team thank-yous",
                "Typical budget: £25-£100",
                "Avoid: a random bottle with a generic note",
            ],
            opening_heading="Start with the reason",
            opening=[
                "Was it a referral? A project that needed patience? A host who went out of their way? A team that made difficult work easier? The reason changes the gift.",
                "Sometimes a bottle is enough. Sometimes a pair feels warmer. Sometimes a hamper or case is better because the thank-you belongs to a group. The message carries the emotion; the gift gives it somewhere to land.",
            ],
            best_fit_table={
                "headers": ["Thank-you moment", "Gift that fits", "Tone"],
                "rows": [
                    ["Project completion", "Sparkling or mixed pair", "Appreciative and specific."],
                    ["Referral", "Smart bottle or hamper", "Warm, not transactional."],
                    ["Host", "Food-friendly bottle", "Personal and simple."],
                    ["Team thank-you", "Mixed case or hamper", "Shareable."],
                ],
            },
            article_sections=[
                {
                    "id": "timing",
                    "heading": "Timing changes the feeling",
                    "paragraphs": [
                        "A thank-you sent soon after the moment feels natural. A thank-you sent months later can still work, but the note has to explain the connection. If the relationship is commercially sensitive, avoid sending during a decision window.",
                    ],
                    "editorial_note": "The note does more work than the bottle. Do not treat it as an afterthought.",
                },
                {
                    "id": "messages",
                    "heading": "A few ways to say it",
                    "messages": [
                        {"label": "Project", "text": "Thank you for helping get the project over the line. We appreciated the collaboration and pace."},
                        {"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."},
                        {"label": "Host", "text": "Thank you again for hosting. We hope this gives you something nice to open afterwards."},
                        {"label": "Team", "text": "A thank-you for the whole team. We appreciated the energy and care you brought to the work."},
                    ],
                },
                {
                    "id": "fit",
                    "heading": "Make the gift fit the thanks",
                    "paragraphs": [
                        "A small, genuine gesture can be stronger than a larger gift with no emotional logic. If the thank-you is personal, keep it personal. If it is for a team, make it shareable. If alcohol is uncertain, choose an equal-quality alternative.",
                    ],
                },
            ],
            faqs=[
                {"q": "What is a good thank-you wine gift?", "a": "A sparkling bottle, red/white pair, compact hamper or mixed case can work if it fits the recipient and occasion."},
                {"q": "How much should I spend on a thank-you wine gift?", "a": "Many thank-you gifts sit between £25 and £100, depending on relationship and policy."},
                {"q": "What should I write in the note?", "a": "Reference the specific help, project, referral or hospitality. Keep it short and warm."},
                {"q": "Is wine suitable for every thank-you?", "a": "No. Use alternatives when alcohol suitability is unclear."},
            ],
            related=["client-wine-gifts", "best-client-wine-gifts", "corporate-wine-gifts-uk"],
            cta="Plan a thank-you wine gift",
            cta_heading="Want the thank-you to feel more personal?",
            cta_text="Use the planner to match the gift route to the relationship and occasion.",
        ),
        "business-gift-wine-etiquette": enhanced_guide(
            title="Business Gift Wine Etiquette: How to Send Wine Without Making It Awkward",
            h1="Business Gift Wine Etiquette: How to Send Wine Without Making It Awkward",
            description="Clear UK business wine gifting etiquette covering value, timing, alcohol suitability, policies, notes and when not to send wine.",
            intro="Most etiquette problems are really judgement problems. The bottle is rarely the issue. The timing, value, assumptions and context are.",
            hero_bullets=[
                "Best for: policy-aware client and partner gifting",
                "Typical budget: depends on relationship and internal policy",
                "Avoid: gifts that feel like pressure or ignore alcohol suitability",
            ],
            opening_heading="Make it easy to accept",
            opening=[
                "A good business wine gift should be proportionate, explainable and easy for the recipient to accept. It should not create obligation, embarrassment or a compliance headache.",
                "This is not legal advice, but where the value is meaningful or the relationship is commercially sensitive, it is sensible to check internal gift policies.",
            ],
            best_fit_table={
                "headers": ["Judgement call", "Safer position", "Reason"],
                "rows": [
                    ["Timing", "After a milestone or thank-you moment", "Avoids pressure."],
                    ["Value", "Policy-aware and proportionate", "Keeps it defensible."],
                    ["Delivery", "Office unless home is appropriate", "Reduces awkwardness."],
                    ["Suitability", "Offer non-alcohol alternatives", "Avoids assumptions."],
                ],
            },
            article_sections=[
                {
                    "id": "adult",
                    "heading": "The adult-in-the-room checks",
                    "paragraphs": [
                        "Ask whether the recipient can accept it, whether alcohol is suitable, whether the value is proportionate and whether the timing could be misread. If any answer feels shaky, choose a safer route.",
                        "Cultural, religious, health and personal reasons can all make alcohol unsuitable without the recipient wanting to explain. Do not make the gift depend on them having to disclose that.",
                    ],
                    "editorial_note": "If the gift would be hard to explain in an email, do not send it yet.",
                },
                {
                    "id": "home-office",
                    "heading": "Home or office?",
                    "paragraphs": [
                        "Office delivery is often simpler for business gifts, but not always. Remote work and Christmas closures can make home delivery more practical, as long as address handling is appropriate and expected.",
                    ],
                },
            ],
            faqs=[
                {"q": "Is it appropriate to send wine as a business gift?", "a": "Sometimes, if it is proportionate, policy-aware and suitable for the recipient."},
                {"q": "Should wine gifts be sent to home or office?", "a": "Office delivery is often safer unless home delivery is appropriate, expected and handled carefully."},
                {"q": "Is this legal advice?", "a": "No. It is practical planning guidance. Use your own legal, procurement or compliance advice where needed."},
                {"q": "What if I do not know whether they drink?", "a": "Choose an alcohol-free or food-led alternative."},
            ],
            related=["client-gifting-etiquette-uk", "client-gift-policy-checklist", "corporate-wine-gifts-uk"],
            cta="Create a policy-aware gift plan",
            cta_heading="Want to avoid an awkward gift?",
            cta_text="Use ClientCellar to shape a more careful gift route before buying.",
        ),
        "corporate-event-wine-planning": enhanced_guide(
            title="Corporate Event Wine Planning: How Much to Buy and What to Serve",
            h1="Corporate Event Wine Planning: How Much to Buy and What to Serve",
            description="Practical corporate event wine planning guidance for receptions, dinners, team celebrations and client events.",
            intro="Event wine planning is not just choosing bottles. It is pacing, food, guest count, venue rules, delivery, glassware, chilling and making sure nobody feels forgotten.",
            hero_bullets=[
                "Best for: receptions, dinners, client events and team celebrations",
                "Typical budget: plan per guest, then confirm with suppliers",
                "Avoid: exact quantity promises without venue or supplier input",
            ],
            opening_heading="Plan the event, then the wine",
            opening=[
                "Start with the shape of the event. Is there a welcome drink? Is food being served? Is wine included during dinner or only at a reception? How long are guests in the room?",
                "Quantities should be treated as planning ranges, not guarantees. The sensible move is to estimate, then ask the supplier or venue to sanity-check the mix.",
            ],
            best_fit_table={
                "headers": ["Moment", "Planning direction", "Common miss"],
                "rows": [
                    ["Welcome drink", "Sparkling or adult alcohol-free alternative", "Forgetting non-drinkers."],
                    ["Reception", "White-led mix with some red", "Overbuying heavy reds."],
                    ["Dinner", "Food-led red and white split", "Ignoring the menu."],
                    ["Team celebration", "Inclusive drinks range", "Making the event too alcohol-centred."],
                ],
            },
            article_sections=[
                {
                    "id": "walkthrough",
                    "heading": "A simple event walk-through",
                    "paragraphs": [
                        "For a reception, think about speed and ease: sparkling at arrival, a white that works without food, a red that does not dominate, and proper alcohol-free options. For dinner, let the menu do more of the work. For a client event, restraint usually feels more professional than abundance.",
                        "Hosts often forget the practical bits: chilling, glassware, delivery windows, corkage, returns, substitutions and who is actually responsible for service on the day.",
                    ],
                    "editorial_note": "For events, the operational questions are as important as the bottle choice.",
                },
                {
                    "id": "supplier",
                    "heading": "Questions for the supplier or venue",
                    "paragraphs": [
                        "Ask whether they can supply the required quantities by the event date, advise on the red/white/sparkling split, deliver to the venue, support sale-or-return where available, and explain what substitutions may be made.",
                    ],
                },
            ],
            faqs=[
                {"q": "How much wine should I buy for a corporate event?", "a": "Use guest count, event length, food and format to create a planning estimate, then confirm with your supplier or venue."},
                {"q": "What wine should be served at a business reception?", "a": "A simple mix of sparkling, white, red and alcohol-free drinks usually works better than niche choices."},
                {"q": "Should corporate events include alcohol-free options?", "a": "Yes. Inclusive event planning should include adult alcohol-free alternatives."},
                {"q": "Can ClientCellar supply event wine?", "a": "No. ClientCellar provides planning guidance and supplier-route recommendations."},
            ],
            related=["wine-for-corporate-events", "wine-tasting-corporate-event", "wine-gifts-for-events"],
            cta="Plan a wine event",
            cta_heading="Planning wine for a corporate event?",
            cta_text="Use the event planner to estimate quantities, supplier questions and logistics.",
            cta_url="/event-planner",
        ),
        "wine-tasting-corporate-event": enhanced_guide(
            title="Wine Tasting Corporate Events: How to Make It Fun Without Making It Forced",
            h1="Wine Tasting Corporate Events: How to Make It Fun Without Making It Forced",
            description="Ideas for corporate wine tasting events, including hosted tastings, blind tasting, food pairing, team building and inclusive formats.",
            intro="Wine tasting events work best when they are not treated like a lecture. Nobody wants to be trapped in a room being quietly tested on tannins.",
            hero_bullets=[
                "Best for: team socials, client entertainment and hosted tasting events",
                "Typical budget: depends on host, wine, food and delivery",
                "Avoid: wine snobbery, compulsory drinking and formats with no pace",
            ],
            opening_heading="Give people permission to enjoy it",
            opening=[
                "A good tasting gives people something to talk about besides work. A blind tasting works because people are allowed to be wrong. A regional theme works because it gives the evening a story. Food pairing works because it turns the wine into a shared experience rather than a quiz.",
                "Keep it inclusive. Non-drinkers should not feel like spectators, and nobody should feel they need to perform expertise to belong in the room.",
            ],
            best_fit_table={
                "headers": ["Format", "Best for", "Why it works"],
                "rows": [
                    ["Hosted tasting", "Client-safe events", "Keeps tone and pace."],
                    ["Blind tasting", "Team socials", "Makes being wrong part of the fun."],
                    ["Regional theme", "More editorial feel", "Gives the event a story."],
                    ["Food pairing", "Premium events", "Feels complete."],
                    ["Virtual tasting", "Remote teams", "Delivery becomes the main risk."],
                ],
            },
            article_sections=[
                {
                    "id": "human",
                    "heading": "Keep the tasting human",
                    "paragraphs": [
                        "The host matters more than the rarity of the bottles. Choose someone who can read the room, keep explanations short and make beginners feel comfortable.",
                        "For teams, a simple scorecard or blind round can work well. For clients, keep the tone polished and relaxed. For remote groups, build in more lead time because delivery is part of the event.",
                    ],
                    "editorial_note": "Avoid making people prove they know wine. The event should give them confidence, not homework.",
                },
                {
                    "id": "inclusive",
                    "heading": "Do not make non-drinkers spectators",
                    "paragraphs": [
                        "Offer alcohol-free alternatives with the same level of care, include food and water, keep pour sizes modest, and make it clear that tasting does not mean compulsory drinking.",
                    ],
                },
            ],
            faqs=[
                {"q": "Are wine tastings good corporate events?", "a": "They can be, if they are hosted well, inclusive and not too heavy on wine knowledge."},
                {"q": "What format works best for a team wine tasting?", "a": "A relaxed hosted tasting, blind tasting or food-pairing format usually works well."},
                {"q": "Can wine tastings work remotely?", "a": "Yes, but delivery lead times, address handling and alcohol-free alternatives need planning."},
                {"q": "How do you avoid making a wine tasting feel forced?", "a": "Keep the structure simple, the tone relaxed, and avoid making attendees perform expertise."},
            ],
            related=["virtual-wine-tasting-for-teams", "wine-tasting-team-building", "corporate-event-wine-planning"],
            cta="Plan a wine event",
            cta_heading="Want a tasting that people actually enjoy?",
            cta_text="Use the event planner to shape format, supplier questions and event logistics.",
            cta_url="/event-planner",
        ),
    }
)

GUIDES.update(
    {
        "christmas-wine-gifts-for-clients": enhanced_guide(
            title="Christmas Wine Gifts for Clients",
            h1="Christmas wine gifts for clients that do not feel last-minute",
            description="Warm, practical guidance for client Christmas wine gifts, including timing, notes, supplier questions and safer alternatives.",
            intro="Christmas client gifting is where good intentions often meet a tired spreadsheet. The gift can be perfectly fine and still feel forgettable if it arrives late, says nothing specific, or looks like everyone got the same thing.",
            hero_bullets=["Best for: account teams, referrers and partner thank-yous", "Typical budget: £40-£150", "Avoid: late ordering, empty-office delivery and generic notes"],
            opening_heading="Do not let December do the thinking",
            opening=[
                "A festive wine gift needs a little more care than a normal thank-you. Offices close, people travel, suppliers substitute stock, and the same beige hamper appears everywhere.",
                "Start with the relationship and the delivery reality. A smaller, warmer gift with a good message usually beats a larger one that feels rushed.",
            ],
            best_fit_table={"headers": ["Recipient", "Better route", "Why"], "rows": [["Senior client", "Sparkling or elegant wine gift", "Classic but not overbearing"], ["Client team", "Mixed case or shareable hamper", "More useful than one bottle"], ["Referrer", "Bottle pair with a specific note", "Personal without being heavy"], ["Unclear alcohol suitability", "Food or alcohol-free alternative", "Avoids assumptions"]]},
            article_sections=[
                {"id": "timing", "heading": "The timing is part of the gift", "paragraphs": ["Ask suppliers about cut-offs before you choose the gift. Confirm whether the recipient will be at the office. A good gift delivered to a closed reception desk is not really a good gift."], "editorial_note": "The safest Christmas option is often the one with the cleanest fulfilment, not the fanciest packaging."},
                {"id": "message", "heading": "Make the message sound human", "messages": [{"label": "Client", "text": "Thank you for your partnership this year. We have really enjoyed working with you and hope you get a proper Christmas break."}, {"label": "Team", "text": "A festive thank-you for the whole team. We appreciated the collaboration and good humour this year."}]},
            ],
            faqs=[
                {"q": "What is a good Christmas wine gift for clients?", "a": "Sparkling wine, a balanced bottle pair, a mixed case or a food-and-wine hamper can all work when the recipient and delivery timing are right."},
                {"q": "When should we order Christmas client gifts?", "a": "Start supplier conversations well before December for larger lists, branded notes or multi-address delivery."},
            ],
            related=["christmas-corporate-wine-gifts", "corporate-wine-gifts-uk", "wine-gift-hampers-uk"],
            cta="Plan Christmas client gifts",
            cta_heading="Need a festive gift that feels considered?",
            cta_text="Use the planner to shape the recipient list, budget and supplier route before December gets noisy.",
        ),
        "staff-wine-gifts": enhanced_guide(
            title="Staff Wine Gifts",
            h1="Staff wine gifts without making alcohol the whole reward",
            description="Inclusive employee wine gift guidance covering choice, policy, alcohol-free options, delivery and budget.",
            intro="Staff wine gifts can be thoughtful, but they need a different kind of care from client gifts. The point is appreciation, not making everyone fit the same bottle.",
            hero_bullets=["Best for: team thank-yous, year-end gifts and small rewards", "Typical budget: £20-£75", "Avoid: alcohol-only gifting with no equal alternative"],
            opening_heading="Choice is the polite option",
            opening=[
                "A staff gift should not make anyone explain why they do not drink. Health, religion, pregnancy, recovery, preference and workplace culture can all matter.",
                "If wine is offered, make the alternative feel equally considered. A weak alcohol-free option can feel less inclusive than offering no wine at all.",
            ],
            best_fit_table={"headers": ["Team situation", "Better route", "Watch"], "rows": [["Small team", "Choice of bottle, hamper or alcohol-free", "Preference handling"], ["Large staff list", "Simple tiered options", "Address data and delivery"], ["Remote team", "Supplier fulfilment", "Failed delivery"], ["Mixed preferences", "Food or choice-led gift", "Alcohol assumptions"]]},
            article_sections=[
                {"id": "practical", "heading": "The practical stuff is the kindness", "paragraphs": ["Confirm headcount, budget including delivery, address handling and HR policy before choosing the supplier. A gift that arrives cleanly and lets people choose is often more appreciated than a clever bottle."], "editorial_note": "A good staff gift should not create admin for the person receiving it."},
                {"id": "message", "heading": "Keep the message collective", "paragraphs": ["Staff gift notes work best when they are simple and sincere. Thank the team for the year, the effort or the specific moment. Avoid performance-review language dressed up as warmth."]},
            ],
            faqs=[
                {"q": "Can you send wine gifts to employees?", "a": "Often yes, but check workplace policy and provide alcohol-free alternatives so the gift stays inclusive."},
                {"q": "What is a good staff alternative to wine?", "a": "Food hampers, coffee, tea, alcohol-free sparkling or choice-based gifts are usually safer for mixed teams."},
            ],
            related=["non-alcoholic-client-gifts", "wine-gifts-for-sales-teams", "virtual-wine-tasting-for-teams"],
            cta="Plan staff gifts",
            cta_heading="Planning gifts for a team?",
            cta_text="Use the gift planner to compare wine, hamper and alcohol-free routes before speaking to suppliers.",
        ),
        "client-thank-you-wine-gifts": enhanced_guide(
            title="Client Thank-You Wine Gifts",
            h1="Client thank-you wine gifts that sound like actual thanks",
            description="Professional thank-you wine gift ideas after a deal, project, referral or meeting.",
            intro="A client thank-you gift should feel connected to the thing you are thanking them for. Without that connection, even a polished bottle can feel like a standard dispatch.",
            hero_bullets=["Best for: projects, referrals, partners and post-meeting appreciation", "Typical budget: £30-£100", "Avoid: gifts that feel like pressure or a reward for a decision"],
            opening_heading="The gift still needs a reason",
            opening=[
                "The best thank-you gifts are specific. They refer to the project, the referral, the patience, the introduction or the effort. The wine matters, but the reason carries the gesture.",
                "If the timing is commercially sensitive, wait or choose a smaller route. A thank-you should not look like an attempt to influence what happens next.",
            ],
            best_fit_table={"headers": ["Moment", "Gift route", "Tone"], "rows": [["Project completion", "Sparkling or bottle pair", "Warm and specific"], ["Referral", "Smart bottle or compact hamper", "Grateful, not transactional"], ["Partner help", "Mixed case or hamper", "Relationship-led"], ["Senior contact", "Elegant single bottle", "Restrained"]]},
            article_sections=[
                {"id": "messages", "heading": "A few note options", "messages": [{"label": "Project", "text": "Thank you for helping make the project such a constructive one. We really appreciated the collaboration."}, {"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."}, {"label": "Meeting", "text": "Thank you for making the time. We appreciated the conversation and your openness."}]},
                {"id": "restraint", "heading": "Restraint helps", "paragraphs": ["A thank-you gift does not need to be grand. In business, proportion is part of the message. If the relationship is new or the context is sensitive, smaller and sincere is usually better."]},
            ],
            faqs=[
                {"q": "What should a client thank-you note say?", "a": "Reference the specific project, referral or help. Keep the wording warm, short and free of sales pressure."},
                {"q": "How much should a client thank-you wine gift cost?", "a": "Many sit between £30 and £100, depending on the relationship, policy and occasion."},
            ],
            related=["thank-you-wine-gifts", "client-wine-gifts", "business-gift-wine-etiquette"],
            cta="Create a thank-you gift plan",
            cta_heading="Want the thanks to land properly?",
            cta_text="Use ClientCellar to match the gift route to the reason, relationship and budget.",
        ),
        "corporate-wine-hampers": enhanced_guide(
            title="Corporate Wine Hampers",
            h1="Corporate wine hampers that are not just padded baskets",
            description="When to choose corporate wine hampers, budget guidance, branding notes and practical supplier questions.",
            intro="Wine hampers are useful because they feel broader than a single bottle. They also attract filler. The trick is knowing which kind you are buying.",
            hero_bullets=["Best for: mixed tastes, teams and presentation-led gifting", "Typical budget: £40-£150", "Avoid: oversized hampers with vague contents"],
            opening_heading="Fewer better items usually wins",
            opening=[
                "A good corporate hamper should feel complete: wine worth opening, food that makes sense with it, and packaging that protects the gift rather than pretending to be the gift.",
                "Branding can help, but only when it is restrained. A subtle note is often better than turning the hamper into a marketing object.",
            ],
            best_fit_table={"headers": ["Use case", "Hamper style", "Watch"], "rows": [["Client team", "Shareable wine-and-food hamper", "Dietary needs"], ["Christmas", "Seasonal but not novelty", "Delivery cut-offs"], ["Staff gift", "Choice-led hamper", "Alcohol alternatives"], ["VIP recipient", "Premium restrained hamper", "Policy limits"]]},
            article_sections=[
                {"id": "supplier", "heading": "Questions worth asking", "paragraphs": ["Ask what is fixed, what may be substituted, whether allergens are clearly listed, whether alcohol-free versions exist and what happens when delivery fails. These questions reveal more about the supplier than the product photo does."], "editorial_note": "Do not buy the hamper image. Buy the actual contents list."},
                {"id": "branding", "heading": "Branding should be quiet", "paragraphs": ["A gift note, sleeve or insert can be useful. Heavy branding can make the gift feel more like a campaign than a thank-you, especially for senior clients."]},
            ],
            faqs=[
                {"q": "When is a hamper better than a bottle?", "a": "When tastes are mixed, the gift is for a team, or you want food and presentation as part of the gesture."},
                {"q": "What should you check before ordering corporate hampers?", "a": "Check contents, allergens, substitutions, delivery dates, gift notes, VAT invoices and alcohol-free alternatives."},
            ],
            related=["wine-gift-hampers-uk", "food-and-wine-hampers", "luxury-wine-hampers-uk"],
            cta="Plan wine hampers",
            cta_heading="Need a hamper route that feels useful?",
            cta_text="Build a quick brief and compare hamper, wine case and alcohol-free routes.",
        ),
        "corporate-champagne-gifts": enhanced_guide(
            title="Corporate Champagne Gifts",
            h1="Corporate Champagne gifts, and when not to choose Champagne",
            description="A UK business guide to Champagne, English sparkling and Crémant-style corporate gifts.",
            intro="Champagne is useful shorthand for celebration. It is also predictable. Sometimes that is exactly what you need; sometimes it is a sign you have not thought past the label.",
            hero_bullets=["Best for: milestones, senior thank-yous and festive gifting", "Typical budget: £45-£150", "Avoid: using Champagne as a status shortcut"],
            opening_heading="Champagne is not a personality",
            opening=[
                "For a genuine celebration, Champagne can be perfect. For a careful client thank-you, English sparkling or a well-chosen mixed case might feel more thoughtful.",
                "The decision is not Champagne versus cheap. It is whether the celebration signal suits the relationship.",
            ],
            best_fit_table={"headers": ["Route", "Use when", "Watch"], "rows": [["Champagne", "Celebration is the point", "Can feel obvious"], ["English sparkling", "UK-focused and polished", "Less instantly recognised"], ["Crémant-style sparkling", "Budget needs flexibility", "Presentation matters"], ["Sparkling hamper", "Gift should be shared", "Check filler"]]},
            article_sections=[
                {"id": "judgement", "heading": "A note on restraint", "paragraphs": ["Champagne can look generous, but it can also look like a reflex. If the relationship is conservative or the value is sensitive, choose a calmer route and let the note carry the warmth."]},
                {"id": "alternatives", "heading": "Alternatives can be stronger", "paragraphs": ["English sparkling feels current and UK-relevant. A bottle pair gives more choice. A hamper can be better for a team. Alcohol-free sparkling deserves equal care when alcohol suitability is unclear."], "editorial_note": "The best sparkling gift is the one the recipient can accept and enjoy without awkwardness."},
            ],
            faqs=[
                {"q": "What is a good alternative to Champagne?", "a": "English sparkling wine, Crémant-style sparkling, a bottle pair or a premium hamper can all be strong alternatives."},
                {"q": "Is Champagne appropriate for clients?", "a": "It can be, especially for milestones, but policy, relationship and alcohol suitability should guide the choice."},
            ],
            related=["champagne-gifts-for-clients", "english-sparkling-corporate-gifts", "luxury-corporate-wine-gifts"],
            cta="Plan sparkling wine gifts",
            cta_heading="Not sure whether Champagne is the right signal?",
            cta_text="Use the planner to compare sparkling, hamper and mixed-case routes.",
        ),
        "virtual-wine-tasting-for-teams": enhanced_guide(
            title="Virtual Wine Tasting for Teams",
            h1="Virtual wine tasting for teams without the awkward video-call energy",
            description="Plan remote and hybrid team wine tasting events with budget, delivery and invite guidance.",
            intro="Virtual tastings can work brilliantly, but only if the delivery, host and format are doing real work. Otherwise it is just another video call with alcohol.",
            hero_bullets=["Best for: remote teams, hybrid socials and light team events", "Typical budget: £25-£75 per head", "Avoid: compulsory drinking and late address collection"],
            opening_heading="The pack is only half the event",
            opening=[
                "The host sets the tone. The pack gives people something to open. The format gives them permission to talk. Miss any of those and the tasting starts to drag.",
                "Alcohol-free packs should be part of the plan from the start, not a late apology.",
            ],
            best_fit_table={"headers": ["Format", "Best for", "Risk"], "rows": [["Hosted tasting", "Mixed confidence groups", "Host quality matters"], ["Blind tasting", "Team energy", "Needs clear instructions"], ["Food pairing", "More premium feel", "Delivery complexity"], ["Alcohol-free tasting", "Inclusive teams", "Needs equal quality"]]},
            article_sections=[
                {"id": "delivery", "heading": "Delivery is the event risk", "paragraphs": ["Collect addresses early, explain privacy handling, ask suppliers about missed deliveries and leave time for replacements. Remote events fail quietly when three people are waiting for packs that never arrived."]},
                {"id": "invite", "heading": "Set expectations in the invite", "paragraphs": ["Tell people what is arriving, whether food is needed, how long it will last, and that drinking is optional. A little clarity makes the event feel relaxed before it starts."]},
            ],
            faqs=[
                {"q": "Can virtual wine tastings work for remote teams?", "a": "Yes, if packs arrive on time, the host is engaging and alcohol-free options are available."},
                {"q": "How much does a virtual corporate wine tasting cost?", "a": "Many hosted formats sit around £25-£75 per head, but suppliers must confirm current pricing."},
            ],
            related=["wine-tasting-corporate-event", "wine-tasting-team-building", "corporate-event-wine-planning"],
            cta="Plan a virtual tasting",
            cta_heading="Planning a remote team tasting?",
            cta_text="Use the event planner to shape the format, supplier questions and logistics.",
            cta_url="/event-planner",
        ),
        "corporate-wine-tasting-london": enhanced_guide(
            title="Corporate Wine Tasting London",
            h1="Corporate wine tasting events in London that feel polished, not forced",
            description="Plan London corporate wine tastings for client entertainment, team socials and hosted private events.",
            intro="London gives you plenty of wine tasting options. The challenge is not finding one. It is choosing a format that fits the guests, timing, transport and tone.",
            hero_bullets=["Best for: client entertainment, team socials and private tastings", "Typical budget: £60-£150+ per head", "Avoid: awkward locations, late finishes and overly technical sessions"],
            opening_heading="Think about the evening after the tasting",
            opening=[
                "Transport matters when alcohol is involved. So does finish time, food, water, room layout and whether the format assumes everyone wants a wine lesson.",
                "For client entertainment, keep it polished and paced. For teams, give people something fun to do without making beginners feel exposed.",
            ],
            best_fit_table={"headers": ["Event type", "Better format", "Watch"], "rows": [["Client entertainment", "Hosted private room", "Tone and pacing"], ["Team social", "Blind tasting or relaxed host", "Beginner confidence"], ["Dinner add-on", "Food-pairing tasting", "Menu and service"], ["Premium group", "Merchant-led tasting", "Transport and finish time"]]},
            article_sections=[
                {"id": "venue", "heading": "The venue is part of the recommendation", "paragraphs": ["A brilliant tasting in an awkward location is still awkward. Ask about transport, private space, food, water, accessibility and cancellation terms before getting excited about the wine list."]},
                {"id": "brief", "heading": "Brief the supplier on the room, not just the wine", "paragraphs": ["Tell them who is attending, how formal the event should feel, whether clients are present, and how much wine knowledge the group is likely to have. That is how you avoid the lecture nobody asked for."]},
            ],
            faqs=[
                {"q": "How much should a London corporate tasting cost?", "a": "Costs vary by venue, host, food and wine. Use a planning budget, then confirm current pricing directly with suppliers."},
                {"q": "Are wine tastings good for client entertainment?", "a": "They can be, if the tone is polished, inclusive and not too alcohol-heavy."},
            ],
            related=["wine-tasting-corporate-event", "corporate-event-wine-planning", "virtual-wine-tasting-for-teams"],
            cta="Plan a London wine tasting",
            cta_heading="Need a clearer tasting brief?",
            cta_text="Use the event planner to shape format, guest count and supplier questions.",
            cta_url="/event-planner",
        ),
        "wine-tasting-team-building": enhanced_guide(
            title="Wine Tasting Team Building",
            h1="Wine tasting as team building, without making it weird",
            description="Use wine tasting as team building without making the event too boozy or exclusive.",
            intro="Wine tasting can be a good team-building format when it gives people permission to talk, guess, laugh and learn a little. It fails when it becomes a test.",
            hero_bullets=["Best for: team socials, away days and hybrid groups", "Typical budget: £25-£120 per head", "Avoid: drinking games, wine snobbery and compulsory participation"],
            opening_heading="Make being wrong part of the fun",
            opening=[
                "Blind tasting works because nobody has to be the expert. Food pairing works because the conversation has somewhere to go. A relaxed host works because they keep the room moving.",
                "The point is not heavy drinking. The point is shared attention and a little low-stakes discovery.",
            ],
            best_fit_table={"headers": ["Team need", "Format", "Why"], "rows": [["New team", "Relaxed hosted tasting", "Gives structure"], ["Established team", "Blind tasting", "Adds energy"], ["Premium away day", "Food pairing", "Feels complete"], ["Remote team", "Virtual packs", "Works across locations"]]},
            article_sections=[
                {"id": "inclusive", "heading": "Do not make non-drinkers spectators", "paragraphs": ["Offer alcohol-free options, keep pour sizes modest, include food and water, and avoid language that makes drinking sound compulsory. Inclusion is not a footnote; it is part of the event design."]},
                {"id": "host", "heading": "Choose the host carefully", "paragraphs": ["A good host can make ordinary wines fun. A bad host can make expensive wines feel like homework. Ask suppliers how they handle mixed-knowledge groups before booking."]},
            ],
            faqs=[
                {"q": "Are wine tastings good team-building events?", "a": "They can be, if the format is inclusive, beginner-friendly and not centred on drinking volume."},
                {"q": "What is the best wine tasting format for teams?", "a": "Blind tasting, relaxed hosted tastings and food-pairing sessions often work well for mixed groups."},
            ],
            related=["wine-tasting-corporate-event", "virtual-wine-tasting-for-teams", "corporate-event-wine-planning"],
            cta="Plan a team tasting",
            cta_heading="Want a team tasting that feels relaxed?",
            cta_text="Use the event planner to shape format, budget and supplier questions.",
            cta_url="/event-planner",
        ),
    }
)

GUIDES.update(
    {
        "corporate-wine-gifts-under-50": enhanced_guide(
            title="Corporate Wine Gifts Under £50",
            h1="Corporate wine gifts under £50 that do not feel cheap",
            description="Practical UK guidance for corporate wine gifts under £50, with honest trade-offs, safer routes and supplier checks.",
            intro="Under £50 is a useful budget when you stop trying to fake luxury. The smartest gifts at this level are focused, cleanly presented and easy to enjoy.",
            hero_bullets=["Best for: modest client thank-yous and smaller teams", "Typical budget: £30-£50", "Avoid: oversized packaging and weak gift sets"],
            opening_heading="Spend the money on the gift",
            opening=["A single good bottle, a sparkling option, a two-bottle pair or a compact wine-and-food gift can all work. The danger is spreading £50 across too many parts until none of them feel strong.", "Do not buy the box first. Buy the thing the recipient will actually open."],
            best_fit_table={"headers": ["Route", "Why it works", "Watch"], "rows": [["Sparkling bottle", "Feels celebratory", "Avoid novelty labels"], ["Two-bottle pair", "Gives choice", "Presentation still matters"], ["Compact hamper", "More complete gift", "Check filler"], ["Merchant pick", "Feels less generic", "Delivery may be simpler locally"]]},
            article_sections=[
                {"id": "trade-off", "heading": "The honest trade-off", "paragraphs": ["At this budget, choose clarity over size. If the recipient is a close client, a better bottle with a thoughtful note can feel more personal than a small hamper padded with average snacks."], "editorial_note": "A modest gift is fine. A modest gift pretending to be luxury is where it starts to feel awkward."},
                {"id": "supplier", "heading": "Ask before ordering", "paragraphs": ["Confirm gift messages, delivery timing, substitutions and whether VAT invoices are available. Those practical details make a small gift feel much more professional."]},
            ],
            faqs=[{"q": "Is £50 enough for a corporate wine gift?", "a": "Yes, if you choose one focused route rather than over-packaged fake luxury."}, {"q": "What is safest under £50?", "a": "Sparkling wine, a bottle pair or compact wine-and-food gift are usually safer than niche bottles."}],
            related=["best-wine-gifts-under-50", "corporate-wine-gifts-uk", "client-wine-gifts"],
            cta="Find a wine gift under £50",
            cta_heading="Need a polished gift within budget?",
            cta_text="Use the planner to compare sensible under-£50 routes before choosing a supplier.",
        ),
        "corporate-wine-gifts-under-100": enhanced_guide(
            title="Corporate Wine Gifts Under £100",
            h1="Corporate wine gifts under £100, where the choice starts to matter",
            description="How to spend up to £100 on corporate wine gifts without wasting money on packaging or prestige.",
            intro="Under £100 gives you room to choose properly. You can buy a better bottle, a useful pair, a small case or a hamper with real contents.",
            hero_bullets=["Best for: priority clients and warmer relationships", "Typical budget: £60-£100", "Avoid: gifts that look expensive but feel thin"],
            opening_heading="This is not just a bigger version of a £50 gift",
            opening=["At £100, you can choose a direction. One strong bottle says confidence. A pair says choice. A mixed case says usefulness. A hamper says sharing.", "The mistake is buying size for its own sake. Bigger packaging can make the gift feel less premium, not more."],
            best_fit_table={"headers": ["Choice", "Use it when", "Risk"], "rows": [["Premium bottle", "Taste is known", "Higher taste risk"], ["Bottle pair", "Taste is partly unknown", "Less dramatic"], ["Mixed case", "Recipient is wine-friendly", "Delivery weight"], ["Compact hamper", "Gift may be shared", "Filler"]]},
            article_sections=[
                {"id": "spend", "heading": "Where I would spend the money", "paragraphs": ["Put the budget into contents, delivery reliability and a proper note. If the supplier can support gift messages, VAT invoices and clear substitutions, that often matters more than a heavier box."], "editorial_note": "Premium should feel calm. It does not need to announce the price."},
                {"id": "fit", "heading": "Choose the route by recipient", "paragraphs": ["A senior individual may suit sparkling or a better bottle. A team usually needs a case or hamper. If alcohol is uncertain, use a food-led or alcohol-free route with the same budget respect."]},
            ],
            faqs=[{"q": "What is the best corporate wine gift under £100?", "a": "A premium bottle, bottle pair, compact case or hamper can all work. Choose based on recipient and occasion."}, {"q": "Is £100 too much for a client gift?", "a": "It depends on policy and relationship context. Keep the gift proportionate and easy to justify."}],
            related=["best-wine-gifts-under-100", "luxury-corporate-wine-gifts", "corporate-wine-gifts-uk"],
            cta="Plan a stronger wine gift",
            cta_heading="Want to use the budget well?",
            cta_text="Build a quick brief before choosing between bottle, case and hamper routes.",
        ),
        "champagne-gifts-for-clients": enhanced_guide(
            title="Champagne Gifts for Clients",
            h1="Champagne gifts for clients, without making it feel automatic",
            description="When Champagne works for client gifts, when English sparkling is smarter, and what to check before ordering.",
            intro="Champagne says celebration quickly. That is useful. It can also say you chose the most obvious option and stopped thinking.",
            hero_bullets=["Best for: milestones, senior clients and Christmas gifting", "Typical budget: £45-£150", "Avoid: Champagne as a shortcut for thoughtfulness"],
            opening_heading="Use Champagne when the signal fits",
            opening=["For a deal milestone, senior thank-you or festive gift, Champagne can be exactly right. For a quieter client relationship, English sparkling, a mixed case or a refined hamper may feel more considered.", "The question is not whether Champagne is good. The question is whether it is the right message."],
            best_fit_table={"headers": ["Scenario", "Better choice", "Reason"], "rows": [["Celebration", "Champagne", "Clear signal"], ["UK-focused gift", "English sparkling", "More distinctive"], ["Unknown taste", "Sparkling hamper", "Broader appeal"], ["Policy-sensitive", "Lower-key alternative", "Less showy"]]},
            article_sections=[
                {"id": "watch", "heading": "Where Champagne gets lazy", "paragraphs": ["The classic bottle can become a reflex. If every senior contact gets the same Champagne with the same note, the prestige disappears and the gift becomes admin."], "editorial_note": "A celebratory gift still needs a reason."},
                {"id": "questions", "heading": "Supplier questions", "paragraphs": ["Ask about gift packaging, delivery cut-offs, substitutions, gift notes and whether alcohol-free sparkling alternatives are available for recipients where alcohol is not suitable."]},
            ],
            faqs=[{"q": "Is Champagne a good client gift?", "a": "It can be, especially for milestones, but it should fit the relationship and policy context."}, {"q": "What is a good alternative to Champagne?", "a": "English sparkling, Crémant-style sparkling, a mixed case or a hamper can all be strong alternatives."}],
            related=["corporate-champagne-gifts", "english-sparkling-corporate-gifts", "client-wine-gifts"],
            cta="Plan a sparkling gift",
            cta_heading="Not sure Champagne is the right route?",
            cta_text="Use the planner to compare sparkling, wine case and hamper options.",
        ),
        "english-sparkling-corporate-gifts": enhanced_guide(
            title="English Sparkling Corporate Gifts",
            h1="English sparkling corporate gifts with a bit more point of view",
            description="How to use English sparkling wine for client gifts, Christmas gifting and business milestones.",
            intro="English sparkling can be a lovely corporate gift because it feels celebratory without being quite as predictable as Champagne.",
            hero_bullets=["Best for: UK-focused client gifts and milestones", "Typical budget: £35-£90", "Avoid: treating it as a cheaper Champagne substitute"],
            opening_heading="It works best when the UK angle matters",
            opening=["This is a good route when you want the gift to feel current, thoughtful and a little less obvious. It can work especially well for UK businesses, local relationships or Christmas gifts where Champagne feels too automatic.", "Do not sell it as almost-Champagne. Let it be its own choice."],
            best_fit_table={"headers": ["Use case", "Why it fits", "Watch"], "rows": [["Client milestone", "Celebratory but distinctive", "Recipient recognition"], ["Christmas gift", "Polished and seasonal", "Delivery cut-offs"], ["Local relationship", "UK relevance", "Supplier coverage"], ["Mixed group", "Pair with food or alternatives", "Alcohol suitability"]]},
            article_sections=[
                {"id": "positioning", "heading": "How to position it", "paragraphs": ["English sparkling works when the note is confident and simple. You do not need a lecture on production methods. A short line about celebration, thanks or the year is enough."]},
                {"id": "fit", "heading": "When not to use it", "paragraphs": ["If the recipient expects a globally recognised luxury signal, Champagne may be clearer. If alcohol suitability is unclear, use an alcohol-free sparkling or food-led option instead."]},
            ],
            faqs=[{"q": "Is English sparkling a good corporate gift?", "a": "Yes, especially when a UK-focused, celebratory gift fits the relationship."}, {"q": "Is English sparkling better than Champagne?", "a": "Not better universally. It is different: often more distinctive, sometimes less instantly recognised."}],
            related=["champagne-gifts-for-clients", "corporate-champagne-gifts", "corporate-wine-gifts-uk"],
            cta="Plan English sparkling gifts",
            cta_heading="Want a sparkling route with more character?",
            cta_text="Use the planner to compare sparkling wine and hamper options.",
        ),
        "red-wine-gifts-for-clients": enhanced_guide(
            title="Red Wine Gifts for Clients",
            h1="Red wine gifts for clients, and why taste risk matters",
            description="How to choose red wine gifts for clients without making risky assumptions about taste, style or food pairing.",
            intro="Red wine feels like a classic gift, but it carries more taste risk than people admit. Heavy, oaky or unusual reds can divide a room.",
            hero_bullets=["Best for: known red wine drinkers and winter gifts", "Typical budget: £25-£100", "Avoid: niche reds for recipients you barely know"],
            opening_heading="Red is safest when you know something",
            opening=["If you know the recipient enjoys red wine, this can be a warm and confident route. If you do not, a mixed pair or case is often smarter.", "The aim is not to impress with obscurity. It is to send something the recipient can open without thinking too hard."],
            best_fit_table={"headers": ["Recipient", "Better red route", "Watch"], "rows": [["Known red drinker", "Classic region or merchant pick", "Overly niche styles"], ["Unknown taste", "Red/white pair", "More choice"], ["Winter gift", "Food-friendly red", "Alcohol strength"], ["Team gift", "Mixed case", "Not everyone wants red"]]},
            article_sections=[
                {"id": "styles", "heading": "Familiar is not boring", "paragraphs": ["Rioja, Rhône-style reds, claret-style blends and other food-friendly classics can be safer business gifts than rare bottles with a story only the buyer understands."]},
                {"id": "note", "heading": "Do not make the wine the whole personality", "paragraphs": ["If the red is part of a thank-you, say why you are sending it. A good note makes a safe bottle feel considered rather than generic."], "editorial_note": "Most people would rather receive something enjoyable than something technically impressive."},
            ],
            faqs=[{"q": "Is red wine a good client gift?", "a": "It can be if the recipient likes red wine. If taste is unknown, a mixed pair or case is safer."}, {"q": "What red wine style is safest?", "a": "Classic, food-friendly styles are usually safer than very heavy or obscure bottles."}],
            related=["client-wine-gifts", "white-wine-gifts-for-clients", "best-client-wine-gifts"],
            cta="Plan red wine gifts",
            cta_heading="Know they like red wine?",
            cta_text="Use the planner to shape a safer bottle, pair or case brief.",
        ),
        "white-wine-gifts-for-clients": enhanced_guide(
            title="White Wine Gifts for Clients",
            h1="White wine gifts for clients that feel useful, not generic",
            description="How to choose white wine gifts for clients, summer gifting, lighter occasions and mixed preferences.",
            intro="White wine can be a very practical client gift. It often feels lighter, easier to share and less formal than a big red or Champagne.",
            hero_bullets=["Best for: summer gifts, lighter thank-yous and food-friendly options", "Typical budget: £25-£90", "Avoid: assuming one crisp white suits everyone"],
            opening_heading="White wine is quietly useful",
            opening=["For summer gifting, host thank-yous or lighter client gestures, white wine can feel more natural than a heavy red. It is also a good part of a mixed pair or case when taste is uncertain.", "The trick is not to choose something too sharp, sweet or obscure unless you know the recipient likes that style."],
            best_fit_table={"headers": ["Situation", "Better route", "Why"], "rows": [["Summer thank-you", "Crisp white or white pair", "Easy to enjoy"], ["Unknown taste", "Red/white pair", "Gives choice"], ["Food gift", "White with savoury hamper", "Useful pairing"], ["Premium client", "Merchant-selected white", "More thoughtful"]]},
            article_sections=[
                {"id": "pairing", "heading": "A white wine gift often works better as a pair", "paragraphs": ["A single white bottle can feel a little light for some business gifts. Pairing it with a red, sparkling or food item gives the recipient more flexibility and makes the gift feel more complete."]},
                {"id": "avoid", "heading": "Avoid the extremes", "paragraphs": ["Very sweet, very oaky or very sharp whites can be divisive. For business gifting, broad appeal usually matters more than showing off range."]},
            ],
            faqs=[{"q": "Is white wine a good client gift?", "a": "Yes, especially for summer, lighter gifts or as part of a bottle pair."}, {"q": "What white wine style is safest?", "a": "Crisp, food-friendly styles usually work better than extreme or niche bottles."}],
            related=["red-wine-gifts-for-clients", "client-wine-gifts", "best-wine-gifts-under-50"],
            cta="Plan white wine gifts",
            cta_heading="Need a lighter wine gift route?",
            cta_text="Use the planner to compare white wine, mixed pair and hamper options.",
        ),
        "wine-gifts-for-sales-teams": enhanced_guide(
            title="Wine Gifts for Sales Teams",
            h1="Wine gifts for sales teams without turning recognition into admin",
            description="Plan wine gifts for sales teams, incentives and recognition moments with inclusive alternatives and practical delivery checks.",
            intro="Sales team gifts can go wrong when the reward is treated like a bulk order rather than recognition. The gift needs to feel fair, easy to receive and not too one-size-fits-all.",
            hero_bullets=["Best for: incentives, end-of-quarter thanks and team recognition", "Typical budget: £25-£75", "Avoid: alcohol-only rewards and unclear delivery"],
            opening_heading="Recognition should feel fair",
            opening=["If one person gets a better gift than another, there should be a clear reason. If everyone gets the same thing, make sure it is suitable enough for the group.", "Choice is often the best way to avoid awkwardness: wine, hamper or alcohol-free route. That does not make it less thoughtful; it makes it more usable."],
            best_fit_table={"headers": ["Moment", "Gift route", "Watch"], "rows": [["Quarter close", "Bottle or small hamper", "Fairness"], ["Top performers", "Tiered premium route", "Clear criteria"], ["Whole team", "Choice-led gift", "Alcohol suitability"], ["Remote team", "Supplier delivery", "Address handling"]]},
            article_sections=[
                {"id": "message", "heading": "Do not make the note sound like a leaderboard", "paragraphs": ["A recognition message should thank people for effort, outcome or persistence without turning the gift into a public ranking unless that is the point of the incentive."]},
                {"id": "operations", "heading": "Delivery is part of the employee experience", "paragraphs": ["Failed deliveries and awkward address collection can take the shine off a reward. Confirm supplier file formats, lead times and alternatives before announcing the gift."]},
            ],
            faqs=[{"q": "Are wine gifts suitable for sales teams?", "a": "They can be, but offer alcohol-free alternatives and check workplace policy."}, {"q": "Should sales team gifts be tiered?", "a": "Only when the criteria are clear. Otherwise a choice-led equal gift may feel fairer."}],
            related=["staff-wine-gifts", "non-alcoholic-client-gifts", "virtual-wine-tasting-for-teams"],
            cta="Plan sales team gifts",
            cta_heading="Need a recognition gift that feels fair?",
            cta_text="Use the planner to compare team gift routes and alternatives.",
        ),
        "wine-gifts-for-agencies": enhanced_guide(
            title="Corporate Wine Gifts for Agencies",
            h1="Wine gifts for agencies, clients and creative partners",
            description="Agency-focused wine gift guidance for client thank-yous, project launches, referrals and Christmas gifting.",
            intro="Agency gifting has a particular tension: it should feel creative without becoming gimmicky, and polished without feeling like a procurement catalogue.",
            hero_bullets=["Best for: project launches, retainers, referrals and Christmas gifts", "Typical budget: £35-£120", "Avoid: novelty packaging and over-branded gifts"],
            opening_heading="Creativity is not the same as novelty",
            opening=["A good agency gift often connects to the project, relationship or launch. It does not need a joke label or a box full of brand colour.", "If the relationship is warm, a personal note can do more than custom packaging. If the gift is for a team, make it shareable."],
            best_fit_table={"headers": ["Agency moment", "Better route", "Why"], "rows": [["Project launch", "Sparkling or mixed pair", "Celebratory"], ["Retainer thank-you", "Mixed case", "Relationship-led"], ["Referral", "Compact hamper", "Warm and practical"], ["Christmas", "Seasonal case or hamper", "Easy to share"]]},
            article_sections=[
                {"id": "branding", "heading": "Keep branding restrained", "paragraphs": ["A tasteful insert or note is usually enough. Heavy branding can make the gift feel like another piece of campaign output rather than a thank-you."]},
                {"id": "tone", "heading": "Use the project in the message", "messages": [{"label": "Launch", "text": "A small thank-you for all the energy around the launch. We really enjoyed bringing it to life with you."}, {"label": "Retainer", "text": "Thank you for the trust and collaboration this year. We have loved working with your team."}]},
            ],
            faqs=[{"q": "What wine gifts work for agency clients?", "a": "Sparkling wine, mixed pairs, cases and hampers can all work when tied to the project or relationship."}, {"q": "Should agencies personalise wine gifts?", "a": "Subtle notes or inserts are usually safer than heavily branded bottles."}],
            related=["personalised-wine-gifts", "client-wine-gifts", "best-client-wine-gifts"],
            cta="Plan agency client gifts",
            cta_heading="Need a client gift with the right tone?",
            cta_text="Use the planner to shape a gift route around project, budget and relationship.",
        ),
        "wine-gifts-for-law-firms": enhanced_guide(
            title="Corporate Wine Gifts for Law Firms",
            h1="Wine gifts for law firms and professional relationships",
            description="Policy-aware wine gifting guidance for law firms, legal clients and professional services relationships.",
            intro="Legal-sector gifting needs restraint. The gift should feel professional, proportionate and easy to explain.",
            hero_bullets=["Best for: post-matter thank-yous and year-end appreciation", "Typical budget: £40-£120", "Avoid: lavish gifts and sensitive timing"],
            opening_heading="Professional is the point",
            opening=["This is not the place for gimmicks, trophy bottles or over-familiar notes. A calm bottle pair, refined hamper or sparkling gift can work well when the timing and policy context are right.", "If a matter, decision or procurement process is live, be careful. Appreciation should not look like pressure."],
            best_fit_table={"headers": ["Scenario", "Better route", "Watch"], "rows": [["Post-matter thanks", "Elegant bottle pair", "Timing"], ["Referral", "Modest hamper", "Gift limits"], ["Christmas", "Refined case or hamper", "Office closures"], ["Senior contact", "Restrained premium gift", "Policy approval"]]},
            article_sections=[
                {"id": "policy", "heading": "Policy first, gift second", "paragraphs": ["This is not legal advice, but where the value is meaningful or the relationship is commercially sensitive, it is sensible to check internal gift policies and keep a record of the reason and value."], "editorial_note": "If the gift is hard to explain, choose a smaller route or wait."},
                {"id": "message", "heading": "Keep the note precise", "paragraphs": ["Thank the recipient for the relationship, project or support without being effusive. In professional services, understated usually reads better."]},
            ],
            faqs=[{"q": "Can law firms send wine gifts?", "a": "Sometimes, if policy, timing and value are appropriate. Check internal guidance where needed."}, {"q": "What gift style is safest?", "a": "A restrained bottle pair, refined hamper or sparkling gift is usually safer than a showy bottle."}],
            related=["business-gift-wine-etiquette", "client-gift-policy-checklist", "client-wine-gifts"],
            cta="Plan a professional gift",
            cta_heading="Need a policy-aware gift route?",
            cta_text="Use the planner to shape a careful brief before contacting suppliers.",
        ),
        "wine-gifts-for-accountancy-firms": enhanced_guide(
            title="Corporate Wine Gifts for Accountancy Firms",
            h1="Wine gifts for accountancy firms, clients and referral partners",
            description="Practical wine gifting guidance for accountancy firms, including client thank-yous, referrals and Christmas gifts.",
            intro="Accountancy gifting tends to work best when it is useful, restrained and timely. The gift should support the relationship, not make it feel transactional.",
            hero_bullets=["Best for: client thank-yous, referral partners and Christmas gifting", "Typical budget: £35-£100", "Avoid: gifts that feel like pressure around decisions"],
            opening_heading="Make it useful, not flashy",
            opening=["A modest wine gift with a clear note can be stronger than an expensive-looking hamper with no reason behind it. For professional relationships, calm usually beats dramatic.", "Timing matters around renewals, referrals and sensitive advisory work. Send thanks for something that has happened, not to influence what might happen next."],
            best_fit_table={"headers": ["Recipient", "Gift route", "Reason"], "rows": [["Client", "Bottle pair or compact hamper", "Professional and useful"], ["Referral partner", "Sparkling or hamper", "Warm but not heavy"], ["Client team", "Mixed case", "Shareable"], ["Senior contact", "Restrained premium option", "Polished"]]},
            article_sections=[
                {"id": "note", "heading": "The note should be specific", "messages": [{"label": "Client", "text": "Thank you for trusting us this year. We really value the relationship and look forward to continuing to support you."}, {"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."}]},
                {"id": "checks", "heading": "The sensible checks", "paragraphs": ["Confirm gift value, delivery address, VAT invoice needs, substitutions and whether the recipient organisation has gift acceptance limits. None of this is glamorous. All of it matters."]},
            ],
            faqs=[{"q": "What wine gifts work for accountancy clients?", "a": "Bottle pairs, sparkling gifts, mixed cases and compact hampers can work when proportionate and timely."}, {"q": "Should referral gifts be expensive?", "a": "No. They should be warm, proportionate and policy-aware."}],
            related=["client-thank-you-wine-gifts", "business-gift-wine-etiquette", "corporate-wine-gifts-uk"],
            cta="Plan accountancy client gifts",
            cta_heading="Need a gift that feels professional?",
            cta_text="Use the planner to compare restrained wine and hamper routes.",
        ),
        "luxury-wine-gifts-for-clients": enhanced_guide(
            title="Luxury Wine Gifts for Clients",
            h1="Luxury wine gifts for clients without overdoing it",
            description="Premium client wine gift guidance covering Champagne, fine wine, hampers, policy and restraint.",
            intro="Luxury client gifting is not about making the gift as large as possible. It is about making the choice feel calm, appropriate and considered.",
            hero_bullets=["Best for: senior clients, key accounts and major milestones", "Typical budget: £100-£250+", "Avoid: trophy bottles and policy discomfort"],
            opening_heading="Expensive can still be thoughtless",
            opening=["A gift can cost a lot and still feel lazy if it is chosen only for status. Trophy bottles, huge boxes and oversized hampers often say more about the sender than the recipient.", "Restraint is not underspending. It is judgement."],
            best_fit_table={"headers": ["Luxury route", "Use when", "Risk"], "rows": [["Fine wine", "Recipient is known to care", "Too niche"], ["Champagne", "Celebration is clear", "Predictable"], ["Premium hamper", "Gift may be shared", "Filler"], ["Merchant case", "Advice matters", "Admin support varies"]]},
            article_sections=[
                {"id": "approval", "heading": "Approval is part of premium gifting", "paragraphs": ["If the value is meaningful, check policy and record the reason. A luxury gift should be easy to justify internally and easy for the recipient to accept."]},
                {"id": "recipient", "heading": "Buy for the recipient, not the room", "paragraphs": ["If they know wine, a specialist merchant route can work. If they do not, presentation, clarity and ease of enjoyment matter more than rarity."], "editorial_note": "Premium should feel thoughtful, not performative."},
            ],
            faqs=[{"q": "What is a luxury wine gift for a client?", "a": "A premium bottle, Champagne, fine wine case or high-quality hamper can all qualify if suitable and proportionate."}, {"q": "Are luxury gifts risky?", "a": "They can be where policy, timing or relationship context is unclear."}],
            related=["luxury-corporate-wine-gifts", "best-wine-gifts-under-100", "business-gift-wine-etiquette"],
            cta="Plan a luxury client gift",
            cta_heading="Need premium without awkwardness?",
            cta_text="Use the planner to shape a more careful premium gift route.",
        ),
        "luxury-wine-hampers-uk": enhanced_guide(
            title="Luxury Wine Hampers UK",
            h1="Luxury wine hampers in the UK, minus the filler",
            description="A critical UK buyer guide to luxury wine hampers for clients, partners and senior business contacts.",
            intro="Luxury hampers can be excellent. They can also be very expensive baskets of average things arranged beautifully.",
            hero_bullets=["Best for: premium client gifts and festive gifting", "Typical budget: £100-£250+", "Avoid: big hampers with vague contents"],
            opening_heading="Read the contents like a sceptic",
            opening=["The photo is not the gift. The contents list is the gift. Look for wine quality, food quality, allergen clarity, substitution policy and whether the hamper feels edited rather than inflated.", "Fewer better items usually look more premium than a giant basket padded with filler."],
            best_fit_table={"headers": ["Hamper route", "Best for", "Watch"], "rows": [["Wine-led hamper", "Wine-friendly client", "Food feels secondary"], ["Food-and-wine hamper", "Shared gift", "Allergens"], ["Champagne hamper", "Celebration", "Showiness"], ["Alcohol-free luxury hamper", "Mixed suitability", "Equal quality"]]},
            article_sections=[
                {"id": "filler", "heading": "The filler test", "paragraphs": ["If you removed the basket, ribbon and straw, would the gift still feel worth sending? That is the simplest way to judge a luxury hamper."]},
                {"id": "delivery", "heading": "Luxury still has to arrive cleanly", "paragraphs": ["Ask about delivery protection, failed deliveries, substitutions, gift notes, VAT invoices and address handling before committing. Premium presentation does not fix poor fulfilment."], "editorial_note": "Do not buy the packaging. Buy the gift."},
            ],
            faqs=[{"q": "Are luxury wine hampers good client gifts?", "a": "They can be where presentation matters and policy allows, especially if the contents are genuinely strong."}, {"q": "What should I check in a luxury hamper?", "a": "Check exact contents, allergens, substitutions, delivery timing and invoice availability."}],
            related=["wine-gift-hampers-uk", "corporate-wine-hampers", "food-and-wine-hampers"],
            cta="Plan a luxury hamper",
            cta_heading="Want a hamper that earns the word luxury?",
            cta_text="Use the planner to compare premium hamper and wine routes.",
        ),
        "wine-gifts-for-christmas": enhanced_guide(
            title="Wine Gifts for Christmas",
            h1="Wine gifts for Christmas that avoid the December rush",
            description="Plan Christmas wine gifts for clients and staff with timing, supplier questions and responsible gifting checks.",
            intro="Christmas wine gifts are rarely ruined by the wine alone. They are ruined by late orders, bad address data, generic notes and suppliers running out of the thing you wanted.",
            hero_bullets=["Best for: festive client, staff and partner thank-yous", "Typical budget: £30-£150", "Avoid: December panic and one-size-fits-all gifts"],
            opening_heading="Start before it feels urgent",
            opening=["The earlier you choose the route, the more room you have for alternatives, gift notes and clean delivery. Leave it late and you are mostly choosing what is still available.", "A thoughtful Christmas gift does not have to be elaborate. It has to arrive on time, suit the recipient and sound like it came from a person."],
            best_fit_table={"headers": ["Recipient", "Route", "Watch"], "rows": [["Client", "Sparkling, pair or hamper", "Policy and message"], ["Staff", "Choice-led gift", "Inclusivity"], ["Partner", "Bottle pair", "Tone"], ["Team", "Mixed case or shareable hamper", "Delivery location"]]},
            article_sections=[
                {"id": "empty-office", "heading": "The empty office problem", "paragraphs": ["December delivery to offices can be messy. Confirm whether people will be in, whether home delivery is appropriate, and what happens if the courier cannot deliver."]},
                {"id": "message", "heading": "Keep the message warmer than the spreadsheet", "messages": [{"label": "Client", "text": "Thank you for your support this year. We hope you and the team have a restful Christmas."}, {"label": "Staff", "text": "A small festive thank-you for everything this year. We really appreciate the work and care you have put in."}]},
            ],
            faqs=[{"q": "When should businesses order Christmas wine gifts?", "a": "Start supplier conversations well before December for larger lists, branding or multi-address delivery."}, {"q": "What is a safe Christmas wine gift?", "a": "Sparkling wine, a bottle pair, mixed case or hamper can work when matched to the recipient."}],
            related=["christmas-corporate-wine-gifts", "christmas-wine-gifts-for-clients", "staff-wine-gifts"],
            cta="Plan Christmas wine gifts",
            cta_heading="Trying to avoid December gifting panic?",
            cta_text="Use the planner to shape the list, budget and supplier route early.",
        ),
    }
)

GUIDES.update(
    {
        "best-wine-accessories-for-gifts": enhanced_guide(
            title="Best Wine Accessories for Gifts",
            h1="Wine accessories that are actually useful as gifts",
            description="Wine accessory gift ideas for clients and staff when alcohol itself may not be suitable.",
            intro="Wine accessories are where gifting can get gimmicky very quickly. The useful ones solve a small problem. The bad ones sit in a drawer.",
            hero_bullets=["Best for: alcohol-sensitive gifting and practical add-ons", "Typical budget: £15-£75", "Avoid: novelty gadgets and fragile showpieces"],
            opening_heading="Useful beats clever",
            opening=["If you are not sending alcohol, a wine-adjacent gift can still work. But the accessory has to be genuinely useful: glassware, a decent opener, a stopper, a tasting notebook, or something that supports an event.", "Avoid anything that promises to transform cheap wine or looks funny for five seconds and then becomes clutter."],
            best_fit_table={"headers": ["Accessory route", "Best for", "Watch"], "rows": [["Good opener", "Practical gift", "Cheap mechanisms"], ["Glassware", "Premium but fragile", "Breakage"], ["Tasting notebook", "Event follow-up", "Too niche"], ["Wine stopper", "Small thank-you", "Can feel slight"]]},
            article_sections=[
                {"id": "where-it-fits", "heading": "When accessories make sense", "paragraphs": ["They work best when alcohol is not suitable, when you need a practical add-on, or when the gift relates to a tasting event. They work less well when they are used as a substitute for thinking about the recipient."]},
                {"id": "avoid", "heading": "The novelty trap", "paragraphs": ["Most novelty accessories age badly. If you would not want it on your own kitchen counter, think twice before sending it to a client."]},
            ],
            faqs=[{"q": "Are wine accessories good client gifts?", "a": "They can be, especially when alcohol is unsuitable or the accessory is genuinely practical."}, {"q": "What wine accessory is safest?", "a": "A quality opener, glassware or tasting notebook is usually safer than novelty gadgets."}],
            related=["non-alcoholic-client-gifts", "wine-tasting-corporate-event", "business-gift-wine-etiquette"],
            cta="Plan a non-wine gift route",
            cta_heading="Need a wine-adjacent gift instead?",
            cta_text="Use the planner to compare wine, accessory and alcohol-free options.",
        ),
        "client-gift-policy-checklist": enhanced_guide(
            title="Client Gift Policy Checklist",
            h1="A client gift policy checklist for sensible wine gifting",
            description="A practical checklist for client wine gifts, policy limits, approvals, recipient suitability and audit trails.",
            intro="Gift policy is not the exciting part of client gifting. It is the part that stops a thoughtful gesture becoming an awkward internal conversation.",
            hero_bullets=["Best for: sales, account, finance and operations teams", "Typical budget: policy-led", "Avoid: meaningful-value gifts with no approval trail"],
            opening_heading="Check before the gift gets emotional",
            opening=["This is not legal advice, but where the value is meaningful or the relationship is commercially sensitive, it is sensible to check internal gift policies.", "The aim is simple: the gift should be proportionate, explainable and easy for the recipient to accept."],
            best_fit_table={"headers": ["Check", "Why it matters", "What to do"], "rows": [["Value", "Approval and perception", "Set tiers"], ["Timing", "Avoid pressure", "Send after milestones"], ["Alcohol", "Suitability", "Offer alternatives"], ["Record", "Audit trail", "Keep reason and cost"]]},
            article_sections=[
                {"id": "judgement", "heading": "Most policy issues are judgement issues", "paragraphs": ["If the gift would be hard to explain in an email, lower the value, change the timing or choose a safer route. The best gifts are easy to defend because they are proportionate to the relationship."]},
                {"id": "checklist", "heading": "The practical approval note", "paragraphs": ["Record who the gift is for, why it is being sent, approximate value, supplier route, delivery method and whether alcohol-free alternatives are available. That small note can save a lot of reconstruction later."], "editorial_note": "A good gift should not create a compliance problem for either side."},
            ],
            faqs=[{"q": "What should a client gift policy checklist include?", "a": "Value, timing, recipient suitability, alcohol alternatives, approval route, delivery method and record keeping."}, {"q": "Is this legal advice?", "a": "No. It is practical planning guidance. Use legal, compliance or procurement advice where needed."}],
            related=["business-gift-wine-etiquette", "client-gifting-etiquette-uk", "how-much-to-spend-on-client-gifts"],
            cta="Create a policy-aware plan",
            cta_heading="Need a gift you can explain clearly?",
            cta_text="Use the planner to shape a practical, policy-aware gift route.",
        ),
        "client-gifting-etiquette-uk": enhanced_guide(
            title="Client Gifting Etiquette UK",
            h1="Client gifting etiquette in the UK, without the awkwardness",
            description="UK client gifting etiquette for wine gifts, hampers and thank-you presents.",
            intro="Client gifting etiquette is mostly about not making the recipient uncomfortable. The gift should feel appreciative, not loaded.",
            hero_bullets=["Best for: client thank-yous, Christmas gifts and professional relationships", "Typical budget: £25-£100", "Avoid: pressure, excess and assumptions about alcohol"],
            opening_heading="The gift should be easy to accept",
            opening=["There is a fine line between generous and awkward. Cross it, and the recipient has to decide whether the gift is appropriate before they can enjoy it.", "Keep value proportionate, timing sensible and wording human. If alcohol is uncertain, provide an equal-quality alternative."],
            best_fit_table={"headers": ["Etiquette question", "Safer answer", "Reason"], "rows": [["When?", "After a real moment", "Avoids pressure"], ["How much?", "Proportionate", "Keeps it comfortable"], ["What?", "Useful and suitable", "Avoids assumptions"], ["Where?", "Office unless home is appropriate", "Reduces awkwardness"]]},
            article_sections=[
                {"id": "not-legal", "heading": "This is judgement, not theatre", "paragraphs": ["This is not legal advice, but where the value is meaningful or the relationship is commercially sensitive, it is sensible to check internal gift policies. A modest, well-timed gift is often stronger than a lavish one."]},
                {"id": "message", "heading": "Tone matters", "paragraphs": ["Avoid language that sounds like a sales nudge. Thank them for the work, relationship, project or support, and then stop. The note does not need to earn a copywriting award."]},
            ],
            faqs=[{"q": "What is good client gifting etiquette?", "a": "Keep gifts proportionate, policy-aware, useful and free of pressure."}, {"q": "Is wine appropriate for client gifting?", "a": "It can be, where alcohol is suitable and the timing and value are appropriate."}],
            related=["business-gift-wine-etiquette", "client-gift-policy-checklist", "client-wine-gifts"],
            cta="Plan an appropriate client gift",
            cta_heading="Want to avoid an awkward gift?",
            cta_text="Use ClientCellar to compare safer gift routes before ordering.",
        ),
        "corporate-gifting-recipient-csv-template": enhanced_guide(
            title="Corporate Gifting Recipient CSV Template",
            h1="Corporate gifting recipient lists without spreadsheet chaos",
            description="How to prepare recipient data for corporate wine gifts, multi-address delivery and supplier upload templates.",
            intro="Recipient data is where corporate gifting quietly falls apart. The gift can be lovely, but if the addresses are messy, the experience is not.",
            hero_bullets=["Best for: bulk gifting and multi-address orders", "Typical budget: admin time before supplier upload", "Avoid: collecting addresses after choosing a delivery date"],
            opening_heading="The spreadsheet is part of the gift",
            opening=["A clean recipient list saves supplier back-and-forth, failed deliveries and awkward follow-ups. It also helps you spot alcohol-free needs, office closures and duplicate recipients before the order is placed.", "This is not glamorous work. It is the difference between a smooth gifting campaign and a week of courier emails."],
            best_fit_table={"headers": ["Field", "Why it matters", "Watch"], "rows": [["Name", "Gift note and delivery", "Spelling"], ["Address", "Successful delivery", "Office closures"], ["Preference", "Suitability", "Privacy"], ["Message", "Personalisation", "Length limits"]]},
            article_sections=[
                {"id": "format", "heading": "Ask the supplier before building the file", "paragraphs": ["Some suppliers want one address per row. Some need phone numbers. Some have message character limits. Get their required format early so you do not rebuild the sheet twice."]},
                {"id": "privacy", "heading": "Handle addresses carefully", "paragraphs": ["Only collect what you need, store it sensibly, and avoid forwarding spreadsheets around casually. For home delivery, be especially careful about who has access."]},
            ],
            faqs=[{"q": "What should a corporate gifting CSV include?", "a": "Recipient name, delivery address, gift message, preference or alternative route where needed, and any supplier-required fields."}, {"q": "Should I collect home addresses for gifts?", "a": "Only where appropriate and handled carefully. Confirm privacy and delivery needs before collecting data."}],
            related=["client-gift-policy-checklist", "wine-gifts-for-christmas", "staff-wine-gifts"],
            cta="Plan a bulk gift order",
            cta_heading="Need a cleaner recipient brief?",
            cta_text="Use the planner to shape the order before you prepare supplier data.",
        ),
        "food-and-wine-hampers": enhanced_guide(
            title="Food and Wine Hampers",
            h1="Food and wine hampers that feel generous, not padded",
            description="How to choose food and wine hampers for clients, staff and partners, including allergens, budgets and delivery.",
            intro="Food and wine hampers are safe until they are not. They work beautifully when the contents are useful and shareable. They feel lazy when the basket is doing more work than the food.",
            hero_bullets=["Best for: teams, mixed preferences and Christmas gifts", "Typical budget: £40-£150", "Avoid: filler, unclear allergens and vague substitutions"],
            opening_heading="Look past the basket",
            opening=["The best hampers are edited. Good wine, sensible food, clear contents, clear delivery. The worst ones are big, beige and full of tiny things nobody would choose separately.", "If dietary needs or alcohol suitability are unclear, ask for alternatives before you order."],
            best_fit_table={"headers": ["Recipient", "Hamper route", "Watch"], "rows": [["Client team", "Shareable savoury and wine", "Allergens"], ["Staff", "Choice-led hamper", "Alcohol-free versions"], ["Senior client", "Restrained premium hamper", "Filler"], ["Christmas", "Seasonal food-and-wine", "Cut-offs"]]},
            article_sections=[
                {"id": "contents", "heading": "The contents list tells the truth", "paragraphs": ["Read it closely. If the wine is vague, the food looks generic, or substitutions are broad, the hamper may be weaker than the photograph suggests."]},
                {"id": "delivery", "heading": "Food creates delivery questions", "paragraphs": ["Ask about shelf life, perishable items, delivery windows, failed deliveries and whether the hamper can be sent to home or office addresses."]},
            ],
            faqs=[{"q": "Are food and wine hampers safer than wine alone?", "a": "Often they are more flexible, but allergens, alcohol suitability and delivery still need checking."}, {"q": "What should a good hamper include?", "a": "Good wine, useful food, clear allergen information and reliable packaging."}],
            related=["wine-gift-hampers-uk", "corporate-wine-hampers", "luxury-wine-hampers-uk"],
            cta="Plan a hamper gift",
            cta_heading="Need a hamper that feels properly chosen?",
            cta_text="Use the planner to compare hamper, wine and alcohol-free routes.",
        ),
        "how-much-to-spend-on-client-gifts": enhanced_guide(
            title="How Much to Spend on Client Gifts",
            h1="How much to spend on client gifts without making it awkward",
            description="A practical UK guide to client gift budgets, including wine gift bands and policy checks.",
            intro="Client gift budgets are not about finding the magic number. They are about choosing an amount that fits the relationship, the moment and the policy context.",
            hero_bullets=["Best for: budget setting and approval conversations", "Typical budget: £25-£150", "Avoid: copying another company’s budget without context"],
            opening_heading="The number needs a reason",
            opening=["A £40 gift can feel thoughtful if the note is specific. A £150 gift can feel awkward if the timing is wrong. Spend is only one part of the signal.", "Set tiers before you choose suppliers. Otherwise the catalogue will quietly decide your budget for you."],
            best_fit_table={"headers": ["Budget", "Use it for", "Judgement"], "rows": [["Under £25", "Small gestures", "Keep expectations honest"], ["£25-£50", "Common thank-yous", "Good for bottle pairs or compact gifts"], ["£50-£100", "Priority clients", "Strong corporate range"], ["£100+", "Senior or key accounts", "Approval recommended"]]},
            article_sections=[
                {"id": "all-in", "heading": "Budget all-in, not just the bottle", "paragraphs": ["Delivery, VAT, gift notes, substitutions and multi-address handling can change the real cost. Build the working budget before judging whether the gift feels affordable."]},
                {"id": "policy", "heading": "More spend means more explanation", "paragraphs": ["Higher-value gifts should have a clearer reason and approval trail. If you are spending more to compensate for a vague message, stop and fix the message first."], "editorial_note": "A client gift should not feel like a bribe, a flex, or an apology."},
            ],
            faqs=[{"q": "What is a normal client gift budget?", "a": "Many businesses use £25-£75 for practical gifts, but the right budget depends on policy, relationship and occasion."}, {"q": "Should delivery be included in the budget?", "a": "Yes. Work with the full cost, including VAT and delivery where relevant."}],
            related=["client-gift-policy-checklist", "best-wine-gifts-under-50", "best-wine-gifts-under-100"],
            cta="Set a gift budget",
            cta_heading="Need a gift budget that makes sense?",
            cta_text="Use the planner to turn recipient type and occasion into a practical budget route.",
        ),
        "non-alcoholic-client-gifts": enhanced_guide(
            title="Non-Alcoholic Client Gifts",
            h1="Non-alcoholic client gifts that do not feel like the backup option",
            description="Client gift ideas and checks for situations where wine or alcohol may not be suitable.",
            intro="Alcohol-free gifting should not feel like second prize. If alcohol is unsuitable, the alternative should have the same level of care and budget respect.",
            hero_bullets=["Best for: mixed groups, staff gifts and unknown preferences", "Typical budget: £25-£100", "Avoid: treating alternatives as an afterthought"],
            opening_heading="Equal quality matters",
            opening=["The mistake is offering a polished wine gift and a weak alternative. That quietly tells recipients they were not the main plan.", "Food hampers, premium coffee or tea, alcohol-free sparkling, soft drinks and choice-led gifts can all feel generous when chosen properly."],
            best_fit_table={"headers": ["Route", "Best for", "Watch"], "rows": [["Food hamper", "Broad appeal", "Allergens"], ["Coffee or tea", "Workplace-safe gifting", "Presentation"], ["Alcohol-free sparkling", "Celebration", "Quality"], ["Choice-led gift", "Unknown preferences", "Admin"]]},
            article_sections=[
                {"id": "sensitivity", "heading": "Do not make people explain", "paragraphs": ["People may avoid alcohol for health, religion, recovery, pregnancy, preference or many other reasons. A good gifting process does not require them to disclose why."]},
                {"id": "presentation", "heading": "Make the alternative feel deliberate", "paragraphs": ["Use clear packaging, good supplier pages and thoughtful notes. Alcohol-free should mean alcohol-free, not care-free."]},
            ],
            faqs=[{"q": "Should businesses offer non-alcoholic gifts?", "a": "Yes, especially for staff gifts, mixed groups and recipients whose preferences are unknown."}, {"q": "What are good non-alcoholic client gifts?", "a": "Food hampers, premium coffee, tea, alcohol-free sparkling and choice-led gifts can all work."}],
            related=["business-gift-wine-etiquette", "staff-wine-gifts", "best-wine-accessories-for-gifts"],
            cta="Plan an alcohol-free route",
            cta_heading="Need an inclusive gift option?",
            cta_text="Use the planner to compare wine, hamper and alcohol-free supplier routes.",
        ),
        "personalised-wine-gifts": enhanced_guide(
            title="Personalised Wine Gifts",
            h1="Personalised wine gifts without making the branding too loud",
            description="A practical guide to personalised wine gifts for clients, including branding, notes and delivery timing.",
            intro="Personalisation can make a wine gift feel considered. It can also turn a thoughtful gesture into branded merchandise with a cork.",
            hero_bullets=["Best for: small client lists, projects and Christmas campaigns", "Typical budget: £40-£150", "Avoid: novelty labels and rushed proofing"],
            opening_heading="Start with the note, not the label",
            opening=["A gift note is often the safest and strongest form of personalisation. Custom labels, sleeves and boxes add lead time, proofing risk and minimum order questions.", "If branding helps the recipient understand the context, use it quietly. If it mainly helps you feel visible, rethink it."],
            best_fit_table={"headers": ["Personalisation", "Best for", "Watch"], "rows": [["Gift note", "Most client gifts", "Message quality"], ["Branded insert", "Campaigns", "Tone"], ["Custom sleeve", "Larger orders", "Lead time"], ["Bottle label", "Informal gifts", "Novelty risk"]]},
            article_sections=[
                {"id": "proofing", "heading": "Proofing is where delays happen", "paragraphs": ["Ask suppliers for artwork requirements, proof deadlines, minimum orders and fallback plain packaging. Personalisation that misses the occasion is not a better gift."]},
                {"id": "tone", "heading": "Personal does not mean overfamiliar", "paragraphs": ["Use the project, milestone or relationship in the message. Avoid names, jokes or design choices that could feel too intimate for a business gift."]},
            ],
            faqs=[{"q": "Are personalised wine gifts good for clients?", "a": "They can be if restrained and professionally executed. Gift notes are often safer than heavily branded bottles."}, {"q": "What personalisation is safest?", "a": "A thoughtful gift note or discreet insert is usually safer than a custom bottle label."}],
            related=["wine-gifts-for-agencies", "best-client-wine-gifts", "corporate-gifting-recipient-csv-template"],
            cta="Plan personalised gifts",
            cta_heading="Need personalisation without the risk?",
            cta_text="Use the planner to shape a gift route before asking suppliers about branding.",
        ),
        "wine-gift-baskets-uk": enhanced_guide(
            title="Wine Gift Baskets UK",
            h1="Wine gift baskets in the UK, and when a hamper is safer",
            description="UK wine gift basket buying guidance for corporate clients, staff and partner gifts.",
            intro="Wine baskets can look charming. They can also be fragile, awkward to ship and less practical than a boxed hamper.",
            hero_bullets=["Best for: smaller gifts and presentation-led gestures", "Typical budget: £30-£100", "Avoid: fragile baskets with unclear delivery protection"],
            opening_heading="Pretty is not the same as practical",
            opening=["A basket can work when presentation is the point and delivery is controlled. For courier-heavy corporate gifting, boxed hampers are often safer.", "Look at the contents, packaging protection and substitution policy before choosing the prettier option."],
            best_fit_table={"headers": ["Route", "Best for", "Watch"], "rows": [["Wine basket", "Local or smaller gift", "Fragility"], ["Boxed hamper", "Courier delivery", "Less decorative"], ["Wine-plus-food set", "Simple thank-you", "Contents"], ["Alcohol-free basket", "Mixed suitability", "Quality"]]},
            article_sections=[
                {"id": "delivery", "heading": "Delivery decides a lot", "paragraphs": ["If the basket needs to travel through standard courier networks, ask how it is protected. A gift that arrives damaged does not feel charming."]},
                {"id": "contents", "heading": "Still read the contents list", "paragraphs": ["Like hampers, baskets can hide weak contents behind presentation. Fewer better items are usually stronger than a larger-looking arrangement."]},
            ],
            faqs=[{"q": "What is the difference between a wine basket and a hamper?", "a": "Baskets are often presentation-led and compact; hampers may be boxed and easier for courier delivery."}, {"q": "Are wine baskets good corporate gifts?", "a": "They can be for smaller or local gifts, but delivery protection and contents matter."}],
            related=["food-and-wine-hampers", "corporate-wine-hampers", "wine-gift-hampers-uk"],
            cta="Compare baskets and hampers",
            cta_heading="Not sure whether a basket is practical?",
            cta_text="Use the planner to compare basket, hamper and wine-case routes.",
        ),
        "wine-gifts-for-events": enhanced_guide(
            title="Wine Gifts for Events",
            h1="Wine gifts for events, speakers and follow-ups",
            description="Plan wine gifts for event attendees, speakers, hosts and clients with delivery and suitability checks.",
            intro="Event wine gifts work best when they feel connected to the event. Otherwise they can feel like a delayed promo item.",
            hero_bullets=["Best for: speaker thank-yous, VIP attendees and post-event client follow-up", "Typical budget: £20-£100", "Avoid: bulk sending without consent or context"],
            opening_heading="The event gives the gift its reason",
            opening=["A speaker thank-you, VIP follow-up or hosted-tasting pack can feel thoughtful when the message connects back to the event. A generic bottle sent two weeks later can feel confusing.", "Address handling, alcohol suitability and timing matter more here than in ordinary gifting because event lists are often messier."],
            best_fit_table={"headers": ["Event use", "Gift route", "Watch"], "rows": [["Speaker thank-you", "Bottle pair or hamper", "Policy"], ["VIP attendee", "Sparkling or compact gift", "Consent"], ["Post-event follow-up", "Modest bottle", "Timing"], ["Tasting pack", "Supplier-led delivery", "Lead time"]]},
            article_sections=[
                {"id": "data", "heading": "Do not treat attendee data casually", "paragraphs": ["Confirm whether you have the right basis and expectation for sending physical gifts. Keep address handling tight and avoid sharing spreadsheets more widely than needed."]},
                {"id": "message", "heading": "Make the event connection explicit", "messages": [{"label": "Speaker", "text": "Thank you again for joining us and giving the session such useful energy. A small thank-you from the team."}, {"label": "VIP attendee", "text": "Thank you for being part of the event. We appreciated your time and hope this gives you something enjoyable to open afterwards."}]},
            ],
            faqs=[{"q": "Can wine gifts be sent after events?", "a": "Yes, where appropriate, but address handling, recipient suitability and gift policy should be checked first."}, {"q": "What is a good speaker thank-you gift?", "a": "A bottle pair, hamper or alcohol-free alternative with a specific note can work well."}],
            related=["corporate-event-wine-planning", "wine-tasting-corporate-event", "corporate-gifting-recipient-csv-template"],
            cta="Plan event gifts",
            cta_heading="Need event gifts that feel connected?",
            cta_text="Use the planner to shape an event gift or follow-up route.",
        ),
        "wine-gifts-for-new-business": enhanced_guide(
            title="Wine Gifts for New Business",
            h1="Wine gifts for new business relationships, handled carefully",
            description="How to approach wine gifts for new clients and partners while keeping compliance and tone in mind.",
            intro="New-business gifts need caution. The timing can change the meaning of the gift more than the bottle does.",
            hero_bullets=["Best for: post-signature welcomes and completed milestones", "Typical budget: £25-£100", "Avoid: gifts during active decisions or negotiations"],
            opening_heading="Wait until the decision is done",
            opening=["A gift before a decision can feel like pressure. A gift after the relationship is agreed can feel like welcome. That difference matters.", "Keep the value modest unless policy and context clearly support more. The gift should mark the beginning of the relationship, not try to buy it."],
            best_fit_table={"headers": ["Moment", "Better route", "Why"], "rows": [["Post-signature", "Modest bottle or pair", "Welcoming"], ["Onboarding", "Compact hamper", "Useful and warm"], ["Partner introduction", "Sparkling or food gift", "Celebratory"], ["During negotiation", "No gift yet", "Avoid pressure"]]},
            article_sections=[
                {"id": "record", "heading": "Record the reason", "paragraphs": ["For new relationships, keep a clear note of why the gift was sent, approximate value and timing. This is boring until someone asks."]},
                {"id": "message", "heading": "Keep the note about the relationship", "messages": [{"label": "Welcome", "text": "We are looking forward to working together. A small welcome from the team."}, {"label": "Partner", "text": "Thank you for the introduction and the early conversations. We appreciate the trust."}]},
            ],
            faqs=[{"q": "Should you send wine gifts to new clients?", "a": "Only where policy and timing are appropriate. Avoid gifts during active procurement or decision-making."}, {"q": "What is a safe new-business gift?", "a": "A modest bottle, bottle pair, hamper or alcohol-free alternative sent after the commercial decision is complete."}],
            related=["business-gift-wine-etiquette", "client-gift-policy-checklist", "client-wine-gifts"],
            cta="Plan a new-client gift",
            cta_heading="Need a careful welcome gift?",
            cta_text="Use the planner to choose a proportionate route and avoid awkward timing.",
        ),
        "wine-gifts-for-thank-you": enhanced_guide(
            title="Wine Gifts for Thank You",
            h1="Wine gifts for thank-you moments that feel genuine",
            description="Choose thank-you wine gifts for clients, referrers and partners without making the gesture feel excessive.",
            intro="A thank-you wine gift should not feel like a random bottle looking for a reason. The reason should come first.",
            hero_bullets=["Best for: referrals, project endings and partner appreciation", "Typical budget: £25-£100", "Avoid: vague notes and excessive gestures"],
            opening_heading="Say what the thanks is for",
            opening=["Was it a referral, a piece of help, a good project, a generous introduction? Put that in the note. The wine gives the thanks a physical form, but the message carries the meaning.", "If the gift is for a group, make it shareable. If alcohol is uncertain, choose a food or alcohol-free route with the same care."],
            best_fit_table={"headers": ["Thank-you", "Better route", "Tone"], "rows": [["Referral", "Smart bottle or hamper", "Grateful"], ["Project", "Sparkling or pair", "Specific"], ["Host", "Food-friendly bottle", "Warm"], ["Team", "Mixed case", "Shareable"]]},
            article_sections=[
                {"id": "messages", "heading": "Examples that do not overdo it", "messages": [{"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."}, {"label": "Project", "text": "Thank you for helping get the project over the line. We appreciated the collaboration and pace."}, {"label": "Partner", "text": "Thank you for your support and reliability. It has made a real difference."}]},
                {"id": "proportion", "heading": "Proportion keeps it comfortable", "paragraphs": ["A thank-you can be small and still meaningful. If you find yourself using a high-value gift to make the thanks feel sincere, rewrite the message first."]},
            ],
            faqs=[{"q": "What should a thank-you wine gift message say?", "a": "Mention the specific help, referral or project, and keep the tone warm without sales pressure."}, {"q": "What wine gift works for a thank-you?", "a": "A sparkling bottle, bottle pair, compact hamper or mixed case can work depending on recipient and occasion."}],
            related=["thank-you-wine-gifts", "client-thank-you-wine-gifts", "client-wine-gifts"],
            cta="Plan a thank-you gift",
            cta_heading="Want the thank-you to feel more personal?",
            cta_text="Use the planner to match the gift route to the reason behind it.",
        ),
    }
)


GUIDES.update(
    {
        "corporate-wine-gifts-uk": enhanced_guide(
            title="Corporate Wine Gifts UK: Client Wine Gifts & Suppliers",
            h1="Corporate Wine Gifts UK",
            description="A practical UK guide to corporate wine gifts, including client gift ideas, budgets, bulk order considerations, packaging, supplier options and what to avoid.",
            intro="Corporate wine gifts can still work very well in the UK, but only when the gift fits the recipient, the occasion and the delivery reality. This is the main ClientCellar buying guide for choosing client wine gifts, bulk orders, hampers, Champagne, alcohol-free alternatives and supplier routes without drifting into generic catalogue gifting.",
            hero_bullets=[
                "Best for: client gifts, bulk orders, Christmas, event follow-ups and senior relationships",
                "Typical budget: £25-£150+, depending on value, policy and use case",
                "Avoid: one-size-fits-all bottles, weak packaging, vague notes and alcohol assumptions",
            ],
            opening_heading="Start with the job the gift has to do",
            opening=[
                "A good corporate wine gift is not just a bottle with a bow on it. It should be easy to accept, easy to enjoy and clearly connected to a real business moment: a thank-you, a project close, Christmas, a referral, a senior relationship or a team celebration.",
                "For an individual client, a polished bottle, pair or sparkling gift can work. For a team, a mixed case or wine hamper is usually more practical. For larger lists, the supplier's delivery process, address handling and gift-note workflow matter as much as the wine itself.",
                "If alcohol suitability is uncertain, do not make wine the only route. A premium food hamper, coffee, tea or alcohol-free sparkling option should feel equally considered.",
            ],
            best_fit_table={
                "headers": ["Gift type", "Best for", "Typical budget", "Watch-outs"],
                "rows": [
                    ["Still wine gift", "Individual thank-yous and known preferences", "£25-£75", "Taste risk if you choose one niche bottle."],
                    ["Champagne or sparkling wine", "Celebrations, senior contacts and milestones", "£45-£150", "Can feel obvious or too showy without a clear reason."],
                    ["Wine hamper", "Teams, Christmas and shareable gifts", "£50-£150+", "Check contents, allergens, substitutions and filler."],
                    ["Mixed case", "Client teams and wine-friendly recipients", "£75-£200+", "Delivery weight and address accuracy matter."],
                    ["Non-alcoholic alternative", "Unknown preferences, policy-sensitive gifts and mixed groups", "£25-£100", "Must feel like an equal-quality choice."],
                    ["Virtual tasting or event gift", "Remote teams, client entertainment and event follow-ups", "£25-£100 per head", "Packs, host quality and delivery timing make or break it."],
                ],
            },
            article_sections=[
                {
                    "id": "good-corporate-wine-gift",
                    "heading": "What makes a good corporate wine gift",
                    "paragraphs": [
                        "The best corporate wine gifts are proportionate, practical and specific. They suit the recipient, include a human note, arrive cleanly and do not create awkwardness around alcohol, value or policy.",
                        "Supplier reliability matters. Before choosing the prettiest product image, check delivery windows, gift messages, VAT invoices, substitutions, branded packaging options and whether the supplier can handle multiple addresses cleanly.",
                    ],
                    "bullets": [
                        "Choose by recipient and occasion before choosing by grape or region.",
                        "Use a short, specific note rather than generic appreciation wording.",
                        "Keep alcohol-free or food-led alternatives available where suitability is unclear.",
                        "Make the gift easy to justify if anyone asks why it was sent.",
                    ],
                },
                {
                    "id": "budget-ranges",
                    "heading": "Best corporate wine gifts by budget",
                    "paragraphs": [
                        "Budget should include delivery, VAT, packaging and any gift-message costs, not just the bottle. A modest gift with a clear reason often lands better than an expensive gift with no context.",
                    ],
                    "table": {
                        "headers": ["Budget", "Best use", "Good routes"],
                        "rows": [
                            ["Under £25", "Light-touch thank-you or large-list gesture", "Simple bottle, small food gift, alcohol-free drink."],
                            ["£25-£50", "Safe client gift range", "Sparkling wine, bottle pair, compact hamper or merchant pick."],
                            ["£50-£100", "Important contact or warmer relationship", "Better bottle, Champagne, curated pair, strong hamper."],
                            ["£100+", "Senior stakeholder, VIP or team gift", "Premium case, luxury hamper or carefully justified sparkling route."],
                        ],
                    },
                },
                {
                    "id": "use-cases",
                    "heading": "Best corporate wine gifts by use case",
                    "bullets": [
                        "Christmas: order early, confirm empty-office risk and avoid generic hampers.",
                        "Thank-you gifts: link the gift to the specific project, referral or support.",
                        "Senior client gifts: choose restraint, polish and a value that is easy to explain.",
                        "Bulk client gifts: prioritise data handling, substitutions, notes and delivery tracking.",
                        "Event follow-ups: make the gift connect clearly to the event or speaker moment.",
                        "Employee or team gifting: offer choice and alcohol-free alternatives from the start.",
                    ],
                },
                {
                    "id": "bulk-orders",
                    "heading": "Bulk corporate wine orders need operations, not hope",
                    "paragraphs": [
                        "Bulk gifting is where a nice idea becomes a logistics project. Ask suppliers about delivery timing, branded packaging, gift-note character limits, recipient data formats, failed deliveries, minimum order quantities and how they handle multiple delivery addresses.",
                        "For home delivery, handle address data carefully and collect only what the supplier needs. For office delivery, check whether people will actually be there when the gift arrives.",
                    ],
                    "editorial_note": "The spreadsheet is part of the gift. Messy names, missing postcodes and generic notes make even good wine feel careless.",
                },
                {
                    "id": "alternatives",
                    "heading": "Wine vs Champagne vs hampers vs non-alcoholic gifts",
                    "paragraphs": [
                        "Still wine is flexible and often good value. Champagne is clearer for celebration, but can feel automatic. Hampers are useful for teams and unknown tastes, provided the contents are strong. Non-alcoholic alternatives are the sensible route when alcohol is risky or preferences are unknown.",
                        "The strongest buying decision is often not the most expensive one. It is the one that creates the least friction for the recipient.",
                    ],
                },
                {
                    "id": "avoid",
                    "heading": "What to avoid when sending wine to clients",
                    "bullets": [
                        "Sending alcohol without checking whether it is appropriate.",
                        "Choosing one bottle for a whole team.",
                        "Using expensive packaging to disguise average contents.",
                        "Leaving address collection and delivery too late.",
                        "Writing a note that sounds like sales copy.",
                        "Ignoring policy, approval or gift-value limits.",
                    ],
                    "messages": [
                        {"label": "Avoid", "text": "Please accept this gift as a token of our appreciation."},
                        {"label": "Better", "text": "A small thank-you for your support on the project this year. We really enjoyed working with you and hope this is useful over the Christmas break."},
                    ],
                },
                {
                    "id": "how-clientcellar-helps",
                    "heading": "How ClientCellar helps shortlist options",
                    "paragraphs": [
                        "ClientCellar helps you turn the recipient, budget, occasion and risk level into a clearer gift brief before speaking to suppliers. Use the planner for the buying logic, then use the supplier directory to compare practical UK supplier routes.",
                    ],
                },
            ],
            faqs=[
                {"q": "What is a good corporate wine gift in the UK?", "a": "Good routes include still wine gifts, bottle pairs, Champagne or English sparkling wine, mixed cases, wine hampers and premium alcohol-free alternatives. The right choice depends on recipient suitability, budget, occasion and delivery needs."},
                {"q": "How much should I spend on a client wine gift?", "a": "Many client gifts sit between £25 and £100. Higher budgets can make sense for senior contacts or team gifts, but policy, timing and proportionality matter more than a universal number."},
                {"q": "Can businesses order wine gifts in bulk?", "a": "Yes. For bulk orders, check minimum quantities, recipient data requirements, multiple-address delivery, gift notes, substitutions, VAT invoices and delivery timing before committing."},
                {"q": "Is Champagne better than wine for corporate gifting?", "a": "Not always. Champagne is useful for celebrations, but still wine, English sparkling, hampers or alcohol-free gifts can be more appropriate depending on the recipient and context."},
                {"q": "Should I send one bottle or a case?", "a": "One bottle can work for an individual client. For a team, shared office or broader relationship, a mixed case or hamper usually feels less awkward."},
            ],
            related=["best-client-wine-gifts", "champagne-gifts-for-clients", "best-wine-gifts-under-50", "luxury-wine-hampers-uk"],
            cta="Build my wine gift brief",
            cta_heading="Need a corporate wine gift that feels properly chosen?",
            cta_text="Use the free gift planner to shape budget, recipient details, supplier questions and a more confident shortlist before ordering.",
        ),
        "champagne-gifts-for-clients": enhanced_guide(
            title="Champagne Gifts for Clients: When It Works & What to Send",
            h1="Champagne Gifts for Clients: When It Works, What to Send and What to Avoid",
            description="A practical UK guide to sending champagne as a client or corporate gift, including when it is appropriate, what to spend, and better alternatives when champagne feels too obvious.",
            intro="Champagne can be an appropriate corporate gift when the moment is genuinely celebratory, the relationship can carry the signal and alcohol is suitable for the recipient. It works well for milestones, senior thank-yous, Christmas gifts and congratulations. It is a poor choice when it looks too personal, too showy, too automatic or risky under the recipient's alcohol or gift policy.",
            hero_bullets=[
                "Best for: senior thank-yous, celebrations, congratulations and polished Christmas gifts",
                "Typical budget: £45-£150, depending on brand, packaging and relationship",
                "Avoid: sending Champagne as a shortcut when a safer wine, hamper or alcohol-free gift would fit better",
            ],
            opening_heading="Champagne works when the signal fits",
            opening=[
                "The question is not whether Champagne is a good gift. It often is. The better question is whether Champagne sends the right message for this client, at this moment, at this value.",
                "Use it when there is a clear reason to celebrate: a completed project, a major milestone, a promotion, a successful event or an end-of-year thank-you for a senior relationship. Avoid it when the recipient is unknown, the organisation has strict alcohol rules, the relationship is early, or the gift could look like status theatre.",
                "If you need a safe premium-feeling client gift, consider English sparkling wine, a well-chosen bottle pair, a mixed case, a refined hamper or a premium non-alcoholic gift with equal care.",
            ],
            best_fit_table={
                "headers": ["Situation", "Best champagne route", "Safer alternative"],
                "rows": [
                    ["Thank-you gift", "Recognisable Champagne or English sparkling with a specific note", "Bottle pair or compact hamper."],
                    ["Senior stakeholder gift", "Restrained premium Champagne in smart packaging", "Premium mixed case or luxury wine hamper."],
                    ["Team gift", "Champagne as part of a shareable hamper or case", "Mixed case, food-and-wine hamper or alcohol-free hamper."],
                    ["Christmas gift", "Champagne or sparkling gift ordered early", "Seasonal case, hamper or non-alcoholic sparkling."],
                    ["Celebration or congratulations", "Champagne when the milestone is clear", "English sparkling wine if a UK angle feels more thoughtful."],
                ],
            },
            article_sections=[
                {
                    "id": "good-client-gift",
                    "heading": "When champagne is a good client gift",
                    "paragraphs": [
                        "Champagne is strongest when celebration is the point. It is easy to understand, feels polished and gives the recipient a clear occasion to open it.",
                        "It works especially well when the note names the reason: a launch, completion, referral, promotion, award, anniversary or strong year of collaboration.",
                    ],
                },
                {
                    "id": "not-right",
                    "heading": "When champagne is not the right choice",
                    "paragraphs": [
                        "Champagne can feel too personal, too expensive or too obvious if the relationship is not warm enough. It can also be unsuitable where alcohol preferences, religion, recovery, health, pregnancy or company policy are unknown.",
                    ],
                    "bullets": [
                        "Do not send it before a sensitive commercial decision.",
                        "Do not use it to make a vague thank-you look more meaningful.",
                        "Do not send alcohol without checking appropriateness where you reasonably can.",
                        "Do not assume a team gift should revolve around one bottle.",
                    ],
                },
                {
                    "id": "spend",
                    "heading": "What to spend on client champagne gifts",
                    "paragraphs": [
                        "For most UK client champagne gifts, £45-£90 is a practical range for a polished bottle or sparkling gift. £90-£150 can work for senior relationships, but the reason and policy context need to be clear.",
                    ],
                    "table": {
                        "headers": ["Budget", "Best use", "Watch-out"],
                        "rows": [
                            ["Under £45", "English sparkling or non-Champagne sparkling", "Do not pretend it is luxury Champagne."],
                            ["£45-£75", "Good client thank-you or Christmas gift", "Packaging should be clean, not excessive."],
                            ["£75-£150", "Senior stakeholder or clear milestone", "Check value limits and avoid showiness."],
                            ["£150+", "Rarely needed for most client gifts", "Use carefully and record the reason."],
                        ],
                    },
                },
                {
                    "id": "sparkling-comparison",
                    "heading": "Champagne vs English sparkling wine vs still wine",
                    "paragraphs": [
                        "Champagne is the clearest celebration signal. English sparkling wine can feel more distinctive and UK-relevant. Still wine or a mixed case is often better when the gift is less about celebration and more about appreciation.",
                        "If taste is unknown, a bottle pair, hamper or mixed case spreads the risk better than one statement bottle.",
                    ],
                },
                {
                    "id": "avoid",
                    "heading": "What to avoid",
                    "bullets": [
                        "Looking too personal for the relationship.",
                        "Looking too cheap by choosing weak packaging or a bargain-led product.",
                        "Ignoring alcohol policy or gift acceptance rules.",
                        "Sending alcohol without checking whether it is appropriate.",
                        "Using weak packaging that makes the gift feel careless on arrival.",
                    ],
                },
                {
                    "id": "checklist",
                    "heading": "A short checklist before sending champagne",
                    "bullets": [
                        "Is there a clear reason for Champagne rather than another gift?",
                        "Is alcohol appropriate for this recipient or organisation?",
                        "Does the value fit your policy and the relationship?",
                        "Will the packaging and delivery protect the gift properly?",
                        "Does the note mention the specific milestone or thanks?",
                        "Do you have a good alcohol-free alternative if needed?",
                    ],
                },
            ],
            faqs=[
                {"q": "Is champagne an appropriate corporate gift?", "a": "Yes, when alcohol is suitable and the gift clearly fits a celebration, thank-you or senior relationship. It is less suitable when policy, timing or recipient preference is unclear."},
                {"q": "How much should you spend on champagne for a client?", "a": "A practical range is often £45-£90. Higher budgets can work for senior contacts or major milestones, but should be proportionate and easy to justify."},
                {"q": "Is English sparkling wine a good alternative to champagne?", "a": "Yes. English sparkling wine can feel thoughtful, current and UK-relevant, especially when Champagne feels too obvious."},
                {"q": "Should you send champagne to clients at Christmas?", "a": "It can work well for Christmas, but order early, check suitability and consider shareable hampers or alcohol-free alternatives for teams and mixed recipient groups."},
            ],
            related=["corporate-wine-gifts-uk", "how-much-to-spend-on-client-gifts", "non-alcoholic-client-gifts"],
            cta="Plan a sparkling client gift",
            cta_heading="Not sure Champagne is the right signal?",
            cta_text="Use the gift planner to compare Champagne, English sparkling, wine hampers and safer premium alternatives before choosing a supplier.",
        ),
        "how-much-to-spend-on-client-gifts": enhanced_guide(
            title="How Much to Spend on Client Gifts: UK Budget Guide",
            h1="How much to spend on client gifts without making it awkward",
            description="A practical guide to client gift budgets in the UK, including sensible spend ranges, when to go higher, and how to avoid gifts feeling either cheap or excessive.",
            intro="Client gift budgets should feel proportionate to the relationship, the moment and the recipient's policy environment. There is no magic number, but there are sensible ranges that help a gift feel considered rather than cheap, excessive or commercially awkward.",
            hero_bullets=["Best for: setting client gift tiers and approval rules", "Typical budget: £25-£100 for most client gifts", "Avoid: high-value gifts with no clear reason or approval trail"],
            opening_heading="The amount needs a reason",
            opening=[
                "A £30 gift can feel thoughtful when the note is specific. A £150 gift can feel uncomfortable if the timing is wrong or the relationship is not strong enough.",
                "Set the budget before browsing suppliers. Otherwise packaging, bundles and catalogue tiers will make the decision for you.",
            ],
            best_fit_table={
                "headers": ["Budget", "Best use", "Practical judgement"],
                "rows": [
                    ["Under £25", "Light-touch thank-you", "Keep it simple and do not dress it up as premium."],
                    ["£25-£50", "Safe client gift range", "Good for bottle pairs, compact hampers or polished small gifts."],
                    ["£50-£100", "Important contact or stronger relationship", "Strong range for corporate wine gifts and better hampers."],
                    ["£100+", "Senior stakeholder or VIP", "Use carefully, check policy and record the reason."],
                ],
            },
            article_sections=[
                {"id": "all-in-cost", "heading": "Budget all-in, not just the gift", "paragraphs": ["Include VAT, delivery, gift messages, packaging, substitutions and any multi-address handling. The real cost of client gifting is rarely just the listed product price."]},
                {"id": "when-to-go-higher", "heading": "When to go higher", "paragraphs": ["A higher budget can make sense for a senior relationship, a major milestone, a team gift or a long-running client. It should not be used to make a vague message feel more meaningful."]},
                {"id": "when-to-hold-back", "heading": "When to hold back", "paragraphs": ["If there is an active procurement process, renewal conversation or sensitive decision, choose a smaller route or wait. Good timing protects the gesture."]},
            ],
            faqs=[
                {"q": "What is a sensible client gift budget in the UK?", "a": "Many practical client gifts sit between £25 and £100, with higher budgets reserved for senior contacts, important milestones or team gifts where policy allows."},
                {"q": "Is £50 enough for a client gift?", "a": "Yes. £50 can be a strong budget for a polished wine gift, compact hamper or premium non-alcoholic option if the choice is focused."},
            ],
            related=["corporate-wine-gifts-uk", "champagne-gifts-for-clients", "client-gift-policy-checklist"],
            cta="Set a gift budget",
            cta_heading="Need a budget that feels proportionate?",
            cta_text="Use the planner to shape a sensible gift route by recipient, occasion and value.",
        ),
        "luxury-wine-hampers-uk": enhanced_guide(
            title="Luxury Wine Hampers UK: Uses, Budgets & Client Tips",
            h1="Luxury wine hampers in the UK, minus the filler",
            description="A practical UK guide to luxury wine hampers for clients, including when they work, what to include, what to spend and what to avoid.",
            intro="Luxury wine hampers can be excellent client gifts when they feel edited, useful and easy to share. They fail when the basket, ribbon and product photo are doing more work than the actual wine and food.",
            hero_bullets=["Best for: senior clients, client teams, Christmas and shareable premium gifts", "Typical budget: £75-£250+", "Avoid: large hampers with vague contents, weak wine or filler snacks"],
            opening_heading="Read the contents list like a buyer",
            opening=[
                "The photo is not the gift. The contents list is the gift. Look for wine quality, food quality, allergen clarity, substitution rules and whether the hamper feels carefully chosen rather than inflated.",
                "For clients, a smaller hamper with better contents usually feels more premium than a huge basket padded with things nobody would buy separately.",
            ],
            best_fit_table={"headers": ["Hamper route", "Best for", "Budget", "Watch"], "rows": [["Wine-led hamper", "Known wine-friendly client", "£75-£150", "Food may feel secondary."], ["Food-and-wine hamper", "Client teams or offices", "£60-£150", "Allergens and shareability."], ["Champagne hamper", "Celebration or Christmas", "£100-£250+", "Can feel showy."], ["Alcohol-free luxury hamper", "Mixed suitability", "£50-£150", "Must be equal quality."]]},
            article_sections=[
                {"id": "when-they-work", "heading": "When luxury wine hampers work", "paragraphs": ["They work when the gift may be shared, when taste is unknown, or when you want something more complete than one bottle. They are especially useful for Christmas, senior relationships and office-based teams."]},
                {"id": "what-to-include", "heading": "What a good hamper should include", "bullets": ["Wine with clear provenance or style.", "Food that makes sense with the wine.", "Clear allergen information.", "Packaging that protects the contents.", "A gift note that explains the reason for sending."]},
                {"id": "what-to-avoid", "heading": "What to avoid", "paragraphs": ["Avoid vague wine descriptions, too many tiny filler items, unclear substitutions and packaging that looks impressive but travels badly."], "editorial_note": "Do not buy the basket. Buy the gift."},
            ],
            faqs=[{"q": "Are luxury wine hampers good client gifts?", "a": "They can be, especially for teams, Christmas and premium relationships, provided the contents are genuinely strong and the value is proportionate."}, {"q": "How much should a luxury wine hamper cost?", "a": "Many useful client hampers sit around £75-£150, with £150+ better reserved for senior contacts, VIPs or team gifts where policy allows."}],
            related=["corporate-wine-gifts-uk", "best-wine-gifts-under-50", "wine-gift-hampers-uk"],
            cta="Plan a luxury hamper",
            cta_heading="Want a hamper that earns the word luxury?",
            cta_text="Use the planner to compare wine hamper, mixed case and alcohol-free premium routes.",
        ),
        "non-alcoholic-client-gifts": enhanced_guide(
            title="Non-Alcoholic Client Gifts: When Wine Is Not Right",
            h1="Non-alcoholic client gifts that do not feel like the backup option",
            description="Client gift ideas for situations where alcohol is not appropriate, including premium food gifts, coffee, tea, experiences and safer corporate gifting alternatives.",
            intro="Non-alcoholic client gifts are the sensible choice when wine is risky, unknown or simply not appropriate. The key is to make the alternative feel deliberate, premium and equal in care, not like the emergency substitute after someone raised a concern.",
            hero_bullets=["Best for: unknown preferences, strict policies, mixed teams and inclusive gifting", "Typical budget: £25-£100", "Avoid: weak alternatives that reveal wine was the only real plan"],
            opening_heading="When alcohol is risky, choose the safer premium route",
            opening=[
                "Clients may avoid alcohol for health, religion, recovery, pregnancy, personal preference or company policy. A good gifting process does not require them to explain why.",
                "Premium food gifts, coffee, tea, alcohol-free sparkling, craft soft drinks, choice-led gifts and some experiences can all work when they are chosen with the same care you would give to wine.",
            ],
            best_fit_table={"headers": ["Route", "Best for", "Watch"], "rows": [["Premium food hamper", "Broad client gifting and teams", "Allergens and dietary needs."], ["Coffee or tea gift", "Workplace-safe individual gifts", "Quality and presentation."], ["Alcohol-free sparkling", "Celebrations", "Do not choose tokenistic alternatives."], ["Experience or voucher", "Known recipient preference", "Choice and admin."], ["Choice-led gift", "Unknown preferences", "Supplier workflow and privacy."]]},
            article_sections=[
                {"id": "why-it-matters", "heading": "This is not just inclusivity theatre", "paragraphs": ["Alcohol-free options protect the recipient from awkward disclosure and protect the sender from making assumptions. They also widen the range of gifts that can be accepted under stricter policies."]},
                {"id": "premium-options", "heading": "Better non-alcoholic client gift ideas", "bullets": ["Specialist coffee or tea with strong packaging.", "Premium food hampers with clear allergens.", "Alcohol-free sparkling for celebration moments.", "Local produce boxes or bakery-led gifts.", "Choice-led gifts where the recipient can select a suitable route."]},
                {"id": "avoid", "heading": "What to avoid", "paragraphs": ["Do not pair a polished wine option with a visibly weaker alternative. If the budget is £75 for wine, the alcohol-free route should feel like a £75 gift too."]},
            ],
            faqs=[{"q": "What can I send instead of wine to a client?", "a": "Premium food hampers, coffee, tea, alcohol-free sparkling, craft soft drinks, local produce and choice-led gifts can all work."}, {"q": "When should I choose a non-alcoholic client gift?", "a": "Choose it when alcohol suitability is unknown, policy is strict, the gift is for a mixed group, or you want the safest professional route."}],
            related=["corporate-wine-gifts-uk", "champagne-gifts-for-clients", "business-gift-wine-etiquette"],
            cta="Plan an alcohol-free route",
            cta_heading="Need a safer client gift?",
            cta_text="Use the planner to compare premium alcohol-free, hamper and wine routes without making assumptions.",
        ),
        "best-wine-gifts-under-50": enhanced_guide(
            title="Best Wine Gifts Under £50: Premium Client Ideas",
            h1="Best Wine Gifts Under £50 That Still Feel Premium",
            description="Wine gift ideas under £50 for clients, colleagues and business contacts, with practical tips on packaging, delivery and when to choose something else.",
            intro="£50 is enough for a client-friendly wine gift if you spend it on the thing that matters. It is not enough to fake luxury, so keep the route focused: a good bottle, a clean pair, sparkling wine or a compact hamper with genuinely useful contents.",
            hero_bullets=["Best for: smaller client thank-yous, colleagues and polished low-risk gifts", "Typical budget: £30-£50", "Avoid: fake luxury packaging, novelty extras and weak wine in heavy boxes"],
            opening_heading="Simple and well chosen beats loud and padded",
            opening=[
                "Under £50, the best gift usually has one clear idea. A sparkling bottle says celebration. A red-and-white pair gives choice. A compact wine-and-food gift can feel complete if the contents are strong.",
                "If alcohol suitability is uncertain, choose a premium food, coffee, tea or alcohol-free sparkling route instead of forcing the wine gift.",
            ],
            best_fit_table={"headers": ["Gift idea", "Best for", "Watch"], "rows": [["English sparkling", "Celebrations and Christmas", "Presentation matters."], ["Two-bottle pair", "Unknown taste", "Keep both bottles broadly useful."], ["Good single bottle", "Known recipient preference", "Taste risk."], ["Compact hamper", "Slightly warmer gifts", "Avoid filler."], ["Merchant pick", "Less generic client gift", "Check delivery and gift notes."]]},
            article_sections=[
                {"id": "packaging", "heading": "Packaging should support the gift, not hide it", "paragraphs": ["Clean packaging, safe delivery and a proper note matter. Heavy boxes and novelty accessories can make an under-£50 gift look like it is pretending to be something else."]},
                {"id": "client-use", "heading": "When under £50 works for clients", "paragraphs": ["This budget is strongest for modest thank-yous, early relationships, colleagues, hosts and smaller festive gestures. For senior stakeholders, it may still work if the note is specific and the gift is restrained."]},
                {"id": "choose-something-else", "heading": "When to choose something else", "paragraphs": ["If you do not know whether alcohol is appropriate, or if the recipient is a wider team, a compact hamper or premium non-alcoholic gift may be safer than one bottle."]},
            ],
            faqs=[{"q": "Is £50 enough for a good wine gift?", "a": "Yes. It can buy a good bottle, sparkling wine, a bottle pair or a compact hamper if you avoid fake luxury packaging."}, {"q": "What wine gift under £50 is safest for clients?", "a": "A sparkling wine, bottle pair or compact wine-and-food gift is usually safer than a niche bottle chosen around your own taste."}],
            related=["corporate-wine-gifts-uk", "how-much-to-spend-on-client-gifts", "non-alcoholic-client-gifts"],
            cta="Find a wine gift under £50",
            cta_heading="Need a polished gift within budget?",
            cta_text="Use the planner to compare under-£50 wine, hamper and alcohol-free routes.",
        ),
        "virtual-wine-tasting-for-teams": enhanced_guide(
            title="Virtual Wine Tasting for Teams: UK Event Guide",
            h1="Virtual wine tasting for teams without the awkward video-call energy",
            description="A practical guide to virtual wine tasting for teams and clients, including when it works, how to choose a supplier and what to check before booking.",
            intro="Virtual wine tastings work when the host, packs and format give people a reason to be there. They fail when the event is treated as another video call with bottles attached.",
            hero_bullets=["Best for: remote teams, hybrid socials, client entertainment and light team-building", "Typical budget: £25-£75 per head", "Avoid: compulsory drinking, late address collection and weak alcohol-free options"],
            opening_heading="The pack is only half the event",
            opening=["A good supplier handles delivery, host quality, instructions, alcohol-free options and contingency plans. A good organiser sets expectations early so nobody is surprised by address collection, timings or the amount of wine involved."],
            best_fit_table={"headers": ["Format", "Best for", "Watch"], "rows": [["Hosted tasting", "Mixed confidence teams", "Host quality matters."], ["Blind tasting", "Lighter team energy", "Needs clear instructions."], ["Food pairing", "Premium client or team event", "Delivery complexity."], ["Alcohol-free tasting", "Inclusive teams", "Needs equal quality."], ["Client tasting", "Relationship-building", "Keep tone polished."]]},
            article_sections=[
                {"id": "supplier", "heading": "How to choose a virtual tasting supplier", "bullets": ["Ask who hosts the session and how experienced they are.", "Confirm pack contents, delivery coverage and missed-delivery process.", "Check alcohol-free packs are available from the start.", "Ask whether the tone suits clients, staff or both.", "Confirm cancellation terms and minimum numbers."]},
                {"id": "delivery", "heading": "Delivery is the event risk", "paragraphs": ["Collect addresses early, explain privacy handling and leave time for replacements. Remote tastings fail quietly when packs arrive late or unevenly."]},
                {"id": "invite", "heading": "Set expectations in the invite", "paragraphs": ["Tell people what is arriving, how long the tasting lasts, whether food is needed and that drinking is optional. Clarity makes the event feel more relaxed before it starts."]},
            ],
            faqs=[{"q": "Can virtual wine tastings work for remote teams?", "a": "Yes, if packs arrive on time, the host is engaging, the format is clear and alcohol-free options are available."}, {"q": "How much does a virtual wine tasting cost?", "a": "Many UK corporate formats sit around £25-£75 per head, but suppliers should confirm current pricing and inclusions."}],
            related=["corporate-wine-gifts-uk", "corporate-event-wine-planning", "wine-tasting-team-building"],
            cta="Plan a virtual tasting",
            cta_heading="Planning a remote team tasting?",
            cta_text="Use the event planner to shape the format, supplier questions, delivery timing and guest experience.",
            cta_url="/event-planner",
        ),
        "client-thank-you-wine-gifts": enhanced_guide(
            title="Thank-You Wine Gifts for Clients: What to Send and When",
            h1="Thank-you wine gifts for clients that sound like actual thanks",
            description="A practical guide to thank-you wine gifts for clients and business contacts, including budget, timing, message wording and safer alternatives.",
            intro="A thank-you wine gift should feel connected to the thing you are thanking the client for. Without that connection, even a polished bottle can feel like a standard dispatch.",
            hero_bullets=["Best for: project completions, referrals, partner help and post-event appreciation", "Typical budget: £25-£100", "Avoid: vague notes, sensitive timing and excessive gestures"],
            opening_heading="Say what the thanks is for",
            opening=[
                "Was it a referral, a project delivered under pressure, a useful introduction or a long-running relationship? Put that in the note before worrying about the bottle.",
                "If the recipient is a group, make the gift shareable. If alcohol is uncertain, choose a food or alcohol-free route with the same care.",
            ],
            best_fit_table={"headers": ["Thank-you moment", "Better route", "Tone"], "rows": [["Referral", "Smart bottle or compact hamper", "Grateful and proportionate"], ["Project completion", "Sparkling wine or bottle pair", "Specific and warm"], ["Senior support", "Restrained premium bottle or hamper", "Polished"], ["Client team", "Mixed case or shareable hamper", "Inclusive"], ["Event follow-up", "Modest bottle or alcohol-free gift", "Connected to the event"]]},
            article_sections=[
                {"id": "budget", "heading": "Budget and timing", "paragraphs": ["Many thank-you gifts sit comfortably between £25 and £100. Go higher only when the relationship, policy and reason justify it. Avoid sending gifts during live decisions or procurement moments."]},
                {"id": "messages", "heading": "Message wording that feels human", "messages": [{"label": "Referral", "text": "A small thank-you for the introduction. We really appreciate you thinking of us."}, {"label": "Project", "text": "Thank you for helping get the project over the line. We appreciated the collaboration and pace."}, {"label": "Partner", "text": "Thank you for your support and reliability. It has made a real difference."}]},
                {"id": "alternatives", "heading": "Safer alternatives", "paragraphs": ["When wine is not suitable, send a premium food hamper, coffee, tea, alcohol-free sparkling or choice-led gift. The alternative should feel as considered as the wine route."]},
            ],
            faqs=[{"q": "What should a thank-you wine gift message say?", "a": "Mention the specific help, referral, project or relationship, and keep the wording warm without sales pressure."}, {"q": "What wine gift works for a client thank-you?", "a": "Sparkling wine, a bottle pair, compact hamper or mixed case can all work depending on recipient, budget and occasion."}],
            related=["corporate-wine-gifts-uk", "champagne-gifts-for-clients", "how-much-to-spend-on-client-gifts"],
            cta="Plan a thank-you gift",
            cta_heading="Want the thank-you to feel specific?",
            cta_text="Use the planner to match the gift route to the reason, recipient and budget.",
        ),
        "wine-gifts-for-thank-you": enhanced_guide(
            title="Wine Gifts for Thank-You Moments: Client Gift Guide",
            h1="Thank-you wine gifts for clients that sound like actual thanks",
            description="A short supporting guide for thank-you wine gift moments, aligned to the main client thank-you wine gifts page.",
            intro="A thank-you wine gift should feel connected to the thing you are thanking the client for.",
            hero_bullets=["Best for: project completions, referrals and partner appreciation", "Typical budget: £25-£100", "Avoid: vague notes and excessive gestures"],
            opening_heading="Use the canonical thank-you guide",
            opening=["This guide is kept aligned with the canonical ClientCellar thank-you wine gifts page."],
            best_fit_table={"headers": ["Thank-you", "Better route", "Tone"], "rows": [["Referral", "Smart bottle or hamper", "Grateful"], ["Project", "Sparkling or pair", "Specific"], ["Team", "Mixed case or hamper", "Shareable"]]},
            article_sections=[],
            faqs=[],
            related=["corporate-wine-gifts-uk", "champagne-gifts-for-clients", "how-much-to-spend-on-client-gifts"],
            cta="Plan a thank-you gift",
            cta_heading="Want the thank-you to feel specific?",
            cta_text="Use the planner to match the gift route to the reason, recipient and budget.",
        ),
    }
)

GUIDES["corporate-wine-gifts-uk"]["internal_links"] = [
    {"label": "Use the gift planner", "href": "/gift-planner", "text": "turn budget, recipient and occasion into a practical brief."},
    {"label": "Use the event planner", "href": "/event-planner", "text": "plan tastings, follow-up gifts or event wine."},
    {"label": "Champagne gifts for clients", "href": "/guides/champagne-gifts-for-clients", "text": "compare Champagne with English sparkling and safer alternatives."},
    {"label": "Best wine gifts under £50", "href": "/guides/best-wine-gifts-under-50", "text": "keep smaller gifts polished without fake luxury."},
    {"label": "Luxury wine hampers UK", "href": "/guides/luxury-wine-hampers-uk", "text": "check when hampers are the stronger route."},
    {"label": "Non-alcoholic client gifts", "href": "/guides/non-alcoholic-client-gifts", "text": "use when wine is not suitable."},
    {"label": "Client gift budget guide", "href": "/guides/how-much-to-spend-on-client-gifts", "text": "set sensible spend tiers."},
    {"label": "UK supplier directory", "href": "/supplier-directory", "text": "compare practical supplier routes."},
]

GUIDES["champagne-gifts-for-clients"]["internal_links"] = [
    {"label": "Corporate wine gifts", "href": "/guides/corporate-wine-gifts-uk", "text": "the main buying guide for client wine gifts, budgets and supplier routes."},
    {"label": "Client gift budget guide", "href": "/guides/how-much-to-spend-on-client-gifts", "text": "sense-check spend before choosing Champagne."},
    {"label": "Non-alcoholic client gifts", "href": "/guides/non-alcoholic-client-gifts", "text": "use when alcohol may not be appropriate."},
    {"label": "Gift planner", "href": "/gift-planner", "text": "compare sparkling, hamper and alcohol-free routes."},
    {"label": "Supplier directory", "href": "/supplier-directory", "text": "find UK wine gift suppliers."},
]

for guide_slug, link_items in {
    "how-much-to-spend-on-client-gifts": [
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "connect budget tiers to wine gift routes."),
        ("Champagne gifts for clients", "/guides/champagne-gifts-for-clients", "sense-check sparkling gift spend."),
        ("Gift planner", "/gift-planner", "turn a budget into a practical brief."),
    ],
    "luxury-wine-hampers-uk": [
        ("UK corporate wine gifting", "/guides/corporate-wine-gifts-uk", "compare hampers with bottles, cases and sparkling gifts."),
        ("Best wine gifts under £50", "/guides/best-wine-gifts-under-50", "see when a smaller gift is enough."),
        ("Gift planner", "/gift-planner", "shape a hamper brief."),
        ("Supplier directory", "/supplier-directory", "compare UK supplier routes."),
    ],
    "non-alcoholic-client-gifts": [
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "compare alcohol and alcohol-free gifting routes."),
        ("Champagne gifts for clients", "/guides/champagne-gifts-for-clients", "check when sparkling is not the right answer."),
        ("Gift planner", "/gift-planner", "build an inclusive client gift plan."),
    ],
    "best-wine-gifts-under-50": [
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "place under-£50 gifts in the wider buying guide."),
        ("Client gift budget guide", "/guides/how-much-to-spend-on-client-gifts", "set sensible spend ranges."),
        ("Gift planner", "/gift-planner", "shortlist gifts within budget."),
    ],
    "virtual-wine-tasting-for-teams": [
        ("Event planner", "/event-planner", "turn the tasting idea into a supplier-ready brief."),
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "compare event packs with client wine gifts."),
        ("Supplier directory", "/supplier-directory", "find UK event and gifting suppliers."),
    ],
    "client-thank-you-wine-gifts": [
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "use the main wine gifting hub for supplier and budget decisions."),
        ("Champagne gifts for clients", "/guides/champagne-gifts-for-clients", "decide when sparkling is the right thank-you signal."),
        ("Gift planner", "/gift-planner", "match the gift route to the reason for thanks."),
    ],
    "wine-gifts-for-thank-you": [
        ("Corporate wine gifts", "/guides/corporate-wine-gifts-uk", "use the main wine gifting hub for supplier and budget decisions."),
        ("Champagne gifts for clients", "/guides/champagne-gifts-for-clients", "decide when sparkling is the right thank-you signal."),
        ("Gift planner", "/gift-planner", "match the gift route to the reason for thanks."),
    ],
}.items():
    if guide_slug in GUIDES:
        GUIDES[guide_slug]["internal_links"] = [
            {"label": label, "href": href, "text": text} for label, href, text in link_items
        ]


GUIDE_IMAGE_ASSETS = {
    "corporate": {
        "image": "/images/clientcellar/guide-corporate-wine-gifts.webp",
        "imageAlt": "Wine bottle and gift box for corporate gifting",
        "image_width": 1200,
        "image_height": 900,
    },
    "budget": {
        "image": "/images/clientcellar/guide-wine-gifts-under-50.webp",
        "imageAlt": "Wine gift setup for budget-friendly client gifting",
        "image_width": 1200,
        "image_height": 900,
    },
    "christmas": {
        "image": "/images/clientcellar/guide-client-christmas-gifts.webp",
        "imageAlt": "Festive wine gift hamper for client Christmas gifts",
        "image_width": 1200,
        "image_height": 900,
    },
    "event": {
        "image": "/images/clientcellar/guide-event-wine-planning.webp",
        "imageAlt": "Wine glasses on a table for event drinks planning",
        "image_width": 1200,
        "image_height": 900,
    },
    "merchant": {
        "image": "/images/clientcellar/guide-choosing-wine-merchant.webp",
        "imageAlt": "Wine merchant shelves for choosing a supplier",
        "image_width": 1200,
        "image_height": 900,
    },
    "champagne": {
        "image": "/images/clientcellar/guide-champagne-gifts.webp",
        "imageAlt": "Champagne bottle in an ice bucket for client gifting",
        "image_width": 1200,
        "image_height": 900,
    },
}


GUIDE_IMAGE_SLUGS = {
    "corporate-wine-gifts-uk": "corporate",
    "client-wine-gifts": "corporate",
    "best-client-wine-gifts": "corporate",
    "corporate-gift-ideas-for-clients": "corporate",
    "wine-gifts-for-customers": "corporate",
    "thank-you-wine-gifts": "corporate",
    "best-wine-gifts-under-25": "budget",
    "best-wine-gifts-under-50": "budget",
    "best-wine-gifts-under-100": "budget",
    "corporate-wine-gifts-under-50": "budget",
    "corporate-wine-gifts-under-100": "budget",
    "christmas-corporate-wine-gifts": "christmas",
    "christmas-wine-gifts-for-clients": "christmas",
    "wine-gifts-for-christmas": "christmas",
    "corporate-event-wine-planning": "event",
    "wine-tasting-corporate-event": "event",
    "virtual-wine-tasting-for-teams": "event",
    "corporate-wine-tasting-london": "event",
    "wine-tasting-team-building": "event",
    "wine-gifts-for-events": "event",
    "corporate-gifting-recipient-csv-template": "merchant",
    "client-gift-policy-checklist": "merchant",
    "business-gift-wine-etiquette": "merchant",
    "client-gifting-etiquette-uk": "merchant",
    "champagne-gifts-for-clients": "champagne",
    "corporate-champagne-gifts": "champagne",
    "english-sparkling-corporate-gifts": "champagne",
}

GUIDE_CARD_IMAGE_SLUGS = {
    "corporate-wine-gifts-uk",
    "best-wine-gifts-under-50",
    "christmas-corporate-wine-gifts",
    "corporate-event-wine-planning",
    "champagne-gifts-for-clients",
    "corporate-gifting-recipient-csv-template",
}


GUIDE_IMAGE_ALT_OVERRIDES = {
    "corporate-wine-gifts": "Wine bottle and gift box for corporate gifting",
    "corporate-wine-gifts-uk": "Wine bottle and gift box for corporate gifting",
    "corporate-wine-gifts-uk-seo": "Wine bottle and gift box for corporate gifting",
    "client-wine-gifts": "Wine gift with thank-you card for a client",
    "client-wine-gifts-seo": "Wine gift with thank-you card for a client",
    "best-client-wine-gifts": "Wine gift shortlist for client gifting",
    "best-wine-gifts-for-clients": "Wine gift shortlist for client gifting",
    "wine-gift-hampers-uk": "Wine hamper with food and gift packaging",
    "corporate-hampers-uk": "Wine hamper with food and gift packaging",
    "corporate-wine-hampers": "Wine hamper with food and gift packaging",
    "luxury-wine-hampers-uk": "Premium wine hamper with food and gift packaging",
    "food-and-wine-hampers": "Food and wine hamper with gift packaging",
    "corporate-event-wine-planning": "Wine glasses on a table for event drinks planning",
    "event-wine-planning-uk": "Wine glasses on a table for event drinks planning",
    "wine-for-corporate-events": "Wine glasses on a table for corporate event drinks",
    "corporate-wine-tasting-events": "Wine glasses and tasting notes for a corporate event",
    "wine-tasting-corporate-event": "Wine glasses and tasting notes for a corporate event",
    "virtual-wine-tasting-for-teams": "Virtual wine tasting packs beside a laptop",
    "corporate-wine-tasting-london": "Wine tasting table for a corporate event in London",
    "wine-tasting-team-building": "Wine tasting glasses for a team-building event",
    "client-christmas-gifts-uk": "Festive wine gift hamper for client Christmas gifts",
    "christmas-corporate-wine-gifts": "Festive wine gift hamper for client Christmas gifts",
    "corporate-christmas-wine-gifts": "Festive wine gift hamper for client Christmas gifts",
    "christmas-wine-gifts-for-clients": "Festive wine gift hamper for client Christmas gifts",
    "wine-gifts-for-christmas": "Festive wine gift hamper for Christmas gifting",
    "best-wine-gifts-under-25": "Simple wine gift setup for budget-friendly client gifting",
    "best-wine-gifts-under-50": "Simple wine gift setup for budget-friendly client gifting",
    "best-wine-gifts-under-100": "Wine gift setup for a higher client gift budget",
    "corporate-wine-gifts-under-50": "Simple wine gift setup for budget-friendly client gifting",
    "corporate-wine-gifts-under-100": "Wine gift setup for a higher corporate gift budget",
    "champagne-gifts-for-clients": "Champagne bottle in an ice bucket for client gifting",
    "corporate-champagne-gifts": "Champagne bottle in an ice bucket for client gifting",
    "english-sparkling-corporate-gifts": "English sparkling wine bottle for corporate gifting",
    "business-gift-wine-etiquette": "Wine gift beside checklist and pen",
    "client-gift-policy-checklist": "Wine gift beside checklist and pen",
    "client-gifting-etiquette-uk": "Wine gift beside checklist and pen",
    "corporate-gifting-recipient-csv-template": "Recipient spreadsheet and gift delivery labels",
    "thank-you-gifts-for-clients": "Wine gift with thank-you card for a client",
    "thank-you-wine-gifts": "Wine gift with thank-you card",
    "client-thank-you-wine-gifts": "Wine gift with thank-you card for a client",
    "wine-gifts-for-thank-you": "Wine gift with thank-you card",
    "staff-wine-gifts": "Staff wine gift options with alcohol-free alternatives",
    "staff-wine-gifts-uk": "Staff wine gift options with alcohol-free alternatives",
    "non-alcoholic-client-gifts": "Alcohol-free client gift options with premium packaging",
    "personalised-wine-gifts": "Personalised wine gift with subtle branded card",
    "best-wine-accessories-for-gifts": "Wine accessories arranged as a client gift",
    "wine-gift-baskets-uk": "Wine gift basket with food and gift packaging",
    "premium-client-gifts-uk": "Premium wine gift with approval notes for a client",
}


def guide_image_alt_for(slug: str, guide: dict | None = None) -> str:
    if slug in GUIDE_IMAGE_ALT_OVERRIDES:
        return GUIDE_IMAGE_ALT_OVERRIDES[slug]
    topic = (guide or {}).get("h1") or (guide or {}).get("title") or slug.replace("-", " ")
    topic_lower = topic.lower()
    if "event" in topic_lower or "tasting" in topic_lower:
        return "Wine glasses on a table for event drinks planning"
    if "hamper" in topic_lower or "basket" in topic_lower:
        return "Wine hamper with food and gift packaging"
    if "christmas" in topic_lower:
        return "Festive wine gift hamper for client Christmas gifts"
    if "champagne" in topic_lower or "sparkling" in topic_lower:
        return "Champagne bottle in an ice bucket for client gifting"
    if "policy" in topic_lower or "etiquette" in topic_lower or "checklist" in topic_lower:
        return "Wine gift beside checklist and pen"
    if "budget" in topic_lower or "under" in topic_lower:
        return "Simple wine gift setup for budget-friendly client gifting"
    if "client" in topic_lower or "thank" in topic_lower:
        return "Wine gift with thank-you card for a client"
    return "Wine bottle and gift box for corporate gifting"


def clean_guide_image_asset_for(slug: str, guide: dict | None = None) -> dict | None:
    # Website guide images live in public/images/clientcellar/guides/*.webp.
    # Keep these clean, no-text assets separate from social/Pinterest graphics.
    # Current guide images are suitable as thumbnails. Full hero images should
    # use true high-resolution per-guide assets before being displayed large.
    image_path = GUIDE_IMAGE_DIR / f"{slug}.webp"
    if not image_path.exists():
        return None
    return {
        "image": f"{GUIDE_IMAGE_URL_PREFIX}/{slug}.webp",
        "imageAlt": guide_image_alt_for(slug, guide),
        "image_width": 1200,
        "image_height": 900,
    }


def guide_image_asset_for(slug: str, guide: dict) -> dict | None:
    clean_asset = clean_guide_image_asset_for(slug, guide)
    if clean_asset:
        return clean_asset
    if slug in GUIDE_IMAGE_SLUGS:
        return GUIDE_IMAGE_ASSETS[GUIDE_IMAGE_SLUGS[slug]]
    haystack = " ".join(
        [
            slug,
            guide.get("title", ""),
            guide.get("h1", ""),
            guide.get("description", ""),
        ]
    ).lower()
    if any(term in haystack for term in ["event", "tasting", "venue"]):
        return GUIDE_IMAGE_ASSETS["event"]
    if any(term in haystack for term in ["under-25", "under £25", "under-50", "under £50", "under-100", "under £100", "budget"]):
        return GUIDE_IMAGE_ASSETS["budget"]
    if any(term in haystack for term in ["champagne", "sparkling", "celebration"]):
        return GUIDE_IMAGE_ASSETS["champagne"]
    if any(term in haystack for term in ["christmas", "seasonal", "festive"]):
        return GUIDE_IMAGE_ASSETS["christmas"]
    if any(term in haystack for term in ["supplier", "merchant", "where to buy", "csv", "bulk"]):
        return GUIDE_IMAGE_ASSETS["merchant"]
    if any(term in haystack for term in ["corporate wine", "corporate gift", "corporate gifting", "client wine"]):
        return GUIDE_IMAGE_ASSETS["corporate"]
    return None


for guide_slug, guide_data in GUIDES.items():
    guide_image_asset = guide_image_asset_for(guide_slug, guide_data)
    if guide_image_asset:
        guide_data.update(guide_image_asset)
        guide_data["show_card_image"] = (
            guide_data["image"].startswith(GUIDE_IMAGE_URL_PREFIX)
            or guide_slug in GUIDE_CARD_IMAGE_SLUGS
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
        "related": [("Supplier directory", "/supplier-directory"), ("Client wine gifts", "/client-wine-gifts"), ("Staff wine gifts", "/staff-wine-gifts")],
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
        "related": [("Supplier directory", "/supplier-directory"), ("Corporate wine gifts", "/corporate-wine-gifts"), ("Virtual tasting guide", "/guides/virtual-wine-tasting-for-teams")],
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
        "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Corporate Christmas wine gifts", "/corporate-christmas-wine-gifts"), ("Supplier directory", "/supplier-directory")],
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
        "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Corporate wine tasting events", "/corporate-wine-tasting-events"), ("Supplier directory", "/supplier-directory")],
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
        "related": [("Client wine gifts", "/client-wine-gifts"), ("Staff wine gifts", "/staff-wine-gifts"), ("Supplier directory", "/supplier-directory")],
    },
}


def seo_supplier(name: str, supplier_id: str, best_for: str, note: str, label: str = "View supplier") -> dict:
    return {
        "name": name,
        "url": configured_supplier_url(supplier_id),
        "best_for": best_for,
        "note": note,
        "label": label,
    }


WINE_GIFT_SUPPLIER_ROUTES = [
    seo_supplier("Majestic Corporate Gifts", "majestic", "Corporate wine gifting, repeat orders and practical business buying.", "Useful first route for client lists, staff rewards and business wine gifts.", "View corporate gifts"),
    seo_supplier("Laithwaites Corporate Wine Gifts", "laithwaites", "Established corporate wine gifts and premium presentation.", "Useful comparison route for wine-only gifting and bulk gift conversations.", "View corporate wine gifts"),
    seo_supplier("Virgin Wines Corporate", "virgin-wines", "Approachable corporate gifts, staff rewards and mixed-case options.", "Useful where the gift should feel accessible rather than formal.", "View corporate gifts"),
]

HAMPER_SUPPLIER_ROUTES = [
    seo_supplier("M&S Food & Drink Gifts", "marks-spencer-corporate", "Mainstream hampers for mixed recipient preferences.", "Useful fallback when wine tastes are unknown or food-and-drink variety is safer.", "View hampers"),
    seo_supplier("Fortnum & Mason", "fortnum-mason", "Premium hampers and presentation-led client gifts.", "Useful for senior clients, formal gifting and stronger perceived value.", "View hampers"),
    seo_supplier("John Lewis Hampers", "john-lewis-hampers", "Broad food and drink gifting.", "Useful for mainstream hamper comparison and non-specialist buyers.", "View hampers"),
]

EVENT_SUPPLIER_ROUTES = [
    seo_supplier("Majestic Commercial", "majestic-commercial", "Larger events, office celebrations and business orders.", "Useful when quantity planning, delivery coordination and substitutions need discussing.", "View event support"),
    seo_supplier("Waitrose Cellar Gifts", "waitrose-cellar", "Recognised UK retail wine gifts and mainstream premium options.", "Useful benchmark if the event is simple and self-managed.", "View wine gifts"),
    seo_supplier("Virgin Wines Corporate", "virgin-wines", "Corporate gifts, staff rewards and mixed-case options.", "Useful for approachable event-adjacent wine gifting or post-event packs.", "View corporate gifts"),
]


HIGH_INTENT_SEO_PAGES = {
    "corporate-wine-gifts-uk": {
        "title": "Corporate Wine Gifts UK",
        "h1": "Corporate wine gifts UK",
        "description": "Plan corporate wine gifts in the UK with budget guidance, supplier routes, buyer checks and a free ClientCellar planning tool.",
        "intro": "UK corporate wine gifts work best when the brief is clear: who receives the gift, what budget feels appropriate, whether alcohol is suitable and which supplier route can handle delivery and admin.",
        "sections": [
            ("Recommended approach", ["Use a corporate wine gifting supplier for standard client lists.", "Keep a hamper or alcohol-free alternative available for mixed preferences.", "Reserve premium retailers or local merchants for senior or VIP relationships."]),
            ("What to decide before contacting suppliers", ["Recipient count and address quality.", "Budget per recipient before delivery and VAT.", "Gift message, branding and alcohol-free requirements.", "Required delivery window and approval deadline."]),
            ("Risks to avoid", ["Do not assume live stock or delivery slots.", "Avoid wine-only gifts where alcohol suitability is unclear.", "Get substitutions, VAT and delivery costs in writing before payment."]),
        ],
        "supplier_routes": WINE_GIFT_SUPPLIER_ROUTES,
        "faqs": [
            {"q": "What is a sensible budget for UK corporate wine gifts?", "a": "Many business buyers start with a planning band such as £30-£75 per recipient, then confirm current supplier pricing, VAT and delivery directly."},
            {"q": "Can ClientCellar supply the wine?", "a": "No. ClientCellar provides planning guidance and supplier-route recommendations. You order directly from suppliers."},
            {"q": "Should every client receive the same gift?", "a": "Not always. A simple VIP, standard and internal stakeholder tiering approach often works better."},
            {"q": "What should I ask suppliers?", "a": "Ask about stock, substitutions, gift messages, VAT invoices, delivery locations, tracking and corporate order support."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing"), ("Premium example", "/example-premium-brief-pack")],
    },
    "client-christmas-gifts-uk": {
        "title": "Client Christmas Gifts UK",
        "h1": "Client Christmas gifts UK",
        "description": "Plan UK client Christmas gifts with practical budget, supplier and delivery guidance for corporate wine gifts and hampers.",
        "intro": "Client Christmas gifting needs early supplier contact, clean recipient data and sensible alternatives. The best route is usually one mainstream supplier for standard recipients plus a premium or advice-led route for VIP clients.",
        "sections": [
            ("Christmas planning priorities", ["Start supplier conversations well before December.", "Confirm final recipient count and addresses early.", "Ask for order cut-off dates, substitutions and failed-delivery handling."]),
            ("Gift routes to compare", ["Corporate wine gifts for wine-friendly clients.", "Food and drink hampers for mixed tastes.", "Premium hampers or wine merchants for senior relationships."]),
            ("Operational checks", ["Gift message support.", "VAT invoice availability.", "Alcohol-free and dietary alternatives.", "Multi-address delivery method."]),
        ],
        "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES[:2], *HAMPER_SUPPLIER_ROUTES[:2]],
        "faqs": [
            {"q": "When should UK businesses order client Christmas gifts?", "a": "Start planning well before December, especially for larger lists, branded notes or multi-address delivery."},
            {"q": "Are wine gifts appropriate for Christmas clients?", "a": "They can be, but check client policies and keep alcohol-free or hamper alternatives available."},
            {"q": "Do suppliers guarantee Christmas delivery?", "a": "ClientCellar does not guarantee delivery. Confirm cut-off dates and delivery windows directly with each supplier."},
            {"q": "Should I use hampers instead of wine?", "a": "Hampers can be safer for mixed preferences or when individual wine tastes are unknown."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Corporate wine gifts UK", "/corporate-wine-gifts-uk"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
    },
    "corporate-hampers-uk": {
        "title": "Corporate Hampers UK",
        "h1": "Corporate hampers UK",
        "description": "Compare corporate hamper routes for UK business gifting, including supplier checks, delivery questions and planning guidance.",
        "intro": "Corporate hampers are useful when recipient tastes are mixed or a single bottle feels too narrow. The key is checking contents, allergens, alcohol-free options and delivery before ordering.",
        "sections": [
            ("When hampers work well", ["Staff gifts where preferences vary.", "Client gifts where food-and-drink variety is safer.", "Premium presentation when perceived value matters."]),
            ("What to compare", ["Alcohol contents and alcohol-free versions.", "Dietary options and allergen information.", "Gift messages, VAT invoices and delivery dates."]),
            ("Buyer cautions", ["Low-spend hampers can feel retail rather than corporate.", "Delivery costs can change the real per-recipient budget.", "Substitutions may affect perceived quality."]),
        ],
        "supplier_routes": HAMPER_SUPPLIER_ROUTES,
        "faqs": [
            {"q": "Are corporate hampers better than wine gifts?", "a": "They can be better for mixed recipient groups or unknown preferences, but wine may suit known wine-friendly clients."},
            {"q": "What should I check before ordering hampers?", "a": "Check allergens, alcohol contents, delivery dates, gift notes, VAT invoices and substitutions."},
            {"q": "Does ClientCellar sell hampers?", "a": "No. ClientCellar provides planning guidance and links to supplier routes."},
            {"q": "Can hampers be used for staff gifts?", "a": "Yes, but keep dietary, cultural, alcohol-free and HR considerations visible."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Supplier directory", "/supplier-directory"), ("Premium example", "/example-premium-brief-pack"), ("Pricing", "/pricing")],
    },
    "best-wine-gifts-for-clients": {
        "title": "Best Wine Gifts for Clients",
        "h1": "Best wine gifts for clients",
        "description": "Choose better wine gifts for clients with UK-focused corporate gifting guidance, supplier routes and practical checks.",
        "intro": "The best client wine gift is not just an impressive bottle. It is a gift that fits the relationship, budget, timing, recipient suitability and supplier delivery reality.",
        "sections": [
            ("Client gift routes", ["Corporate wine gifting for standard client lists.", "Premium retailers for presentation-led VIP gifts.", "Local merchants for advice-led bottle choices."]),
            ("How to choose", ["Use broad-appeal styles unless preferences are known.", "Keep policy and alcohol suitability in mind.", "Match presentation level to relationship value."]),
            ("What good planning includes", ["Budget per recipient.", "Delivery deadline.", "Gift message tone.", "Fallback route if stock changes."]),
        ],
        "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1], HAMPER_SUPPLIER_ROUTES[1]],
        "faqs": [
            {"q": "What wine makes a good client gift?", "a": "Broad-appeal bottles, sparkling wine, mixed cases or wine-and-food hampers often work better than niche choices."},
            {"q": "Should I send wine to every client?", "a": "No. Consider alcohol suitability, policy and relationship context before choosing a wine-only gift."},
            {"q": "How can I make client gifts feel more personal?", "a": "Use tiering, a thoughtful message and supplier questions about presentation or gift notes."},
            {"q": "Can ClientCellar recommend exact bottles?", "a": "ClientCellar gives planning guidance and supplier routes, but live stock and suitability must be confirmed with suppliers."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Corporate wine gifts UK", "/corporate-wine-gifts-uk"), ("Supplier directory", "/supplier-directory"), ("Premium example", "/example-premium-brief-pack")],
    },
    "corporate-gifting-ideas-uk": {
        "title": "Corporate Gifting Ideas UK",
        "h1": "Corporate gifting ideas UK",
        "description": "Practical UK corporate gifting ideas for clients, staff and business relationships, with supplier routes and planning checks.",
        "intro": "Good corporate gifting is practical as much as creative. Start with the recipient type, budget, timing and suitability, then choose a supplier route that can actually fulfil the brief.",
        "sections": [
            ("Useful gift ideas", ["Corporate wine gifts for wine-friendly clients.", "Food and drink hampers for mixed tastes.", "Non-alcoholic drinks or food-only gifts where alcohol is unsuitable.", "Premium hampers for VIP relationships."]),
            ("How to shortlist", ["Separate clients, staff and VIPs.", "Decide whether alcohol is appropriate.", "Compare supplier routes before choosing a product."]),
            ("What to ask before buying", ["Can you support the required quantity?", "Can you include gift messages?", "Can you provide VAT invoices?", "What happens if products are out of stock?"]),
        ],
        "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[1]],
        "faqs": [
            {"q": "What are good corporate gifting ideas in the UK?", "a": "Wine gifts, hampers, premium food gifts, alcohol-free drinks and event-adjacent gifts can all work when matched to recipient suitability."},
            {"q": "What should businesses avoid?", "a": "Avoid gifts that feel too personal, unsuitable, policy-sensitive or hard to deliver reliably."},
            {"q": "How does ClientCellar help?", "a": "The free planner turns recipient count, budget and occasion into practical supplier-route guidance."},
            {"q": "Do you provide live prices?", "a": "No. Supplier pricing, stock and delivery must be confirmed directly."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Gift planner", "/gift-planner"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
    },
    "event-wine-planning-uk": {
        "title": "Event Wine Planning UK",
        "h1": "Event wine planning UK",
        "description": "Plan wine for UK corporate events with quantity guidance, supplier routes, logistics reminders and event planning checks.",
        "intro": "Event wine planning is about more than bottle count. You need guest assumptions, format, delivery ownership, chilling, glassware, alcohol-free options and venue rules agreed before ordering.",
        "sections": [
            ("Planning priorities", ["Estimate attendee count, format and event duration.", "Decide whether wine is served, tasted or gifted.", "Confirm venue rules, corkage and service ownership."]),
            ("Operational reminders", ["Delivery window and venue access.", "Chilling, glassware, water and spittoons where relevant.", "Alcohol-free alternatives that feel considered."]),
            ("Supplier questions", ["Can you supply the required quantity by the event date?", "Can you advise on red, white and sparkling mix?", "What substitutions might be made?", "Is sale-or-return available?"]),
        ],
        "supplier_routes": EVENT_SUPPLIER_ROUTES,
        "faqs": [
            {"q": "How much wine do I need for a corporate event?", "a": "It depends on format, duration, food and guest profile. Use the event planner for an estimate and confirm with suppliers or the venue."},
            {"q": "Should I use a venue wine package?", "a": "Venue packages can reduce admin, but check corkage, service charges, house wine quality and minimum spend."},
            {"q": "Does ClientCellar supply event wine?", "a": "No. ClientCellar provides planning guidance and supplier routes."},
            {"q": "What should I confirm before ordering?", "a": "Confirm quantities, delivery, chilling, glassware, substitutions, venue access and alcohol-free options."},
        ],
        "primary_cta": ("Create a free event plan", "/event-planner"),
        "example_url": "/example-premium-event-pack",
        "related": [("Event planner", "/event-planner"), ("Supplier directory", "/supplier-directory"), ("Event premium example", "/example-premium-event-pack")],
    },
    "wine-for-corporate-events": {
        "title": "Wine for Corporate Events",
        "h1": "Wine for corporate events",
        "description": "Choose wine for corporate events with UK supplier routes, quantity checks, event logistics and alcohol-free considerations.",
        "intro": "Wine for corporate events should fit the occasion, audience and service setup. A board dinner, team social, client reception and virtual tasting all need different supplier questions.",
        "sections": [
            ("Choose by event type", ["Client entertainment needs polished but safe choices.", "Team socials need inclusive alcohol-free options.", "Receptions need simple serving plans and reliable quantities."]),
            ("Mix and quantity", ["Confirm attendee count and service duration.", "Ask suppliers about red, white, sparkling and alcohol-free balance.", "Plan water, food, glassware and chilling."]),
            ("Practical checks", ["Venue corkage and delivery access.", "Supplier lead times and substitutions.", "Who handles service, cleanup and leftover stock."]),
        ],
        "supplier_routes": EVENT_SUPPLIER_ROUTES,
        "faqs": [
            {"q": "What wine is best for a corporate event?", "a": "Broad-appeal styles usually work best unless the event is a specialist tasting."},
            {"q": "Can I buy from a supermarket or retailer?", "a": "For simple self-managed events, mainstream retailers can be useful. Confirm case availability, delivery slots and substitutions."},
            {"q": "Should alcohol-free options be included?", "a": "Yes. Inclusive events should include adult alcohol-free alternatives."},
            {"q": "Does ClientCellar confirm event quantities?", "a": "ClientCellar provides planning estimates only. Confirm final quantities with suppliers, caterers or venues."},
        ],
        "primary_cta": ("Create a free event plan", "/event-planner"),
        "example_url": "/example-premium-event-pack",
        "related": [("Event wine planning UK", "/event-wine-planning-uk"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
    },
    "thank-you-gifts-for-clients": {
        "title": "Thank You Gifts for Clients",
        "h1": "Thank-you gifts for clients",
        "description": "Plan thank-you gifts for UK clients with wine, hamper and premium supplier route guidance from ClientCellar.",
        "intro": "Client thank-you gifts should feel warm, professional and proportionate. The right supplier route depends on the relationship, budget, timing and whether alcohol is suitable.",
        "sections": [
            ("Good thank-you routes", ["Wine gifts for known wine-friendly clients.", "Hampers when preferences are unclear.", "Premium retailers for senior relationships.", "Local merchants for advice-led VIP gifts."]),
            ("Tone and message", ["Keep the note short and specific.", "Avoid sales-heavy wording.", "Make the gift feel like appreciation, not pressure."]),
            ("Checks before sending", ["Client gift policy.", "Recipient suitability.", "Delivery address accuracy.", "Supplier substitution rules."]),
        ],
        "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[1]],
        "faqs": [
            {"q": "What is a good thank-you gift for clients?", "a": "Wine, hampers, sparkling wine or alcohol-free premium drinks can work when they fit the client and occasion."},
            {"q": "When should I send a thank-you gift?", "a": "Common moments include project completion, renewals, referrals or long-term relationship milestones."},
            {"q": "Should thank-you gifts be expensive?", "a": "Not necessarily. Proportionate, well-presented and easy-to-receive gifts often work best."},
            {"q": "Can ClientCellar write the supplier brief?", "a": "The free planner creates guidance, and the Premium Brief Pack provides supplier-ready copy and comparison structure."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Gift planner", "/gift-planner"), ("Premium example", "/example-premium-brief-pack"), ("Supplier directory", "/supplier-directory")],
    },
    "staff-wine-gifts-uk": {
        "title": "Staff Wine Gifts UK",
        "h1": "Staff wine gifts UK",
        "description": "Plan staff wine gifts in the UK with guidance on alcohol suitability, alternatives, budgets and supplier routes.",
        "intro": "Staff wine gifts need care because teams have mixed preferences, policies and alcohol suitability. Treat alcohol-free and hamper alternatives as normal options, not afterthoughts.",
        "sections": [
            ("When staff wine gifts work", ["Small team thank-yous where preferences are known.", "Optional celebration packs.", "Recognition gifts with equal-value alternatives."]),
            ("Inclusive planning", ["Offer alcohol-free options.", "Check dietary and cultural considerations.", "Avoid making alcohol feel expected."]),
            ("Supplier checks", ["Delivery to home or office addresses.", "Gift messages and VAT invoices.", "Substitutions and failed-delivery handling."]),
        ],
        "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[2], HAMPER_SUPPLIER_ROUTES[0], seo_supplier("Waitrose Cellar Gifts", "waitrose-cellar", "Mainstream retail wine gifts and recognised options.", "Useful for straightforward staff or team gifting comparisons.", "View wine gifts")],
        "faqs": [
            {"q": "Are wine gifts suitable for staff?", "a": "Sometimes, but staff gifting needs extra attention to alcohol suitability, HR guidance and equal-value alternatives."},
            {"q": "What is a safer staff gifting route?", "a": "Hampers, choice-based gifts or alcohol-free premium drinks can be safer for mixed teams."},
            {"q": "Should gifts go to home addresses?", "a": "Only if you have permission and clean address data. Confirm delivery handling with suppliers."},
            {"q": "Does ClientCellar sell staff gifts?", "a": "No. ClientCellar provides planning guidance and supplier-route links."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Corporate gifting ideas UK", "/corporate-gifting-ideas-uk"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
    },
    "premium-client-gifts-uk": {
        "title": "Premium Client Gifts UK",
        "h1": "Premium client gifts UK",
        "description": "Plan premium client gifts in the UK with guidance on wine, hampers, VIP tiers, supplier checks and approval-ready briefs.",
        "intro": "Premium client gifts should feel considered, polished and proportionate. The strongest route is usually a clear VIP tier, a premium supplier option and written checks before payment.",
        "sections": [
            ("Premium routes to compare", ["Fortnum & Mason or premium retailers for presentation-led hampers.", "Corporate wine suppliers for scalable premium wine gifts.", "Local merchants for advice-led VIP bottle choices."]),
            ("Approval considerations", ["Gift value and policy fit.", "Business reason for the gift.", "VAT, delivery and itemised supplier quote.", "Substitution and presentation quality."]),
            ("Avoid overpaying", ["Do not choose prestige before confirming delivery practicality.", "Use mainstream fallback suppliers for standard recipients.", "Reserve boutique routes for senior relationships."]),
        ],
        "supplier_routes": [HAMPER_SUPPLIER_ROUTES[1], WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1]],
        "faqs": [
            {"q": "What makes a client gift premium?", "a": "Presentation, supplier reliability, suitability and thoughtful context matter as much as product price."},
            {"q": "Should premium gifts be sent to all clients?", "a": "Usually no. Tiering helps reserve premium routes for senior or strategically important relationships."},
            {"q": "What should procurement approve?", "a": "Ask for itemised quotes, VAT treatment, delivery costs, substitution rules and business justification."},
            {"q": "Can ClientCellar compare supplier quotes?", "a": "The Premium Brief Pack gives a comparison matrix structure, but suppliers must confirm their own quotes directly."},
        ],
        "primary_cta": ("Create a free gift plan", "/gift-planner"),
        "example_url": "/example-premium-brief-pack",
        "related": [("Premium example", "/example-premium-brief-pack"), ("Pricing", "/pricing"), ("Supplier directory", "/supplier-directory")],
    },
}

SUPPLIER_INTENT_SEO_PAGES = {
    "corporate-wine-gift-suppliers-uk": {
        "title": "Corporate Wine Gift Suppliers UK: How to Shortlist Better Options",
        "h1": "Corporate wine gift suppliers in the UK",
        "description": "Compare what matters when choosing UK corporate wine gift suppliers, from budgets and delivery to presentation, personalisation and client suitability.",
        "intro": "This page is for business buyers who need a better supplier shortlist before they start sending enquiry emails. ClientCellar does not sell wine directly or pretend every supplier is a partner; use this as a practical way to compare routes and ask better questions.",
        "editorial_label": "Supplier shortlisting",
        "editorial_heading": "Choose the supplier around the job, not the bottle photo",
        "editorial_intro": [
            "Corporate wine gifting is rarely just a product decision. The supplier has to handle budgets, recipient data, substitutions, gift messages, invoices and delivery timing.",
            "A good shortlist normally includes one scalable corporate route, one premium route for senior recipients, and one sensible fallback if alcohol suitability is unclear.",
        ],
        "decision": {
            "heading": "What to compare before ordering",
            "headers": ["Criteria", "What good looks like", "Watch-out"],
            "rows": [
                ["Corporate ordering", "Clear business contact route, VAT invoice and bulk order support", "Consumer checkout only"],
                ["Delivery", "Multi-address support, cut-off dates and failed-delivery process", "Unclear substitutions or no delivery reporting"],
                ["Presentation", "Gift notes, packaging options and proofing where needed", "Branding that makes the gift feel like marketing"],
                ["Suitability", "Alcohol-free or hamper alternatives available", "Assuming every recipient drinks wine"],
            ],
        },
        "advisory": {
            "heading": "Editorially useful beats commercially convenient",
            "paragraphs": [
                "ClientCellar is building supplier ideas and shortlists around buyer usefulness: fit for the brief, operational reliability and suitability for business gifting.",
                "Where commercial relationships exist in future, they should not replace basic judgement. Buyers still need to confirm live stock, pricing, delivery and policies directly.",
            ],
        },
        "supplier_routes": WINE_GIFT_SUPPLIER_ROUTES,
        "supplier_heading": "Supplier routes worth comparing",
        "primary_cta": ("Create a gift brief", "/gift-planner"),
        "full_guide": ("Read the corporate wine gifts guide", "/guides/corporate-wine-gifts-uk"),
        "related_guides": [
            ("Corporate wine gifts UK", "/guides/corporate-wine-gifts-uk", "The fuller buying guide for budgets, notes and supplier routes."),
            ("Best client wine gifts", "/guides/best-client-wine-gifts", "Useful when you need gift ideas by client type and occasion."),
            ("Business gift wine etiquette", "/guides/business-gift-wine-etiquette", "Policy and suitability checks before sending alcohol."),
        ],
        "related": [
            ("Gift Planner", "/gift-planner"),
            ("Event Planner", "/event-planner"),
            ("Guides", "/guides"),
            ("Supplier Partnerships", "/supplier-partnerships"),
            ("Corporate hamper suppliers", "/corporate-hamper-suppliers-uk"),
        ],
        "image": "/images/clientcellar/guide-corporate-wine-gifts.webp",
        "imageAlt": "Corporate wine gift bottle and packaging for supplier shortlisting",
        "image_width": 1200,
        "image_height": 900,
        "cta_eyebrow": "Supplier inclusion",
        "cta_heading": "Are you a UK wine, hamper or gifting supplier?",
        "cta_text": "ClientCellar is building a practical UK resource for corporate gifting, wine gifts and event planning. If you supply businesses, client gifting teams or event organisers, tell us about your range for possible editorial inclusion.",
    },
    "corporate-hamper-suppliers-uk": {
        "title": "Corporate Hamper Suppliers UK: What to Check Before Ordering",
        "h1": "Corporate hamper suppliers in the UK",
        "description": "A practical guide to choosing UK corporate hamper suppliers for client gifts, team rewards and Christmas gifting.",
        "intro": "Corporate hampers can be the safest route for mixed recipients, but only when the contents, delivery and supplier process stand up. This page helps you compare hamper suppliers before the order turns into a late-season scramble.",
        "editorial_label": "Supplier shortlisting",
        "editorial_heading": "The contents list matters more than the basket",
        "editorial_intro": [
            "A hamper photographs well long before anyone knows whether it contains useful, generous or suitable items. Read the contents list carefully and ask what can be substituted.",
            "For business gifting, supplier reliability often matters as much as taste: delivery dates, address handling, gift messages, allergens and VAT invoices all need checking.",
        ],
        "decision": {
            "heading": "Corporate hamper supplier checks",
            "headers": ["Criteria", "What to ask", "Why it matters"],
            "rows": [
                ["Contents", "Exact item list, sizes, alcohol contents and substitutions", "Avoids filler and disappointment"],
                ["Dietary needs", "Allergens, vegetarian, vegan and alcohol-free options", "Keeps gifts usable for mixed teams"],
                ["Fulfilment", "Multi-address upload, delivery tracking and failed-delivery handling", "Prevents December admin pain"],
                ["Presentation", "Gift note, branding restraint and packaging quality", "Makes the gift feel considered"],
            ],
        },
        "advisory": {
            "heading": "Use hampers when variety solves a problem",
            "paragraphs": [
                "Hampers are strong for client teams, staff rewards and uncertain preferences. They are weaker when they are bought only because nobody wanted to choose properly.",
                "For senior clients, restrained premium presentation usually works better than oversized packaging.",
            ],
        },
        "supplier_routes": HAMPER_SUPPLIER_ROUTES,
        "supplier_heading": "Hamper supplier routes worth comparing",
        "primary_cta": ("Plan a hamper brief", "/gift-planner"),
        "full_guide": ("Read the wine hamper guide", "/guides/wine-gift-hampers-uk"),
        "related_guides": [
            ("Wine gift hampers UK", "/guides/wine-gift-hampers-uk", "How to avoid weak hampers and overpackaged gifts."),
            ("Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts", "Seasonal planning when delivery windows matter."),
            ("Food and wine hampers", "/guides/food-and-wine-hampers", "Useful when wine alone feels too narrow."),
        ],
        "related": [
            ("Gift Planner", "/gift-planner"),
            ("Event Planner", "/event-planner"),
            ("Guides", "/guides"),
            ("Supplier Partnerships", "/supplier-partnerships"),
            ("Client gift suppliers", "/client-gift-suppliers-uk"),
        ],
        "image": "/images/clientcellar/supplier-premium-hampers.webp",
        "imageAlt": "Corporate hamper with wine and food gifts",
        "image_width": 1200,
        "image_height": 900,
        "cta_eyebrow": "Supplier inclusion",
        "cta_heading": "Are you a UK wine, hamper or gifting supplier?",
        "cta_text": "ClientCellar is building a practical UK resource for corporate gifting, wine gifts and event planning. If you supply businesses, client gifting teams or event organisers, tell us about your range for possible editorial inclusion.",
    },
    "client-gift-suppliers-uk": {
        "title": "Client Gift Suppliers UK: Better Ways to Shortlist Business Gifts",
        "h1": "Client gift suppliers in the UK",
        "description": "How to compare client gift suppliers in the UK, including budgets, delivery, brand fit, alcohol policies and premium options.",
        "intro": "Client gift suppliers are not interchangeable. The right choice depends on relationship value, recipient suitability, delivery risk, budget and whether the gift should feel personal, scalable or premium.",
        "editorial_label": "Supplier shortlisting",
        "editorial_heading": "Start with the relationship, then choose the route",
        "editorial_intro": [
            "A new client, a long-term account, a referral partner and a client team are different gifting problems. Supplier choice should follow that context.",
            "Use this page to build a shortlist that includes practical corporate fulfilment, premium options where appropriate, and safer alternatives when alcohol is not the right answer.",
        ],
        "decision": {
            "heading": "How to compare client gift suppliers",
            "headers": ["Buyer need", "Supplier route", "Question to ask"],
            "rows": [
                ["Many recipients", "Corporate gifting or wine supplier", "Can they handle bulk data and delivery reporting?"],
                ["Senior relationship", "Premium hamper or merchant route", "Is the gift polished without being excessive?"],
                ["Unknown preferences", "Food hamper or alcohol-free route", "Is there an equal-quality alternative?"],
                ["Policy-sensitive client", "Modest and practical route", "Can the value and reason be justified?"],
            ],
        },
        "advisory": {
            "heading": "Do not let supplier convenience decide the gift",
            "paragraphs": [
                "A supplier with a slick checkout may still be wrong for the recipient. A slower advice-led merchant may be better for one VIP gift and worse for a 200-recipient Christmas list.",
                "ClientCellar’s supplier ideas are selection-led and planning-led. Confirm live commercial terms directly before ordering.",
            ],
        },
        "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1], HAMPER_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[1]],
        "supplier_heading": "Supplier routes for client gifts",
        "primary_cta": ("Create a client gift plan", "/gift-planner"),
        "full_guide": ("Read best client wine gifts", "/guides/best-client-wine-gifts"),
        "related_guides": [
            ("Best client wine gifts", "/guides/best-client-wine-gifts", "Gift ideas by relationship, budget and occasion."),
            ("Client gifting etiquette UK", "/guides/client-gifting-etiquette-uk", "Useful before gifts become awkward."),
            ("Corporate gift ideas for clients", "/guides/corporate-gift-ideas-for-clients", "Broader ideas beyond wine."),
        ],
        "related": [
            ("Gift Planner", "/gift-planner"),
            ("Event Planner", "/event-planner"),
            ("Guides", "/guides"),
            ("Supplier Partnerships", "/supplier-partnerships"),
            ("Wine gift suppliers", "/wine-gift-suppliers-for-businesses"),
        ],
        "image": "/images/clientcellar/guides/client-wine-gifts.webp",
        "imageAlt": "Client gift with wine and thank-you card",
        "image_width": 1200,
        "image_height": 900,
        "cta_eyebrow": "Supplier inclusion",
        "cta_heading": "Are you a UK wine, hamper or gifting supplier?",
        "cta_text": "ClientCellar is building a practical UK resource for corporate gifting, wine gifts and event planning. If you supply businesses, client gifting teams or event organisers, tell us about your range for possible editorial inclusion.",
    },
    "christmas-client-gift-suppliers": {
        "title": "Christmas Client Gift Suppliers: UK Shortlisting Guide",
        "h1": "Christmas client gift suppliers",
        "description": "A practical guide to finding Christmas client gift suppliers, avoiding late ordering problems and choosing gifts that feel appropriate.",
        "intro": "Christmas client gifting is where supplier choice becomes operational. The gift still needs taste and judgement, but order cut-offs, clean data and substitutions decide whether it lands well.",
        "editorial_label": "Supplier shortlisting",
        "editorial_heading": "December rewards the organised buyer",
        "editorial_intro": [
            "The best Christmas supplier is not always the fanciest catalogue. It is the one that can handle the recipient list, delivery window, gift message and fallback plan without turning the buyer into a helpdesk.",
            "Build a shortlist early, then ask direct questions about stock, substitutions, branded notes, address files and final safe order dates.",
        ],
        "decision": {
            "heading": "Christmas supplier checks",
            "headers": ["Risk", "Question to ask", "Better sign"],
            "rows": [
                ["Late ordering", "What is the final safe order date?", "Clear cut-offs and proofing deadlines"],
                ["Address errors", "Do you provide a recipient file template?", "CSV upload or checked address process"],
                ["Stock changes", "How are substitutions approved?", "Written substitution policy"],
                ["Mixed recipients", "Can you provide hamper or alcohol-free alternatives?", "Equal-quality alternative routes"],
            ],
        },
        "advisory": {
            "heading": "Keep Christmas gifts warm, not chaotic",
            "paragraphs": [
                "A specific message and sensible recipient tiering can make a bulk Christmas order feel less bulk-bought.",
                "If you cannot confirm alcohol suitability, consider a hamper, food gift or alcohol-free route with the same care as the wine option.",
            ],
        },
        "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES[:2], *HAMPER_SUPPLIER_ROUTES[:2]],
        "supplier_heading": "Christmas gift supplier routes to compare",
        "primary_cta": ("Plan Christmas client gifts", "/gift-planner"),
        "full_guide": ("Read Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts"),
        "related_guides": [
            ("Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts", "The main seasonal wine gifting guide."),
            ("Corporate gifting recipient CSV template", "/guides/corporate-gifting-recipient-csv-template", "Useful when delivery admin is the main risk."),
            ("Wine gift hampers UK", "/guides/wine-gift-hampers-uk", "A safer route for mixed recipient preferences."),
        ],
        "related": [
            ("Gift Planner", "/gift-planner"),
            ("Event Planner", "/event-planner"),
            ("Guides", "/guides"),
            ("Supplier Partnerships", "/supplier-partnerships"),
            ("Corporate wine gift suppliers", "/corporate-wine-gift-suppliers-uk"),
        ],
        "image": "/images/clientcellar/guide-client-christmas-gifts.webp",
        "imageAlt": "Christmas wine gift hamper for client gifting",
        "image_width": 1200,
        "image_height": 900,
        "cta_eyebrow": "Supplier inclusion",
        "cta_heading": "Are you a UK wine, hamper or gifting supplier?",
        "cta_text": "ClientCellar is building a practical UK resource for corporate gifting, wine gifts and event planning. If you supply businesses, client gifting teams or event organisers, tell us about your range for possible editorial inclusion.",
    },
    "wine-gift-suppliers-for-businesses": {
        "title": "Wine Gift Suppliers for Businesses: What to Look For",
        "h1": "Wine gift suppliers for businesses",
        "description": "How businesses should choose wine gift suppliers for clients, stakeholders, teams and corporate events.",
        "intro": "Business wine gifts need more than a good bottle. The supplier has to support the way companies buy: clear pricing, VAT invoices, delivery confidence, presentation and sensible alternatives.",
        "editorial_label": "Supplier shortlisting",
        "editorial_heading": "Business buying has different pressure points",
        "editorial_intro": [
            "A personal wine gift can be chosen on taste. A business wine gift has to survive procurement, delivery, suitability and timing.",
            "Use this page to compare suppliers by what they help you manage, not just what they sell.",
        ],
        "decision": {
            "heading": "Business wine gift supplier criteria",
            "headers": ["Criteria", "Why it matters", "What to confirm"],
            "rows": [
                ["Invoice and pricing clarity", "Internal approval needs clean numbers", "VAT, delivery and itemised quotes"],
                ["Recipient handling", "Corporate lists create admin risk", "Address upload, tracking and failed delivery process"],
                ["Gift quality", "The gift represents your business", "Packaging, notes and substitution rules"],
                ["Use-case fit", "Clients, teams and events need different routes", "Wine-only, hamper, alcohol-free and event options"],
            ],
        },
        "advisory": {
            "heading": "A supplier shortlist should have a fallback",
            "paragraphs": [
                "For business gifting, one route rarely covers everything. Keep a scalable corporate supplier, a premium option and an alcohol-free or hamper alternative in view.",
                "If the wine is for an event rather than a gift list, use the Event Planner first; quantities, glassware and service may matter more than gift packaging.",
            ],
        },
        "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES, EVENT_SUPPLIER_ROUTES[0]],
        "supplier_heading": "Wine supplier routes for business use cases",
        "primary_cta": ("Create a gift plan", "/gift-planner"),
        "full_guide": ("Read the corporate wine gifts guide", "/guides/corporate-wine-gifts-uk"),
        "related_guides": [
            ("Corporate wine gifts UK", "/guides/corporate-wine-gifts-uk", "The main business wine gift buying guide."),
            ("Corporate event wine planning", "/guides/corporate-event-wine-planning", "Use this when the wine is for an event."),
            ("Champagne gifts for clients", "/guides/champagne-gifts-for-clients", "A more specific route for premium or celebratory gifts."),
        ],
        "related": [
            ("Gift Planner", "/gift-planner"),
            ("Event Planner", "/event-planner"),
            ("Guides", "/guides"),
            ("Supplier Partnerships", "/supplier-partnerships"),
            ("Client gift suppliers", "/client-gift-suppliers-uk"),
        ],
        "image": "/images/clientcellar/guide-corporate-wine-gifts.webp",
        "imageAlt": "Wine gifts for business supplier shortlisting",
        "image_width": 1200,
        "image_height": 900,
        "cta_eyebrow": "Supplier inclusion",
        "cta_heading": "Are you a UK wine, hamper or gifting supplier?",
        "cta_text": "ClientCellar is building a practical UK resource for corporate gifting, wine gifts and event planning. If you supply businesses, client gifting teams or event organisers, tell us about your range for possible editorial inclusion.",
    },
}

HIGH_INTENT_SEO_PAGES.update(SUPPLIER_INTENT_SEO_PAGES)

SEO_PAGES.update(HIGH_INTENT_SEO_PAGES)

SEO_PAGES.update(
    {
        "corporate-wine-gifts": {
            "title": "Corporate Wine Gifts | ClientCellar",
            "h1": "Corporate wine gifts for UK businesses",
            "description": "Plan UK corporate wine gifts with practical budget guidance, supplier routes and links to ClientCellar's gift planner.",
            "intro": "Corporate wine gifts are easy to buy and surprisingly easy to get wrong. The useful question is not which bottle looks smartest; it is whether the gift fits the recipient, the relationship and the delivery reality.",
            "editorial_heading": "Start with the reason for the gift",
            "editorial_intro": [
                "A renewal thank-you, a staff reward and a senior client Christmas gift should not all lead to the same bottle in a box. The route matters: corporate wine supplier, hamper, premium retailer, or a more advice-led merchant.",
                "This page is the short planning version. Use it to decide the route, then use the planner when you need supplier-ready next steps.",
            ],
            "decision": {
                "heading": "The quickest way to choose a route",
                "headers": ["Situation", "Better route", "Why"],
                "rows": [
                    ["Standard client list", "Corporate wine gifting supplier", "Better for repeat orders, delivery admin and business buying"],
                    ["Mixed recipients", "Hamper or alcohol-free option", "Safer when wine preference or suitability is unknown"],
                    ["Senior relationship", "Premium retailer or merchant", "Presentation and judgement matter more"],
                    ["Staff gifts", "Choice-led or equal-value routes", "Avoids making alcohol feel expected"],
                ],
            },
            "advisory": {
                "heading": "Do not choose the bottle before the context",
                "paragraphs": [
                    "A good bottle can still be the wrong gift. One bottle for a whole team creates a sharing problem. A premium Champagne can look awkward where the relationship is not warm enough. A hamper can be practical, but only if the contents are doing real work.",
                    "Confirm gift notes, VAT invoices, delivery addresses, alcohol-free alternatives and substitutions before anyone internally approves the spend.",
                ],
                "note": "The point is not to prove you know wine. The point is to make the recipient feel considered.",
            },
            "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES, HAMPER_SUPPLIER_ROUTES[0]],
            "supplier_heading": "Supplier routes worth comparing",
            "faqs": [
                {"q": "What is a sensible budget for corporate wine gifts?", "a": "Many UK businesses start around £30-£75 per recipient for standard gifts, with higher budgets reserved for senior or VIP relationships. Supplier pricing, VAT and delivery must be confirmed directly."},
                {"q": "Should corporate wine gifts include alcohol-free alternatives?", "a": "Yes where recipient suitability is uncertain, the gift is for staff, or the recipient group is mixed."},
                {"q": "Does ClientCellar sell the wine?", "a": "No. ClientCellar provides planning guidance and supplier-route links. You order directly from suppliers."},
            ],
            "primary_cta": ("Build a wine gift brief", "/gift-planner"),
            "full_guide": ("Read the full corporate wine gifts guide", "/guides/corporate-wine-gifts-uk"),
            "related_guides": [
                ("Corporate wine gifts UK", "/guides/corporate-wine-gifts-uk", "The fuller guide to budgets, notes, mistakes and supplier routes."),
                ("Business gift wine etiquette", "/guides/business-gift-wine-etiquette", "Use this when policy, value or alcohol suitability is sensitive."),
            ],
            "related": [("Client wine gifts", "/client-wine-gifts"), ("Staff wine gifts", "/staff-wine-gifts"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Turn the gift idea into a practical brief",
            "cta_text": "Tell ClientCellar who the gift is for, your budget and the occasion, and get clearer supplier routes before you start contacting suppliers.",
        },
        "corporate-wine-tasting-events": {
            "title": "Corporate Wine Tasting Events | ClientCellar",
            "h1": "Corporate wine tasting events",
            "description": "Plan corporate wine tasting events for clients and teams with practical guidance on format, suppliers, inclusion and event logistics.",
            "intro": "A good corporate tasting should feel social, relaxed and properly hosted. A bad one feels like a lecture with glasses.",
            "editorial_heading": "Keep the tasting human",
            "editorial_intro": [
                "Wine tasting events work best when people have permission to enjoy themselves without pretending to be experts. Blind tasting, food pairing and regional themes can all work, but the format should suit the group.",
                "For business events, the practical details matter as much as the wines: delivery, pacing, glassware, non-drinkers, venue rules and who is actually hosting the room.",
            ],
            "decision": {
                "heading": "Choose the format before the supplier",
                "headers": ["Format", "Best when", "Watch"],
                "rows": [
                    ["Hosted tasting", "Clients or teams need structure", "Host quality and pace"],
                    ["Blind tasting", "You want conversation and low pressure", "Keep it playful, not competitive"],
                    ["Virtual tasting", "Remote groups need shared experience", "Delivery lead times and substitutions"],
                    ["Food pairing", "The event includes hospitality", "Allergens and dietary needs"],
                ],
            },
            "advisory": {
                "heading": "Do not make non-drinkers spectators",
                "paragraphs": [
                    "A corporate tasting should not quietly exclude people. Ask suppliers about alcohol-free sparkling, adult soft drinks, food pairings and whether the format can still work for attendees who do not drink.",
                    "If the event is client-facing, keep the tone polished and avoid anything that relies on heavy drinking to feel successful.",
                ],
                "note": "The best tasting gives people something to talk about besides work.",
            },
            "supplier_routes": EVENT_SUPPLIER_ROUTES,
            "supplier_heading": "Event supplier routes to check",
            "faqs": [
                {"q": "What makes a good corporate wine tasting event?", "a": "A clear host, suitable wines, sensible pacing, food or water, and inclusive alcohol-free options usually matter more than obscure bottles."},
                {"q": "Can a wine tasting work for remote teams?", "a": "Yes, but delivery timing, substitutions, address handling and late arrivals need planning."},
                {"q": "Does ClientCellar run tastings?", "a": "No. ClientCellar helps you plan the brief and compare supplier routes."},
            ],
            "primary_cta": ("Plan a wine event", "/event-planner"),
            "full_guide": ("Read the wine tasting event guide", "/guides/wine-tasting-corporate-event"),
            "related_guides": [
                ("Wine tasting corporate event", "/guides/wine-tasting-corporate-event", "A more playful guide to tastings that do not feel forced."),
                ("Corporate event wine planning", "/guides/corporate-event-wine-planning", "Planning memo for quantities, service and supplier questions."),
            ],
            "related": [("Event wine planning UK", "/event-wine-planning-uk"), ("Wine for corporate events", "/wine-for-corporate-events"), ("Event planner", "/event-planner")],
            "example_url": "/example-premium-event-pack",
            "cta_heading": "Build a clearer event wine plan",
            "cta_text": "Use the event planner to turn guest count, format and budget into practical supplier questions.",
        },
        "client-wine-gifts": {
            "title": "Client Wine Gifts | ClientCellar",
            "h1": "Client wine gifts and customer thank-you gifts",
            "description": "Practical UK planning advice for client wine gifts, customer thank-yous, supplier routes and gift message tone.",
            "intro": "Client wine gifts should feel warm, useful and proportionate. They should not feel like a bribe, a flex, or an apology.",
            "editorial_heading": "The relationship decides the gift",
            "editorial_intro": [
                "A new client needs a safer, lighter touch than a long-standing client. A senior contact may suit a restrained premium route. A client team needs something shareable.",
                "The note matters because it tells the recipient why the gift exists. Without that, even a decent bottle can feel like a generic procurement line.",
            ],
            "decision": {
                "heading": "Client gift routes by relationship",
                "headers": ["Relationship", "Better route", "Tone"],
                "rows": [
                    ["New client", "Smart bottle pair or small hamper", "Polished but not heavy"],
                    ["Long-standing client", "Mixed case or premium hamper", "Warmer and more personal"],
                    ["Senior stakeholder", "Sparkling or restrained premium gift", "Elegant and simple"],
                    ["Client team", "Shareable case or hamper", "Practical"],
                ],
            },
            "advisory": {
                "heading": "Appreciation should not feel like pressure",
                "paragraphs": [
                    "Be careful with timing around decisions, renewals and negotiations. A thank-you after a project lands differently from a gift before a commercial decision.",
                    "If alcohol suitability is unclear, choose a food hamper or alcohol-free route with the same level of care. The alternative should not feel like an afterthought.",
                ],
            },
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1], HAMPER_SUPPLIER_ROUTES[1]],
            "faqs": [
                {"q": "What wine should I send to a client?", "a": "Broad-appeal sparkling, bottle pairs, mixed cases and wine-and-food hampers are often safer than niche bottles unless you know the client's taste."},
                {"q": "How much should I spend on a client wine gift?", "a": "The right spend depends on relationship value, policy and timing. Many standard gifts sit around £35-£100, with premium routes reserved for senior relationships."},
                {"q": "What should I write in a client gift note?", "a": "Mention the specific relationship, project or thanks. Keep it warm, short and not sales-led."},
            ],
            "primary_cta": ("Plan a client wine gift", "/gift-planner"),
            "full_guide": ("Read the client wine gifts guide", "/guides/client-wine-gifts"),
            "related_guides": [
                ("Client wine gifts", "/guides/client-wine-gifts", "The fuller relationship-led guide."),
                ("Best client wine gifts", "/guides/best-client-wine-gifts", "Decision-led ideas by client type."),
            ],
            "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Thank-you gifts for clients", "/thank-you-gifts-for-clients"), ("Gift planner", "/gift-planner")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Choose a client gift with a clearer reason",
            "cta_text": "Use the planner to match the route to the relationship, occasion and budget.",
        },
        "staff-wine-gifts": {
            "title": "Staff Wine Gifts | ClientCellar",
            "h1": "Staff wine gifts and employee recognition",
            "description": "Plan staff wine gifts and employee recognition with practical guidance on suitability, alternatives, budgets and delivery.",
            "intro": "Staff wine gifts need more care than client gifts because fairness, alcohol suitability and delivery experience all affect how the gift lands.",
            "editorial_heading": "Recognition should not create a problem",
            "editorial_intro": [
                "A wine gift can work for a small team where preferences are known. For larger or mixed teams, a hamper, choice-led gift or alcohol-free alternative may be more considerate.",
                "The gift should feel like recognition, not an assumption that everyone drinks or wants the same thing.",
            ],
            "decision": {
                "heading": "Staff gift route finder",
                "headers": ["Scenario", "Better route", "Why"],
                "rows": [
                    ["Small known team", "Bottle or bottle pair", "Simple and personal"],
                    ["Mixed workforce", "Choice-led gift or hamper", "More inclusive"],
                    ["Remote team", "Supplier delivery route", "Cleaner fulfilment"],
                    ["Top performers", "Tiered gift with clear reason", "Fairer when criteria are visible"],
                ],
            },
            "advisory": {
                "heading": "Make alternatives normal",
                "paragraphs": [
                    "Alcohol-free and dietary alternatives should be presented as proper choices, not apologetic substitutions. If staff have to ask for a different gift, the process already feels less thoughtful.",
                    "Check HR guidance, delivery address permissions, VAT invoices and failed-delivery handling before announcing a reward.",
                ],
            },
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[2], HAMPER_SUPPLIER_ROUTES[0], seo_supplier("Waitrose Cellar Gifts", "waitrose-cellar", "Mainstream retail wine gifts and recognised options.", "Useful for straightforward staff or team gifting comparisons.", "View wine gifts")],
            "faqs": [
                {"q": "Are wine gifts suitable for staff?", "a": "Sometimes, but staff gifting needs extra attention to alcohol suitability, HR guidance and equal-value alternatives."},
                {"q": "What is a safer staff gifting route?", "a": "Hampers, choice-based gifts or alcohol-free premium drinks can be safer for mixed teams."},
                {"q": "Should gifts go to home addresses?", "a": "Only if you have permission and clean address data. Confirm delivery handling with suppliers."},
            ],
            "primary_cta": ("Plan staff gifts", "/gift-planner"),
            "full_guide": ("Read the staff wine gifts guide", "/guides/wine-gifts-for-sales-teams"),
            "related_guides": [
                ("Non-alcoholic client gifts", "/guides/non-alcoholic-client-gifts", "Useful when alcohol suitability is uncertain."),
                ("Business gift wine etiquette", "/guides/business-gift-wine-etiquette", "Policy-aware gift guidance."),
            ],
            "related": [("Corporate wine gifts", "/corporate-wine-gifts"), ("Corporate gifting ideas UK", "/corporate-gifting-ideas-uk"), ("Gift planner", "/gift-planner")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Plan recognition without making assumptions",
            "cta_text": "Use ClientCellar to compare staff gifting routes with alcohol-free and hamper alternatives in mind.",
        },
        "corporate-christmas-wine-gifts": {
            "title": "Corporate Christmas Wine Gifts | ClientCellar",
            "h1": "Corporate Christmas wine gifts",
            "description": "Plan corporate Christmas wine gifts for clients and staff with practical guidance on supplier timing, messages and alternatives.",
            "intro": "Christmas wine gifting is where good intentions often get swallowed by December admin. The best gifts still feel like they came from a person.",
            "editorial_heading": "Avoid the December spreadsheet gift",
            "editorial_intro": [
                "Recipient lists, delivery cut-offs and approval deadlines are necessary, but none of them make the gift feel thoughtful. The gift still needs a reason and a message.",
                "Start early enough to choose properly, confirm delivery and keep alternatives available for people who do not drink alcohol.",
            ],
            "decision": {
                "heading": "Christmas gift route finder",
                "headers": ["Recipient", "Better route", "Watch"],
                "rows": [
                    ["Individual client", "Sparkling, pair or compact hamper", "Policy and tone"],
                    ["Client team", "Mixed case or shareable hamper", "Avoid one-bottle awkwardness"],
                    ["Staff", "Choice-led or alcohol-free route", "Suitability"],
                    ["Senior contact", "Premium but restrained gift", "Appropriateness"],
                ],
            },
            "advisory": {
                "heading": "The office delivery problem is real",
                "paragraphs": [
                    "A good Christmas gift sent to an empty office becomes a courier problem. Confirm where people will be, whether home delivery is appropriate and how failed deliveries are handled.",
                    "A smaller thoughtful gift with a proper note can beat a large beige hamper chosen in a rush.",
                ],
            },
            "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES[:2], *HAMPER_SUPPLIER_ROUTES[:2]],
            "supplier_heading": "Christmas supplier routes to compare",
            "faqs": [
                {"q": "When should UK businesses order client Christmas gifts?", "a": "Start planning well before December, especially for larger lists, branded notes or multi-address delivery."},
                {"q": "Are wine gifts appropriate for Christmas clients?", "a": "They can be, but check client policies and keep alcohol-free or hamper alternatives available."},
                {"q": "Should I use hampers instead of wine?", "a": "Hampers can be safer for mixed preferences or when individual wine tastes are unknown."},
            ],
            "primary_cta": ("Create a Christmas gift plan", "/gift-planner"),
            "full_guide": ("Read the full Christmas guide", "/guides/christmas-corporate-wine-gifts"),
            "related_guides": [("Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts", "A warmer full guide to avoiding forgettable December gifts."), ("Client wine gifts", "/guides/client-wine-gifts", "Relationship-led advice for client gifting tone and timing.")],
            "related": [("Client Christmas gifts UK", "/client-christmas-gifts-uk"), ("Corporate wine gifts", "/corporate-wine-gifts"), ("Gift planner", "/gift-planner")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Plan Christmas gifts before the rush",
            "cta_text": "Build a clearer route for client, team or staff Christmas gifts before supplier cut-offs become the main decision.",
        },
        "corporate-wine-gifts-uk": {
            "title": "Corporate Wine Gifts UK | ClientCellar",
            "h1": "Corporate wine gifts UK",
            "description": "A concise UK planning page for corporate wine gifts, with supplier routes, budget judgement and links to ClientCellar’s full guide and free planner.",
            "intro": "Use this page when you need to decide quickly what kind of corporate wine gift you are buying: bottle, pair, case, hamper or premium route.",
            "editorial_heading": "This is the action page, not the long guide",
            "editorial_intro": ["Corporate wine gifts work best when the brief is clear: who receives the gift, why it is being sent, whether it needs to be shared and whether alcohol is suitable.", "If you want the deeper editorial advice, read the full guide. If you need a practical supplier direction now, start with the planner."],
            "decision": {"heading": "Quick route finder", "headers": ["Need", "Route", "Watch"], "rows": [["Standard client list", "Corporate wine gifting supplier", "Bulk delivery and gift notes"], ["VIP client", "Premium retailer or merchant", "Policy and presentation"], ["Team gift", "Mixed case or hamper", "Shareability"], ["Uncertain alcohol suitability", "Hamper or alcohol-free route", "Equal quality alternatives"]]},
            "advisory": {"heading": "Do not choose the bottle before the context", "paragraphs": ["A bottle can be excellent and still be the wrong gift. A mixed case may be smarter for a team. A hamper may be safer when taste is unknown. Champagne may be right for a milestone, but too obvious for a quieter thank-you."], "note": "The point is not to prove you know wine. The point is to make the recipient feel considered."},
            "supplier_routes": WINE_GIFT_SUPPLIER_ROUTES,
            "faqs": [
                {"q": "What is a sensible budget for UK corporate wine gifts?", "a": "Many business buyers start with a planning band such as £30-£75 per recipient, then confirm current supplier pricing, VAT and delivery directly."},
                {"q": "Can ClientCellar supply the wine?", "a": "No. ClientCellar provides planning guidance and supplier-route recommendations. You order directly from suppliers."},
                {"q": "Should every client receive the same gift?", "a": "Not always. A simple VIP, standard and internal stakeholder tiering approach often works better."},
            ],
            "primary_cta": ("Build a wine gift brief", "/gift-planner"),
            "full_guide": ("Read the full corporate wine gifts guide", "/guides/corporate-wine-gifts-uk"),
            "related_guides": [("Corporate wine gifts UK", "/guides/corporate-wine-gifts-uk", "The fuller editorial guide to judgement, budget and message."), ("Best client wine gifts", "/guides/best-client-wine-gifts", "More decision-led client gift ideas.")],
            "related": [("Gift planner", "/gift-planner"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Build a wine gift brief",
            "cta_text": "Use the planner to turn recipient count, budget, occasion and suitability into a practical supplier direction.",
        },
        "client-christmas-gifts-uk": {
            "title": "Client Christmas Gifts UK | Thoughtful Corporate Gift Planning",
            "h1": "Client Christmas Gifts UK",
            "description": "Practical UK advice for choosing client Christmas gifts that feel thoughtful, appropriate and easy to manage, from wine gifts to hampers and team-friendly options.",
            "intro": "Client Christmas gifts have a habit of becoming a spreadsheet exercise. Names, addresses, budgets, order cut-offs. All necessary, but none of it makes the gift feel thoughtful.",
            "editorial_heading": "Keep the operations tidy without making the gift feel like admin",
            "editorial_intro": [
                "Christmas gifting is partly about taste and partly about timing. A good gift sent too late, to the wrong address, or without a clear message becomes a problem rather than a gesture.",
                "Start by separating individual client gifts from team gifts, then decide where you need a safe mainstream supplier and where a more personal route is worth the extra effort.",
            ],
            "decision": {
                "heading": "Choose by recipient, not by catalogue page",
                "headers": ["Situation", "Better route", "Why"],
                "rows": [
                    ["Individual client", "Sparkling, bottle pair or compact hamper", "Feels personal without being too much"],
                    ["Client team", "Mixed case or shareable hamper", "Avoids the one-bottle problem"],
                    ["Senior relationship", "Premium but restrained gift", "Polished without looking excessive"],
                    ["Unknown preferences", "Food hamper or alcohol-free route", "Safer for mixed suitability"],
                ],
            },
            "advisory": {
                "heading": "Do not send the same beige hamper to everyone",
                "paragraphs": [
                    "A standardised gift can still feel thoughtful if the message is specific and the route fits the recipient. The problem is not scale; it is letting scale remove all judgement.",
                    "Confirm office closures, home-delivery handling, gift messages, substitutions and VAT invoices before payment.",
                ],
                "note": "The message matters more at Christmas because everyone knows the gift may have been bought in bulk.",
            },
            "supplier_routes": [*WINE_GIFT_SUPPLIER_ROUTES[:2], *HAMPER_SUPPLIER_ROUTES[:2]],
            "supplier_heading": "Supplier routes for Christmas client gifts",
            "faqs": [
                {"q": "When should UK businesses order client Christmas gifts?", "a": "Start planning well before December, especially for larger lists, branded notes or multi-address delivery."},
                {"q": "Are wine gifts appropriate for Christmas clients?", "a": "They can be, but check client policies and keep alcohol-free or hamper alternatives available."},
                {"q": "Should I use hampers instead of wine?", "a": "Hampers can be safer for mixed preferences or when individual wine tastes are unknown."},
            ],
            "primary_cta": ("Create a Christmas gift plan", "/gift-planner"),
            "full_guide": ("Read the full Christmas guide", "/guides/christmas-corporate-wine-gifts"),
            "related_guides": [("Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts", "A warmer full guide to avoiding forgettable December gifts."), ("Client wine gifts", "/guides/client-wine-gifts", "Relationship-led advice for client gifting tone and timing.")],
            "related": [("Corporate wine gifts UK", "/corporate-wine-gifts-uk"), ("Gift planner", "/gift-planner"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Create a Christmas gift plan",
            "cta_text": "Use ClientCellar to decide the right Christmas route before supplier choice turns into deadline panic.",
        },
        "corporate-hampers-uk": {
            "title": "Corporate Hampers UK | Client and Team Gift Planning",
            "h1": "Corporate hampers UK",
            "description": "How to choose corporate hampers that feel useful rather than generic, with advice on wine hampers, team gifts, Christmas gifting and what to avoid.",
            "intro": "Corporate hampers are useful when they are genuinely shareable. They are weak when they are padded with filler and sent because nobody had a better idea.",
            "editorial_heading": "A hamper should solve a recipient problem, not a buyer problem",
            "editorial_intro": ["Hampers work well for mixed tastes, teams and Christmas gifting because they offer more than one way to enjoy the gift.", "The danger is buying the basket rather than the contents. Big is not automatically generous."],
            "decision": {"heading": "Hamper or wine case?", "headers": ["Situation", "Better choice", "Reason"], "rows": [["Client team", "Shareable hamper", "Food and drink variety helps"], ["Known wine lover", "Mixed wine case", "More value in the wine"], ["Christmas list", "Hamper with clear contents", "Seasonal and easy to share"], ["Senior client", "Premium restrained hamper", "Presentation without gimmicks"]]},
            "advisory": {"heading": "Read the contents list like a sceptic", "paragraphs": ["Look for exact items, allergen clarity, alcohol contents, substitutions and delivery protection. Tiny jars, vague wine descriptions and oversized packaging are signs the hamper may photograph better than it feels."], "note": "Do not buy the packaging. Buy the gift."},
            "supplier_routes": HAMPER_SUPPLIER_ROUTES,
            "faqs": [
                {"q": "Are corporate hampers better than wine gifts?", "a": "They can be better for mixed recipient groups or unknown preferences, but wine may suit known wine-friendly clients."},
                {"q": "What should I check before ordering hampers?", "a": "Check allergens, alcohol contents, delivery dates, gift notes, VAT invoices and substitutions."},
                {"q": "Can hampers be used for staff gifts?", "a": "Yes, but keep dietary, cultural, alcohol-free and HR considerations visible."},
            ],
            "primary_cta": ("Plan a hamper or wine gift", "/gift-planner"),
            "full_guide": ("Read the wine hamper guide", "/guides/wine-gift-hampers-uk"),
            "related_guides": [("Wine gift hampers UK", "/guides/wine-gift-hampers-uk", "A critical guide to avoiding filler and weak hampers."), ("Christmas corporate wine gifts", "/guides/christmas-corporate-wine-gifts", "Seasonal advice for client and team gifts.")],
            "related": [("Gift planner", "/gift-planner"), ("Supplier directory", "/supplier-directory"), ("Premium example", "/example-premium-brief-pack")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Plan a hamper or wine gift",
            "cta_text": "Use the planner to compare whether a hamper, mixed case, single bottle or alcohol-free route is the better fit.",
        },
        "best-wine-gifts-for-clients": {
            "title": "Best Wine Gifts for Clients | ClientCellar",
            "h1": "Best wine gifts for clients",
            "description": "Advisor-led UK guidance for choosing client wine gifts by relationship, occasion and budget, with links to deeper ClientCellar guides.",
            "intro": "The best client wine gift depends less on the bottle and more on the relationship. New client, long-term client, senior contact and team gift are not the same problem.",
            "editorial_heading": "Start with the relationship",
            "editorial_intro": ["A client gift should feel like appreciation, not pressure. For new clients, stay polished and modest. For long-standing clients, you can be warmer. For teams, make it shareable.", "The note does more work than most people think. A good bottle with a vague note can still feel generic."],
            "decision": {"heading": "Choose by client type", "headers": ["Client type", "Better gift route", "Why"], "rows": [["New client", "Smart bottle pair or compact hamper", "Warm without overdoing it"], ["Long-term client", "Mixed case or premium hamper", "Recognises the relationship"], ["Senior contact", "Sparkling or restrained premium gift", "Polished"], ["Client team", "Shareable case or hamper", "Avoids awkward distribution"]]},
            "advisory": {"heading": "A good gift should not feel like a sales tactic", "paragraphs": ["Avoid sending gifts during sensitive commercial decisions. Keep the wording specific to the project, relationship or thanks. If you are not sure they drink alcohol, use a hamper or alcohol-free option with the same level of care."], "note": "There is a fine line between generous and awkward."},
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1], HAMPER_SUPPLIER_ROUTES[1]],
            "faqs": [
                {"q": "What wine makes a good client gift?", "a": "Broad-appeal bottles, sparkling wine, mixed cases or wine-and-food hampers often work better than niche choices."},
                {"q": "Should I send wine to every client?", "a": "No. Consider alcohol suitability, policy and relationship context before choosing a wine-only gift."},
                {"q": "How can I make client gifts feel more personal?", "a": "Use tiering, a thoughtful message and supplier questions about presentation or gift notes."},
            ],
            "primary_cta": ("Find the right client gift", "/gift-planner"),
            "full_guide": ("Read the client wine gifts guide", "/guides/client-wine-gifts"),
            "related_guides": [("Client wine gifts", "/guides/client-wine-gifts", "Relationship-led client gift advice."), ("Best client wine gifts", "/guides/best-client-wine-gifts", "More specific gift ideas by client type.")],
            "related": [("Gift planner", "/gift-planner"), ("Corporate wine gifts UK", "/corporate-wine-gifts-uk"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Find the right client gift",
            "cta_text": "Use the planner to match gift route, supplier type and message tone to the client relationship.",
        },
        "corporate-gifting-ideas-uk": {
            "title": "Corporate Gifting Ideas UK | ClientCellar",
            "h1": "Corporate gifting ideas UK",
            "description": "Useful UK corporate gifting ideas across wine, hampers, food, coffee, experiences and alcohol-free alternatives, with practical planning guidance.",
            "intro": "Most corporate gifts are forgettable because they are chosen by category, not by context. Wine can be right, but it should not be the automatic answer.",
            "editorial_heading": "Choose the gift around the situation",
            "editorial_intro": ["A client thank-you, staff reward, customer campaign and event follow-up all need different judgement. The best route is the one the recipient can accept and enjoy with the least friction.", "Branded filler rarely feels like appreciation. Useful beats visible."],
            "decision": {"heading": "Gift ideas by context", "headers": ["Context", "Good route", "Why"], "rows": [["Client thank-you", "Wine, sparkling or compact hamper", "Warm and professional"], ["Mixed team", "Food hamper or choice-led gift", "Shareable and safer"], ["Alcohol unsuitable", "Coffee, tea, food or alcohol-free drinks", "Inclusive"], ["Closer relationship", "Experience or specialist merchant route", "More personal when appropriate"]]},
            "advisory": {"heading": "Where wine works, and where it does not", "paragraphs": ["Wine works for celebrations, thank-yous and known wine-friendly recipients. It is weaker where alcohol suitability is unknown, policy is sensitive or the gift is going to a broad customer list.", "Food, coffee, tea, alcohol-free drinks and choice-led options can be more thoughtful than forcing wine into the wrong situation."]},
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[1]],
            "faqs": [
                {"q": "What are good corporate gifting ideas in the UK?", "a": "Wine gifts, hampers, premium food gifts, alcohol-free drinks and event-adjacent gifts can all work when matched to recipient suitability."},
                {"q": "What should businesses avoid?", "a": "Avoid gifts that feel too personal, unsuitable, policy-sensitive or hard to deliver reliably."},
                {"q": "Do you provide live prices?", "a": "No. Supplier pricing, stock and delivery must be confirmed directly."},
            ],
            "primary_cta": ("Create a corporate gift plan", "/gift-planner"),
            "full_guide": ("Read the corporate gift ideas guide", "/guides/corporate-gift-ideas-for-clients"),
            "related_guides": [("Corporate gift ideas for clients", "/guides/corporate-gift-ideas-for-clients", "Broader editorial guidance beyond wine."), ("Business gift wine etiquette", "/guides/business-gift-wine-etiquette", "Use this when suitability or policy is unclear.")],
            "related": [("Gift planner", "/gift-planner"), ("Supplier directory", "/supplier-directory"), ("Pricing", "/pricing")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Create a corporate gift plan",
            "cta_text": "Turn a broad gifting idea into a more useful shortlist by recipient type, budget and suitability.",
        },
        "event-wine-planning-uk": {
            "title": "Event Wine Planning UK | Corporate Wine and Tasting Guide",
            "h1": "Event wine planning UK",
            "description": "Plan wine for corporate events, tastings and client evenings with practical guidance on quantities, styles, suppliers and non-alcoholic options.",
            "intro": "Event wine planning is not about choosing impressive bottles. It is about making sure guests have the right drink, at the right time, without awkward shortages or waste.",
            "editorial_heading": "Plan the event before the wine",
            "editorial_intro": ["Start with guest count, format, food, pacing and venue rules. A reception, dinner, client evening and tasting all need different assumptions.", "Non-drinkers, glassware, chilling, delivery access and corkage are not afterthoughts. They are the event working properly."],
            "decision": {"heading": "Event wine route finder", "headers": ["Event moment", "Better route", "Watch"], "rows": [["Reception", "Sparkling plus white-led mix", "Service speed"], ["Dinner", "Food-led red and white split", "Menu and pacing"], ["Client event", "Polished mainstream supplier route", "Professional tone"], ["Tasting", "Hosted supplier or merchant", "Inclusive format"], ["Mixed audience", "Adult alcohol-free options", "Equal quality"]]},
            "advisory": {"heading": "What hosts forget", "paragraphs": ["Ask who receives the delivery, who chills the wine, who provides glassware, who handles leftovers and what substitutions may be made. These practical questions shape the guest experience more than the label on the bottle.", "Use planning ranges, then confirm final quantities with the supplier, caterer or venue."], "note": "Event wine is hospitality plus logistics. Treat both seriously."},
            "supplier_routes": EVENT_SUPPLIER_ROUTES,
            "faqs": [
                {"q": "How much wine do I need for a corporate event?", "a": "It depends on format, duration, food and guest profile. Use the event planner for an estimate and confirm with suppliers or the venue."},
                {"q": "Should I use a venue wine package?", "a": "Venue packages can reduce admin, but check corkage, service charges, house wine quality and minimum spend."},
                {"q": "What should I confirm before ordering?", "a": "Confirm quantities, delivery, chilling, glassware, substitutions, venue access and alcohol-free options."},
            ],
            "primary_cta": ("Plan event wine", "/event-planner"),
            "full_guide": ("Read the event wine planning guide", "/guides/corporate-event-wine-planning"),
            "related_guides": [("Corporate event wine planning", "/guides/corporate-event-wine-planning", "The fuller planning memo for event wine."), ("Wine tasting corporate event", "/guides/wine-tasting-corporate-event", "How to make tastings fun without making them forced.")],
            "related": [("Event planner", "/event-planner"), ("Wine for corporate events", "/wine-for-corporate-events"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-event-pack",
            "cta_heading": "Plan event wine",
            "cta_text": "Build a clearer event wine brief around guest count, format, timing, service and supplier questions.",
        },
        "wine-for-corporate-events": {
            "title": "Wine for Corporate Events | ClientCellar",
            "h1": "Wine for corporate events",
            "description": "Choose wine for corporate events with UK supplier routes, quantity checks, event logistics and alcohol-free considerations.",
            "intro": "Wine for a corporate event is not just a shopping list. It is part of hospitality, pacing and logistics.",
            "editorial_heading": "The bottle is only one part of the event",
            "editorial_intro": [
                "A client reception, board dinner, team social and hosted tasting need different wine decisions. Before choosing bottles, decide how wine is being served, who is pouring it, what food is involved and what non-drinkers receive.",
                "If the venue controls service or corkage, the supplier decision may be partly made for you. If you are self-managing, delivery and chilling become your responsibility.",
            ],
            "decision": {
                "heading": "Match the wine route to the event",
                "headers": ["Event", "Useful route", "Watch"],
                "rows": [
                    ["Reception", "Sparkling and simple white-led mix", "Pace and glassware"],
                    ["Dinner", "Food-led red and white split", "Menu fit"],
                    ["Team social", "Mainstream supplier plus alcohol-free options", "Inclusivity"],
                    ["Client evening", "Polished supplier route", "Tone and service"],
                ],
            },
            "advisory": {
                "heading": "What makes the event feel smooth",
                "paragraphs": [
                    "Guests rarely remember the exact logistics, but they notice when glasses sit empty, wine is warm, or alcohol-free options look like an afterthought.",
                    "Ask suppliers or venues about delivery windows, substitutions, chilling, glassware, service, corkage and leftovers before committing.",
                ],
            },
            "supplier_routes": EVENT_SUPPLIER_ROUTES,
            "faqs": [
                {"q": "What wine is best for a corporate event?", "a": "Broad-appeal styles usually work best unless the event is a specialist tasting."},
                {"q": "Should alcohol-free options be included?", "a": "Yes. Inclusive events should include adult alcohol-free alternatives."},
                {"q": "Does ClientCellar confirm event quantities?", "a": "ClientCellar provides planning estimates only. Confirm final quantities with suppliers, caterers or venues."},
            ],
            "primary_cta": ("Plan event wine", "/event-planner"),
            "full_guide": ("Read the event wine planning guide", "/guides/corporate-event-wine-planning"),
            "related_guides": [("Corporate event wine planning", "/guides/corporate-event-wine-planning", "Practical planning memo for event wine."), ("Wine tasting corporate event", "/guides/wine-tasting-corporate-event", "Useful if the event is a hosted tasting.")],
            "related": [("Event wine planning UK", "/event-wine-planning-uk"), ("Event planner", "/event-planner"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-event-pack",
            "cta_heading": "Get a clearer event wine plan",
            "cta_text": "Use the event planner to shape quantities, styles and supplier questions before ordering.",
        },
        "thank-you-gifts-for-clients": {
            "title": "Thank You Gifts for Clients | ClientCellar",
            "h1": "Thank-you gifts for clients",
            "description": "Plan thank-you gifts for UK clients with wine, hamper and premium supplier route guidance from ClientCellar.",
            "intro": "A thank-you gift should not feel like a random bottle looking for a reason. The reason comes first.",
            "editorial_heading": "Say what the thanks is for",
            "editorial_intro": [
                "Was it a referral, a project delivered under pressure, a long-running relationship, or a useful introduction? Put that into the message and choose a gift that fits the weight of the moment.",
                "A modest bottle with a specific note can feel warmer than an expensive hamper with generic wording.",
            ],
            "decision": {
                "heading": "Thank-you routes that usually work",
                "headers": ["Moment", "Better route", "Tone"],
                "rows": [
                    ["Project completion", "Sparkling or bottle pair", "Specific and warm"],
                    ["Referral", "Smart bottle or compact hamper", "Grateful but proportionate"],
                    ["Client team", "Mixed case or shareable hamper", "Inclusive"],
                    ["Senior contact", "Premium restrained option", "Polished"],
                ],
            },
            "advisory": {
                "heading": "Proportion keeps it comfortable",
                "paragraphs": [
                    "Thank-you gifts can become awkward when the value feels disconnected from the reason. If the gift is doing too much work, rewrite the message first.",
                    "Avoid sending anything during a sensitive commercial decision. Appreciation should not look like pressure.",
                ],
            },
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[0], HAMPER_SUPPLIER_ROUTES[1]],
            "faqs": [
                {"q": "What is a good thank-you gift for clients?", "a": "Wine, hampers, sparkling wine or alcohol-free premium drinks can work when they fit the client and occasion."},
                {"q": "When should I send a thank-you gift?", "a": "Common moments include project completion, renewals, referrals or long-term relationship milestones."},
                {"q": "Should thank-you gifts be expensive?", "a": "Not necessarily. Proportionate, well-presented and easy-to-receive gifts often work best."},
            ],
            "primary_cta": ("Plan a thank-you gift", "/gift-planner"),
            "full_guide": ("Read thank-you wine gifts", "/guides/thank-you-wine-gifts"),
            "related_guides": [("Thank-you wine gifts", "/guides/thank-you-wine-gifts", "Warmer advice for thank-you moments."), ("Client wine gifts", "/guides/client-wine-gifts", "Relationship-led gift guidance.")],
            "related": [("Gift planner", "/gift-planner"), ("Best wine gifts for clients", "/best-wine-gifts-for-clients"), ("Premium example", "/example-premium-brief-pack")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Make the thank-you feel specific",
            "cta_text": "Use the planner to turn the reason for the gift into a clearer supplier route and message.",
        },
        "staff-wine-gifts-uk": {
            "title": "Staff Wine Gifts UK | ClientCellar",
            "h1": "Staff wine gifts UK",
            "description": "Plan staff wine gifts in the UK with guidance on alcohol suitability, alternatives, budgets and supplier routes.",
            "intro": "Staff wine gifts need care because teams have mixed preferences, policies and alcohol suitability. Treat alternatives as part of the gift, not a backup plan.",
            "editorial_heading": "Fairness matters as much as the bottle",
            "editorial_intro": [
                "A staff gift is judged by how easy it is to receive and enjoy. If someone has to ask for a non-alcoholic version, or feels awkward about the gift, the recognition loses some of its warmth.",
                "For larger teams, choice-led gifting, hampers and alcohol-free options often work better than one standard wine gift for everyone.",
            ],
            "decision": {
                "heading": "Staff gifting routes",
                "headers": ["Use case", "Better route", "Why"],
                "rows": [
                    ["Known small team", "Bottle or mixed pair", "Simple and personal"],
                    ["Large team", "Choice-led or hamper route", "More inclusive"],
                    ["Remote staff", "Supplier fulfilment", "Cleaner delivery"],
                    ["Recognition tier", "Clear tiered gift", "Fair if criteria are visible"],
                ],
            },
            "advisory": {
                "heading": "Do the boring checks early",
                "paragraphs": [
                    "Confirm HR guidance, address permissions, alcohol-free alternatives, VAT invoices, substitutions and failed-delivery handling before the gift is announced.",
                    "A reward should not become another admin task for the person receiving it.",
                ],
            },
            "supplier_routes": [WINE_GIFT_SUPPLIER_ROUTES[2], HAMPER_SUPPLIER_ROUTES[0], seo_supplier("Waitrose Cellar Gifts", "waitrose-cellar", "Mainstream retail wine gifts and recognised options.", "Useful for straightforward staff or team gifting comparisons.", "View wine gifts")],
            "faqs": [
                {"q": "Are wine gifts suitable for staff?", "a": "Sometimes, but staff gifting needs extra attention to alcohol suitability, HR guidance and equal-value alternatives."},
                {"q": "What is a safer staff gifting route?", "a": "Hampers, choice-based gifts or alcohol-free premium drinks can be safer for mixed teams."},
                {"q": "Should gifts go to home addresses?", "a": "Only if you have permission and clean address data. Confirm delivery handling with suppliers."},
            ],
            "primary_cta": ("Plan staff gifts", "/gift-planner"),
            "full_guide": ("Read staff gifting advice", "/guides/wine-gifts-for-sales-teams"),
            "related_guides": [("Business gift wine etiquette", "/guides/business-gift-wine-etiquette", "Policy and suitability guidance."), ("Non-alcoholic client gifts", "/guides/non-alcoholic-client-gifts", "Useful alcohol-free alternatives.")],
            "related": [("Corporate gifting ideas UK", "/corporate-gifting-ideas-uk"), ("Supplier directory", "/supplier-directory"), ("Gift planner", "/gift-planner")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Plan staff gifts with alternatives built in",
            "cta_text": "Use ClientCellar to compare staff gifting routes before choosing a supplier.",
        },
        "premium-client-gifts-uk": {
            "title": "Premium Client Gifts UK | ClientCellar",
            "h1": "Premium client gifts UK",
            "description": "Plan premium client gifts in the UK with guidance on wine, hampers, VIP tiers, supplier checks and approval-ready briefs.",
            "intro": "Premium client gifts should feel calm, considered and proportionate. Loud is not the same as generous.",
            "editorial_heading": "Restraint often looks more premium than excess",
            "editorial_intro": [
                "This is where corporate gifting can accidentally look least thoughtful. A trophy bottle may be impressive, but it can also be awkward if the recipient, timing or policy context is wrong.",
                "The stronger route is usually tiering: standard clients, VIP clients and internal stakeholders get different supplier routes for clear reasons.",
            ],
            "decision": {
                "heading": "Premium routes by purpose",
                "headers": ["Purpose", "Better route", "Watch"],
                "rows": [
                    ["VIP client", "Fortnum & Mason or premium merchant", "Policy and presentation"],
                    ["Standard high-value list", "Corporate wine supplier", "Scalable fulfilment"],
                    ["Known wine enthusiast", "Independent or specialist merchant", "Advice quality"],
                    ["Mixed tastes", "Premium hamper", "Filler and allergens"],
                ],
            },
            "advisory": {
                "heading": "Premium should be easy to justify",
                "paragraphs": [
                    "If the value is meaningful, keep a clear business reason, itemised quote and written supplier assumptions. VAT, delivery, substitutions and gift notes should be confirmed before approval.",
                    "A smaller elegant gift can look better than a huge showy one if it is easier to accept and better matched to the relationship.",
                ],
                "note": "A client gift should not feel like a bribe, a flex, or an apology.",
            },
            "supplier_routes": [HAMPER_SUPPLIER_ROUTES[1], WINE_GIFT_SUPPLIER_ROUTES[0], WINE_GIFT_SUPPLIER_ROUTES[1]],
            "faqs": [
                {"q": "What makes a client gift premium?", "a": "Presentation, supplier reliability, suitability and thoughtful context matter as much as product price."},
                {"q": "Should premium gifts be sent to all clients?", "a": "Usually no. Tiering helps reserve premium routes for senior or strategically important relationships."},
                {"q": "What should procurement approve?", "a": "Ask for itemised quotes, VAT treatment, delivery costs, substitution rules and business justification."},
            ],
            "primary_cta": ("Plan a premium client gift", "/gift-planner"),
            "full_guide": ("Read luxury corporate wine gifts", "/guides/luxury-corporate-wine-gifts"),
            "related_guides": [("Luxury corporate wine gifts", "/guides/luxury-corporate-wine-gifts", "Sharper advice on premium gifting without overdoing it."), ("Best wine gifts under £100", "/guides/best-wine-gifts-under-100", "Useful trade-offs around a strong gift budget.")],
            "related": [("Premium example", "/example-premium-brief-pack"), ("Pricing", "/pricing"), ("Supplier directory", "/supplier-directory")],
            "example_url": "/example-premium-brief-pack",
            "cta_heading": "Create a premium-ready gift brief",
            "cta_text": "Use the free planner first, then upgrade if you need supplier-ready emails, a matrix and approval summary.",
        },
    }
)


GUIDE_SLUG_REDIRECTS = {
    redirect_path.removeprefix("/guides/"): destination.removeprefix("/guides/")
    for redirect_path, destination in SEO_REDIRECTS.items()
    if redirect_path.startswith("/guides/") and destination.startswith("/guides/")
}


def canonicalise_internal_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/"):
        return path
    clean = canonical_path(path)
    return SEO_REDIRECTS.get(clean, clean)


def canonicalise_related_guide_slugs(slugs: list[str], current_slug: str | None = None) -> list[str]:
    canonical_slugs: list[str] = []
    for slug in slugs or []:
        canonical_slug = GUIDE_SLUG_REDIRECTS.get(slug, slug)
        if canonical_slug == current_slug or canonical_slug in canonical_slugs:
            continue
        canonical_slugs.append(canonical_slug)
    return canonical_slugs


def canonicalise_tuple_links(items: list[tuple]) -> list[tuple]:
    canonical_items = []
    for item in items or []:
        if not isinstance(item, tuple):
            canonical_items.append(item)
            continue
        canonical_items.append(
            tuple(canonicalise_internal_path(value) if index == 1 else value for index, value in enumerate(item))
        )
    return canonical_items


for guide_slug, guide_data in GUIDES.items():
    guide_data["related"] = canonicalise_related_guide_slugs(guide_data.get("related", []), guide_slug)

for seo_slug, seo_page in SEO_PAGES.items():
    if seo_page.get("primary_cta"):
        label, href = seo_page["primary_cta"]
        seo_page["primary_cta"] = (label, canonicalise_internal_path(href))
    if seo_page.get("full_guide"):
        label, href = seo_page["full_guide"]
        seo_page["full_guide"] = (label, canonicalise_internal_path(href))
    if seo_page.get("related_guides"):
        seo_page["related_guides"] = canonicalise_tuple_links(seo_page["related_guides"])
    if seo_page.get("related"):
        seo_page["related"] = canonicalise_tuple_links(seo_page["related"])
    if seo_page.get("example_url"):
        seo_page["example_url"] = canonicalise_internal_path(seo_page["example_url"])

SEO_META_UPDATES = {
    "corporate-wine-gifts": (
        "Corporate Wine Gifts UK: Supplier Ideas, Budgets & Safer Picks",
        "Plan better UK corporate wine gifts with supplier routes, budget checks, gift-message guidance and practical alternatives for clients and teams.",
    ),
    "client-christmas-gifts-uk": (
        "Client Christmas Gifts UK: Wine, Hampers & Better Supplier Ideas",
        "Choose better client Christmas gifts in the UK with wine, hamper and supplier-route guidance that avoids last-minute generic gifting.",
    ),
    "corporate-hampers-uk": (
        "Corporate Hampers UK: How to Choose Better Client Hampers",
        "A practical guide to corporate hampers in the UK, including contents checks, delivery questions, alcohol-free options and supplier routes.",
    ),
    "corporate-gifting-ideas-uk": (
        "Corporate Gifting Ideas UK: Practical Options for Clients and Teams",
        "Useful UK corporate gifting ideas across wine, hampers, food, alcohol-free options and experiences, with practical suitability checks.",
    ),
}

for seo_slug, (title, description) in SEO_META_UPDATES.items():
    if seo_slug in SEO_PAGES:
        SEO_PAGES[seo_slug]["title"] = title
        SEO_PAGES[seo_slug]["description"] = description

if "best-client-wine-gifts" in GUIDES:
    GUIDES["best-client-wine-gifts"]["title"] = "Best Wine Gifts for Clients: Safer Picks by Budget and Occasion"
    GUIDES["best-client-wine-gifts"]["description"] = "Choose better wine gifts for clients with practical ideas by budget, occasion and relationship, plus supplier checks before ordering."

if "champagne-gifts-for-clients" in GUIDES:
    champagne_guide = GUIDES["champagne-gifts-for-clients"]
    champagne_guide["title"] = "Is Champagne an Appropriate Corporate Gift? Client Gift Guide"
    champagne_guide["description"] = "Decide when Champagne is an appropriate corporate or client gift, what to send, what to spend and when English sparkling, hampers or alcohol-free gifts are safer."
    champagne_guide["h1"] = "Is Champagne an Appropriate Corporate or Client Gift?"
    champagne_guide["intro"] = "Champagne can be an appropriate corporate gift when the moment is genuinely celebratory, the relationship can carry the signal and alcohol is suitable for the recipient. Use this guide to decide whether Champagne is right, what to send if it is, and what to choose when a safer gift would be better."
    champagne_guide.setdefault("hero_summary", [])
    champagne_guide["hero_summary"] = [
        {"label": "Short answer", "text": "yes, for celebratory, senior or clearly appreciative client moments"},
        {"label": "Typical budget", "text": "£45-£150, depending on brand, packaging and relationship"},
        {"label": "Safer alternatives", "text": "English sparkling, wine hampers, mixed cases or premium alcohol-free gifts"},
    ]
    champagne_guide.setdefault("article_sections", []).insert(
        0,
        {
            "id": "quick-answer",
            "heading": "Quick answer: when champagne is appropriate",
            "paragraphs": [
                "Champagne is appropriate when the gift is tied to a real business moment: a completed project, a senior thank-you, a promotion, a successful event, a festive relationship gift or a genuine congratulations.",
                "It is less appropriate when the recipient is unknown, the relationship is early, the company has strict gift or alcohol rules, or the bottle could look like a flashy shortcut instead of a considered thank-you.",
            ],
            "bullets": [
                "Good fit: senior client thank-you, milestone, celebration, festive gift, polished congratulations.",
                "Risky fit: cold prospecting, early negotiation, unclear alcohol suitability, strict procurement policy.",
                "Safer swap: English sparkling, refined hamper, classic mixed case or premium alcohol-free sparkling.",
            ],
        },
    )
    champagne_guide.setdefault("faqs", []).insert(
        0,
        {
            "q": "I need to send champagne as a corporate gift to clients. What should I get?",
            "a": "Choose a recognised Champagne or English sparkling gift with smart packaging, a restrained note and confirmed delivery. For unknown tastes or stricter policies, a wine hamper, mixed case or premium alcohol-free option may be safer.",
        },
    )

if "best-client-wine-gifts" in GUIDES:
    best_client_guide = GUIDES["best-client-wine-gifts"]
    best_client_guide["intro"] = "This page is for the moment when you know you should send something, but you do not want the gift to feel like a line item in account management. Use it to choose client wine gifts by relationship, occasion and risk level before speaking to suppliers."
    best_client_guide.setdefault("article_sections", []).insert(
        0,
        {
            "id": "best-by-situation",
            "heading": "Best client wine gifts by situation",
            "paragraphs": [
                "The best client wine gift is rarely the most expensive bottle. It is the option that fits the relationship, occasion, recipient policy and delivery reality.",
                "For unknown tastes, start with broad-appeal routes. For senior contacts, use restraint and presentation. For teams, choose something shareable. For policy-sensitive relationships, consider alcohol-free or food-led alternatives.",
            ],
            "table": {
                "headers": ["Situation", "Safer gift route", "Why it works"],
                "rows": [
                    ["New client or prospect", "Smart single bottle or compact wine hamper", "Polished without feeling excessive."],
                    ["Long-standing client", "Bottle pair, mixed case or more personal merchant choice", "Allows more thought while staying professional."],
                    ["Senior contact", "Champagne, English sparkling or premium hamper", "Signals value without needing novelty."],
                    ["Client team", "Mixed case or food-and-wine hamper", "Shareable and less dependent on one person's taste."],
                    ["Alcohol suitability unclear", "Premium alcohol-free sparkling, coffee, tea or food hamper", "Keeps the gesture inclusive and easier to accept."],
                ],
            },
        },
    )
    best_client_guide.setdefault("internal_links", [])
    best_client_guide["internal_links"] = [
        {"label": "Use the gift planner", "href": "/gift-planner", "text": "turn recipient count, budget and timing into a practical brief."},
        {"label": "Compare supplier routes", "href": "/supplier-directory", "text": "see wine merchants, hamper suppliers and premium routes."},
        {"label": "View Premium Brief Pack example", "href": "/example-premium-brief-pack", "text": "see the supplier-ready output before upgrading."},
    ] + best_client_guide["internal_links"]

if "christmas-corporate-wine-gifts" in GUIDES:
    christmas_guide = GUIDES["christmas-corporate-wine-gifts"]
    christmas_guide["title"] = "Christmas Gifts for Clients: Corporate Wine & Hamper Ideas"
    christmas_guide["description"] = "Choose better Christmas gifts for clients with corporate wine, Champagne, hamper and alcohol-free routes, plus timing, supplier and delivery checks."
    christmas_guide["h1"] = "Christmas Gifts for Clients: Corporate Wine and Hamper Ideas"
    christmas_guide.setdefault("article_sections", []).insert(
        0,
        {
            "id": "client-christmas-gift-ideas",
            "heading": "Christmas gifts for clients: what works best",
            "paragraphs": [
                "The highest-impression Christmas queries are broad, so the page needs to answer the bigger question before narrowing into wine. Good client Christmas gifts are timely, easy to accept and specific enough not to feel like a mass send.",
                "Wine can work well, but it should sit alongside hampers, sparkling gifts, alcohol-free choices and policy-safe alternatives when the recipient list is mixed.",
            ],
            "bullets": [
                "For one senior contact: Champagne, English sparkling or a refined wine hamper.",
                "For a whole client team: mixed case, food-and-wine hamper or shareable gift.",
                "For policy-sensitive clients: alcohol-free sparkling, food hamper, coffee, tea or choice-led gift.",
                "For larger lists: supplier-led fulfilment, recipient CSV, delivery cut-offs and substitutions matter more than bottle novelty.",
            ],
        },
    )
    christmas_guide.setdefault("internal_links", [])
    christmas_guide["internal_links"] = [
        {"label": "Plan Christmas client gifts", "href": "/gift-planner", "text": "shape the recipient list, budget and supplier brief."},
        {"label": "Supplier directory", "href": "/supplier-directory", "text": "compare wine merchants and hamper suppliers before ordering."},
        {"label": "Champagne gifts for clients", "href": "/guides/champagne-gifts-for-clients", "text": "decide whether Champagne is the right festive signal."},
    ] + christmas_guide["internal_links"]


SEO_IMAGE_SLUG_OVERRIDES = {
    "corporate-wine-gifts-uk": "corporate-wine-gifts-uk-seo",
    "client-wine-gifts": "client-wine-gifts-seo",
}


def seo_page_image_asset_for(slug: str, page: dict) -> dict | None:
    image_slug = SEO_IMAGE_SLUG_OVERRIDES.get(slug, slug)
    return clean_guide_image_asset_for(image_slug, page)


for seo_slug, seo_page in SEO_PAGES.items():
    if seo_page.get("image"):
        seo_page.setdefault("imageAlt", guide_image_alt_for(seo_slug, seo_page))
        continue
    seo_image_asset = seo_page_image_asset_for(seo_slug, seo_page)
    if seo_image_asset:
        seo_page.update(seo_image_asset)


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


def supplier_directory_item_list_schema(request: Request, suppliers: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "UK wine gift supplier directory",
        "url": absolute_url(request, "/supplier-directory"),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": supplier["name"],
                "url": supplier.get("primaryUrl") or absolute_url(request, "/supplier-directory"),
            }
            for index, supplier in enumerate(suppliers, start=1)
        ],
    }


GUIDE_FALLBACK_FAQS = [
    {
        "q": "Are prices and stock live?",
        "a": "No. ClientCellar provides planning guidance only. Confirm current pricing, stock, delivery and suitability directly with suppliers.",
    },
    {
        "q": "Should we include alcohol-free alternatives?",
        "a": "Yes, where recipient suitability is uncertain or the gift is for a mixed workplace group. Alcohol is not suitable for every person or company policy.",
    },
]


def visible_guide_faqs(guide: dict) -> list[dict]:
    questions = list(guide.get("faqs") or [])
    if questions and len(questions) < 3:
        questions.extend(GUIDE_FALLBACK_FAQS)
    return questions


def faq_schema(questions: list[dict]) -> dict:
    visible_questions = [
        {"q": str(item.get("q", "")).strip(), "a": str(item.get("a", "")).strip()}
        for item in questions
        if item.get("q") and item.get("a")
    ]
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in visible_questions
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
    context.setdefault("has_live_affiliate_links", has_live_affiliate_links())
    context.setdefault("gift_recommendation_routes", gift_recommendation_routes())
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
        "Corporate Wine Gifts & Event Drinks Planning",
        "Plan better corporate wine gifts, client hampers and event drinks with ClientCellar’s free planning tools, UK supplier directory and practical wine gifting guides.",
        page_title="ClientCellar | Corporate Wine Gifts & Event Drinks Planning",
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
    example_preview = add_premium_advisory_sections(
        {
            "pack_type": "gift",
            "supplier_comparison": gift_supplier_comparison_rows(),
            "recommended_shortlist": gift_recommendation_shortlist(),
        },
        "gift",
        45,
        25,
    )
    return render(
        request,
        "example_premium_brief_pack.html",
        "Example Premium Brief Pack",
        "See an example ClientCellar Premium Brief Pack with supplier-ready buying brief, enquiry email, budget breakdown, supplier quote comparison table and internal approval summary.",
        structured_data=[premium_pack_product_schema(request)],
        example_supplier_links=example_supplier_links,
        example_preview=example_preview,
    )


@app.get("/example-premium-event-pack", response_class=HTMLResponse)
def example_premium_event_pack(request: Request):
    planner_input = {
        "event_type": "client_entertainment",
        "attendee_count": 40,
        "budget_per_person": 65,
        "format": "in_person",
        "location": "London",
        "tone": "client_safe",
        "date": "Early December",
        "wine_knowledge_level": "mixed",
        "food_pairing_needed": True,
        "known_preferences": "Polished, beginner-friendly and inclusive, with alcohol-free alternatives.",
    }
    event_req = EventPlanRequest(**planner_input)
    planner_output = make_event_plan(event_req)
    example_preview = make_premium_pack_preview(
        PremiumPackPreviewRequest(
            pack_type="event",
            planner_input=planner_input,
            planner_output=planner_output,
        )
    )
    example_preview["pack_name"] = "Example Premium Event Brief Pack"
    return render(
        request,
        "premium_pack_view.html",
        "Example Premium Event Brief Pack",
        "See an example ClientCellar Premium Event Brief Pack with supplier recommendations, event planning notes, supplier enquiry email, budget breakdown and comparison matrix.",
        structured_data=[premium_pack_product_schema(request)],
        preview=example_preview,
        pack={"pack_type": "event"},
        pack_token="example-event-pack",
        payment_verified=False,
        is_example_pack=True,
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


def make_high_intent_seo_route(slug: str):
    def high_intent_seo_route(request: Request):
        return render_seo_landing(request, slug)

    high_intent_seo_route.__name__ = f"seo_{slug.replace('-', '_')}"
    return high_intent_seo_route


for high_intent_slug in HIGH_INTENT_SEO_PAGES:
    app.add_api_route(
        f"/{high_intent_slug}",
        make_high_intent_seo_route(high_intent_slug),
        response_class=HTMLResponse,
        methods=["GET"],
    )


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
    track_server_event(
        "checkout_success_page_viewed",
        request,
        checkout_session_id=session_id,
        metadata={"source": "checkout_success"},
    )

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
                    track_server_event(
                        "premium_access_granted",
                        request,
                        report_type=(pack or {}).get("pack_type"),
                        checkout_session_id=session_id,
                        metadata={"pack_token": pack_token, "payment_status": payment_status},
                    )
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
            track_server_event(
                "premium_access_failed",
                request,
                checkout_session_id=session_id,
                metadata={"error": "checkout_success_verification_failed"},
            )

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
        track_server_event(
            "premium_access_failed",
            request,
            metadata={"pack_token": pack_token, "error": "pack_not_found"},
        )
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
        track_server_event(
            "premium_access_failed",
            request,
            report_type=pack.get("pack_type"),
            metadata={"pack_token": pack_token, "payment_status": pack.get("payment_status"), "error": "payment_not_verified"},
        )
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
    if pack.get("pack_type") in {"gift", "event"}:
        track_server_event(
            f"{pack.get('pack_type')}_premium_viewed",
            request,
            report_type=pack.get("pack_type"),
            checkout_session_id=pack.get("stripe_session_id"),
            metadata={"pack_token": pack_token, "payment_status": pack.get("payment_status")},
        )
    track_server_event(
        "premium_access_granted",
        request,
        report_type=pack.get("pack_type"),
        checkout_session_id=pack.get("stripe_session_id"),
        metadata={"pack_token": pack_token, "payment_status": pack.get("payment_status")},
    )

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


@app.get("/supplier-directory", response_class=HTMLResponse)
def supplier_directory_page(request: Request):
    directory_suppliers = supplier_directory_entries()
    categories = sorted({supplier["category"] for supplier in directory_suppliers})
    best_use_filters = [
        "Corporate gifts",
        "Premium hampers",
        "Events",
        "Independent merchant",
        "Budget-friendly",
        "Luxury",
    ]
    budgets = ["£-££", "££", "£££"]
    return render(
        request,
        "supplier_directory.html",
        "UK Wine Gift Supplier Directory",
        "Compare UK wine gift suppliers for corporate gifting, client hampers, event drinks and business thank-you gifts. Editorially selected by ClientCellar.",
        suppliers=directory_suppliers,
        featured_suppliers=featured_supplier_directory_entries(),
        categories=categories,
        best_use_filters=best_use_filters,
        budgets=budgets,
        structured_data=[
            breadcrumb_schema(request, [("Home", "/"), ("Supplier directory", "/supplier-directory")]),
            supplier_directory_item_list_schema(request, directory_suppliers),
        ],
    )


@app.get("/uk-wine-gift-supplier-comparison", response_class=HTMLResponse)
def supplier_comparison_page(request: Request):
    return render(
        request,
        "supplier_comparison.html",
        "UK Wine Gift Supplier Comparison",
        "Compare UK wine gift suppliers by use case, budget, delivery complexity, corporate gifting support and presentation style.",
    )


@app.get("/submit-supplier", response_class=HTMLResponse)
def submit_supplier_page(request: Request):
    return render(
        request,
        "submit_supplier.html",
        "Submit a Supplier",
        "Suggest a UK wine gift, hamper, tasting or corporate event supplier for possible inclusion in the ClientCellar supplier directory.",
    )


@app.get("/uk-wine-gift-suppliers")
def uk_wine_gift_suppliers_redirect():
    return RedirectResponse(url="/supplier-directory", status_code=301)


@app.get("/wine-gift-suppliers-uk")
def wine_gift_suppliers_uk_redirect():
    return RedirectResponse(url="/supplier-directory", status_code=301)


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
    report_type = "event" if "event" in (source_page or "") else "gift" if "gift" in (source_page or "") else None
    track_server_event(
        "supplier_click",
        request,
        page_path=source_page or request.headers.get("referer"),
        report_type=report_type,
        supplier_name=supplier.get("name"),
        supplier_url=destination,
        metadata={"source": "supplier_outbound", "source_page": source_page},
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
        "Wine Gift & Corporate Event Guides UK",
        "Practical UK guides for corporate wine gifts, client gifting, hampers, Christmas gifts and event wine planning — written to help you choose something more thoughtful.",
        guides=GUIDES,
        seo_pages=SEO_PAGES,
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
        guides=GUIDES,
        structured_data=[
            breadcrumb_schema(request, [("Home", "/"), ("Guides", "/guides"), (page["h1"], f"/{slug}")]),
            *([faq_schema(page["faqs"])] if page.get("faqs") else []),
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
            *([faq_schema(visible_guide_faqs(guide))] if guide.get("faqs") else []),
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
    return render(
        request,
        "affiliate_disclosure.html",
        "Affiliate Disclosure",
        "How ClientCellar may use affiliate links while keeping UK wine gifting recommendations editorially useful and transparent.",
    )


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
        "How UK wine merchants, hamper companies and event drinks suppliers can be considered for ClientCellar editorial listings.",
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
    guide_urls = [f"/guides/{slug}" for slug in SITEMAP_GUIDE_SLUGS if slug in GUIDES]
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


def fetch_analytics_events(days: int = 30, limit: int = 10000) -> list[dict]:
    settings = supabase_settings()
    if not settings["service_configured"]:
        return []
    days = max(1, min(days, 90))
    limit = max(1, min(limit, 10000))
    since_dt = datetime.utcnow().replace(microsecond=0) - timedelta(days=days)
    since_value = urllib.parse.quote(since_dt.isoformat() + "Z", safe=":-TZ")
    url = (
        f"{settings['url']}/rest/v1/analytics_events"
        f"?select=created_at,event_name,session_id,page_path,device_type,report_type,supplier_name,supplier_url,checkout_session_id"
        f"&created_at=gte.{since_value}&order=created_at.desc&limit={limit}"
    )
    try:
        data = _supabase_json_request(
            url,
            headers={
                "apikey": settings["service_role_key"],
                "Authorization": f"Bearer {settings['service_role_key']}",
            },
            timeout=8,
        )
    except Exception as error:
        print("Supabase analytics summary fetch failed:", str(error))
        return []
    return data if isinstance(data, list) else []


def analytics_count(rows: list[dict], event_names: set[str]) -> int:
    return sum(1 for row in rows if row.get("event_name") in event_names)


def analytics_group_count(rows: list[dict], key: str, event_names: set[str] | None = None, limit: int = 12) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        if event_names and row.get("event_name") not in event_names:
            continue
        value = str(row.get(key) or "unknown")[:180]
        counts[value] = counts.get(value, 0) + 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def analytics_summary_for_days(days: int) -> dict:
    rows = fetch_analytics_events(days)
    free_reports = analytics_count(rows, {"gift_free_report_generated", "event_free_report_generated"})
    upgrade_clicks = analytics_count(rows, {"gift_upgrade_clicked", "event_upgrade_clicked", "example_upgrade_clicked"})
    checkout_starts = analytics_count(rows, {"gift_checkout_started", "event_checkout_started"})
    successful_payments = analytics_count(rows, {"stripe_webhook_completed"})
    return {
        "days": days,
        "analytics_configured": supabase_settings()["service_configured"],
        "event_count": len(rows),
        "visits_by_page": analytics_group_count(rows, "page_path", {"page_view"}),
        "planner_starts": {
            "gift": analytics_count(rows, {"gift_planner_started"}),
            "event": analytics_count(rows, {"event_planner_started"}),
            "total": analytics_count(rows, {"gift_planner_started", "event_planner_started"}),
        },
        "free_reports_generated": {
            "gift": analytics_count(rows, {"gift_free_report_generated"}),
            "event": analytics_count(rows, {"event_free_report_generated"}),
            "total": free_reports,
        },
        "upgrade_clicks": {
            "gift": analytics_count(rows, {"gift_upgrade_clicked"}),
            "event": analytics_count(rows, {"event_upgrade_clicked"}),
            "example": analytics_count(rows, {"example_upgrade_clicked"}),
            "total": upgrade_clicks,
        },
        "checkout_starts": checkout_starts,
        "successful_payments": successful_payments,
        "supplier_clicks": analytics_count(rows, {"supplier_click", "gift_supplier_clicked", "event_supplier_clicked"}),
        "free_report_to_upgrade_click_rate": round(upgrade_clicks / free_reports, 4) if free_reports else 0,
        "checkout_start_to_payment_success_rate": round(successful_payments / checkout_starts, 4) if checkout_starts else 0,
        "gift_vs_event": analytics_group_count(rows, "report_type", None),
        "mobile_vs_desktop": analytics_group_count(rows, "device_type", None),
        "top_free_report_pages": analytics_group_count(
            rows,
            "page_path",
            {"gift_free_report_generated", "event_free_report_generated"},
            limit=10,
        ),
        "top_upgrade_click_pages": analytics_group_count(
            rows,
            "page_path",
            {"gift_upgrade_clicked", "event_upgrade_clicked", "example_upgrade_clicked"},
            limit=10,
        ),
        "top_checkout_start_pages": analytics_group_count(
            rows,
            "page_path",
            {"gift_checkout_started", "event_checkout_started"},
            limit=10,
        ),
        "top_supplier_click_pages": analytics_group_count(
            rows,
            "page_path",
            {"supplier_click", "gift_supplier_clicked", "event_supplier_clicked"},
            limit=10,
        ),
        "top_clicked_suppliers": analytics_group_count(
            rows,
            "supplier_name",
            {"supplier_click", "gift_supplier_clicked", "event_supplier_clicked"},
            limit=10,
        ),
    }


@app.post("/api/analytics")
def analytics_event(req: AnalyticsEventRequest, request: Request):
    if req.event_name not in ANALYTICS_EVENT_ALLOWLIST:
        return Response(status_code=204)
    payload = build_analytics_payload(
        req.event_name,
        request,
        page_path=req.page_path,
        referrer=req.referrer,
        device_type=req.device_type,
        viewport_width=req.viewport_width,
        session_id=req.session_id,
        report_type=req.report_type,
        supplier_name=req.supplier_name,
        supplier_url=req.supplier_url,
        checkout_session_id=req.checkout_session_id,
        metadata=req.metadata,
        timestamp=req.timestamp,
    )
    store_analytics_event(payload)
    return Response(status_code=204)


@app.get("/api/admin/analytics-summary")
def admin_analytics_summary(request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD")
    supplied_password = request.query_params.get("password", "")
    if not admin_password or supplied_password != admin_password:
        raise HTTPException(status_code=403, detail="Analytics summary is not enabled or the password is incorrect.")
    return {
        "last_7_days": analytics_summary_for_days(7),
        "last_30_days": analytics_summary_for_days(30),
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
    track_server_event(
        "checkout_session_created",
        request,
        report_type=req.pack_type,
        checkout_session_id=session.id,
        metadata={"pack_token": pack_token, "source": "stripe_checkout"},
    )
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
            track_server_event(
                "stripe_webhook_completed",
                request,
                report_type=stripe_obj_get(metadata, "pack_type"),
                checkout_session_id=stripe_obj_get(data_obj, "id"),
                metadata={"pack_token": pack_token, "stripe_event_type": event_type, "payment_status": payment_status},
            )
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
            track_server_event(
                "stripe_webhook_completed",
                request,
                report_type=stripe_obj_get(metadata, "pack_type"),
                checkout_session_id=stripe_obj_get(data_obj, "id"),
                metadata={"stripe_event_type": event_type, "payment_status": payment_status, "error": "missing_pack_token"},
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
