import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from main import app


client = TestClient(app)


def test_homepage_loads():
    assert client.get("/").status_code == 200


def test_gift_planner_loads():
    assert client.get("/gift-planner").status_code == 200


def test_event_planner_loads():
    assert client.get("/event-planner").status_code == 200


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_checkout_success_loads_without_session_id():
    response = client.get("/checkout/success")
    assert response.status_code == 200
    assert "Payment received" in response.text


def test_checkout_success_loads_with_fake_session_id():
    response = client.get("/checkout/success?session_id=fake")
    assert response.status_code == 200
    assert "Payment received" in response.text


def test_checkout_cancelled_loads():
    response = client.get("/checkout/cancelled")
    assert response.status_code == 200
    assert "Checkout cancelled" in response.text


def test_billing_pages_load():
    success = client.get("/billing/success")
    cancel = client.get("/billing/cancel")
    assert success.status_code == 200
    assert "Payment received" in success.text
    assert cancel.status_code == 200
    assert "Checkout cancelled" in cancel.text


def test_premium_pack_page_loads():
    response = client.get("/premium-pack")
    assert response.status_code == 200
    assert "Premium Brief Pack" in response.text


def test_missing_premium_pack_view_loads_friendly_error(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "clientcellar.db")
    response = client.get("/premium-pack/view/not-a-real-token")
    assert response.status_code == 404
    assert "Pack not found" in response.text


def test_pricing_page_loads():
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "Pricing" in response.text


def test_commercial_content_routes_load():
    for path in [
        "/suppliers",
        "/about",
        "/contact",
        "/terms",
        "/privacy",
        "/affiliate-disclosure",
        "/corporate-wine-gifts",
        "/corporate-wine-tasting-events",
        "/client-wine-gifts",
        "/staff-wine-gifts",
        "/corporate-christmas-wine-gifts",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "404" not in response.text


def test_new_high_intent_guides_load():
    for path in [
        "/guides/corporate-wine-gifts-under-50",
        "/guides/corporate-wine-gifts-under-100",
        "/guides/luxury-wine-gifts-for-clients",
        "/guides/english-sparkling-corporate-gifts",
        "/guides/wine-gifts-for-sales-teams",
        "/guides/wine-gifts-for-agencies",
        "/guides/wine-gifts-for-law-firms",
        "/guides/wine-gifts-for-accountancy-firms",
        "/guides/client-gift-policy-checklist",
        "/guides/corporate-gifting-recipient-csv-template",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "<h1" in response.text
        assert "Turn this guide into a practical plan" in response.text


def test_sitemap_includes_public_seo_and_excludes_checkout_pages():
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    text = response.text
    assert "/guides/corporate-wine-gifts-under-50" in text
    assert "/guides/corporate-gifting-recipient-csv-template" in text
    assert "/corporate-wine-gifts" in text
    assert "/checkout/success" not in text
    assert "/billing/success" not in text
    assert "/admin" not in text


def test_checkout_pages_are_noindex():
    response = client.get("/checkout/success")
    assert response.status_code == 200
    assert 'name="robots" content="noindex, nofollow"' in response.text


def test_homepage_has_structured_data_and_conversion_links():
    response = client.get("/")
    assert response.status_code == 200
    assert 'application/ld+json' in response.text
    assert "See Premium Brief Pack" in response.text
    assert "/guides/corporate-wine-gifts-uk" in response.text


def test_account_routes_load():
    for path in ["/sign-in", "/login", "/account", "/logout"]:
        response = client.get(path)
        assert response.status_code == 200


def test_gift_plan_endpoint():
    response = client.post(
        "/api/gift-plan",
        json={
            "recipient_type": "clients",
            "recipient_count": 12,
            "budget_per_recipient": 45,
            "occasion": "Christmas thank-you",
            "gift_style": "not_sure",
            "tone": "safe",
            "uk_only": True,
            "international_needed": False,
            "personal_message_needed": True,
            "branding_needed": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "supplier_shortlist" in data
    assert "supplier_category" in data
    assert "internal_approval_summary" in data


def test_event_plan_endpoint():
    response = client.post(
        "/api/event-plan",
        json={
            "event_type": "team_social",
            "attendee_count": 20,
            "budget_per_person": 50,
            "format": "virtual",
            "tone": "fun",
            "wine_knowledge_level": "beginner",
            "food_pairing_needed": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "event_structure" in data
    assert "supplier_category" in data
    assert "internal_approval_summary" in data


def test_premium_status_defaults_to_free():
    response = client.get("/api/premium-status")
    assert response.status_code == 200
    data = response.json()
    assert data["loggedIn"] is False
    assert data["authenticated"] is False
    assert data["plan"] == "free"
    assert data["isPremium"] is False
    assert data["premium"] is False


def test_checkout_allows_one_off_purchase_without_login(monkeypatch):
    captured = {}

    class FakeSession:
        url = "https://checkout.stripe.test/session"
        id = "cs_test_no_user"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    monkeypatch.setattr(main, "payments_enabled", lambda: True)
    monkeypatch.setattr(main, "verify_supabase_access_token", lambda token: None)
    monkeypatch.setattr(main, "generate_pack_token", lambda: "pack_no_user")
    monkeypatch.setattr(main, "save_premium_pack", lambda **kwargs: 1)
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("APP_BASE_URL", "https://clientcellar.test")

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    response = client.post("/api/create-checkout-session", json={"pack_type": "gift"})
    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.test/session"
    assert captured["metadata"]["supabase_user_id"] == ""
    assert captured["payment_intent_data"]["metadata"]["supabase_user_id"] == ""


def test_checkout_session_includes_supabase_metadata(monkeypatch):
    captured = {}

    class FakeSession:
        url = "https://checkout.stripe.test/session"
        id = "cs_test_123"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    monkeypatch.setattr(main, "payments_enabled", lambda: True)
    monkeypatch.setattr(main, "verify_supabase_access_token", lambda token: {"id": "user_123", "email": "buyer@example.com"} if token == "valid-token" else None)
    monkeypatch.setattr(main, "generate_pack_token", lambda: "pack_123")
    monkeypatch.setattr(main, "save_premium_pack", lambda **kwargs: 1)
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("APP_BASE_URL", "https://clientcellar.test")

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    response = client.post(
        "/api/stripe/create-checkout-session",
        headers={"Authorization": "Bearer valid-token"},
        json={"pack_type": "gift"},
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.test/session"
    assert captured["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert captured["success_url"] == "https://clientcellar.test/billing/success?session_id={CHECKOUT_SESSION_ID}"
    assert captured["cancel_url"] == "https://clientcellar.test/billing/cancel"
    assert captured["customer_email"] == "buyer@example.com"
    assert captured["metadata"]["supabase_user_id"] == "user_123"
    assert captured["metadata"]["email"] == "buyer@example.com"
    assert captured["metadata"]["product"] == "clientcellar_premium_brief_pack"
    assert captured["payment_intent_data"]["metadata"]["supabase_user_id"] == "user_123"
    assert captured["payment_intent_data"]["metadata"]["email"] == "buyer@example.com"
    assert captured["payment_intent_data"]["metadata"]["product"] == "clientcellar_premium_brief_pack"


def test_auth_config_defaults_to_unconfigured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_ANON_KEY", raising=False)
    response = client.get("/api/auth-config")
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_premium_preview_requires_backend_confirmed_access():
    response = client.post(
        "/api/premium-pack-preview",
        json={
            "pack_type": "gift",
            "planner_input": {},
            "planner_output": {},
        },
    )
    assert response.status_code == 403
    assert "Premium Brief Pack features require a completed one-off purchase" in response.text
