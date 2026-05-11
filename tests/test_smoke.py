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
    assert "Your Premium Brief Pack is saved" in response.text


def test_checkout_success_loads_with_fake_session_id():
    response = client.get("/checkout/success?session_id=fake")
    assert response.status_code == 200
    assert "Your Premium Brief Pack is saved" in response.text


def test_checkout_cancelled_loads():
    response = client.get("/checkout/cancelled")
    assert response.status_code == 200
    assert "Checkout cancelled" in response.text


def test_billing_pages_load():
    success = client.get("/billing/success")
    cancel = client.get("/billing/cancel")
    assert success.status_code == 200
    assert "Your Premium Brief Pack is saved" in success.text
    assert cancel.status_code == 200
    assert "Checkout cancelled" in cancel.text


def test_premium_pack_page_loads():
    response = client.get("/premium-pack")
    assert response.status_code == 200
    assert "Premium Brief Pack" in response.text


def test_my_packs_page_loads():
    response = client.get("/my-packs")
    assert response.status_code == 200
    assert "Find your Premium Brief Packs" in response.text
    assert "Send access link" in response.text


def test_missing_premium_pack_view_loads_friendly_error(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "clientcellar.db")
    response = client.get("/premium-pack/view/not-a-real-token")
    assert response.status_code == 404
    assert "We couldn’t find this Premium Brief Pack." in response.text
    assert "Create a new plan" in response.text


def test_paid_premium_pack_view_renders_fallback_content(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "clientcellar.db")
    token = "verified-pack-token"
    main.save_premium_pack(
        pack_token=token,
        pack_type="gift",
        customer_email="buyer@example.com",
        payment_status="paid",
    )

    response = client.get(f"/premium-pack/view/{token}")

    assert response.status_code == 200
    assert "Executive summary" in response.text
    assert "Supplier enquiry email" in response.text
    assert "Supplier quote comparison table" in response.text
    assert "Internal approval summary" in response.text
    assert "Some planning details were not available" in response.text
    assert "Saved pack" in response.text


def test_pack_access_request_is_generic_and_calls_email_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "clientcellar.db")
    token = "saved-access-token"
    main.save_premium_pack(
        pack_token=token,
        pack_type="gift",
        customer_email="buyer@example.com",
        payment_status="paid",
        premium_preview={"pack_name": "Saved gift pack", "pack_type": "gift", "executive_summary": "Saved content"},
    )
    calls = []

    def fake_send_email(recipient_email, subject, text_body, html_body=None):
        calls.append((recipient_email, subject, text_body))
        return {"sent": True, "id": "email_123"}

    monkeypatch.setattr(main, "send_email", fake_send_email)
    monkeypatch.setattr(main, "PACK_ACCESS_REQUEST_COUNTS", {})

    response = client.post("/api/premium-packs/request-access", json={"email": "buyer@example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "If that email has saved packs, we’ll send a secure access link.",
    }
    assert calls[0][0] == "buyer@example.com"
    assert calls[0][1] == "Your ClientCellar Premium Brief Packs"
    assert f"/premium-pack/view/{token}" in calls[0][2]
    assert token not in response.text


def test_pack_access_request_does_not_reveal_missing_email(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "fetch_paid_premium_packs_by_email", lambda email: [])
    monkeypatch.setattr(main, "send_pack_recovery_email", lambda request, email, packs: calls.append((email, packs)) or [])

    response = client.post("/api/premium-packs/request-access", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json()["message"] == "If that email has saved packs, we’ll send a secure access link."
    assert "missing" not in response.text
    assert calls == [("missing@example.com", [])]


def test_pack_ready_email_uses_resend_helper():
    calls = []

    def fake_send_email(recipient_email, subject, text_body, html_body=None):
        calls.append((recipient_email, subject, text_body))
        return {"sent": True, "id": "email_ready"}

    original = main.send_email
    main.send_email = fake_send_email
    try:
        class DummyRequest:
            base_url = "https://clientcellar.test/"

        payload = main.build_premium_pack_email(DummyRequest(), "buyer@example.com", "secure-token")
    finally:
        main.send_email = original

    assert payload["send_result"]["sent"] is True
    assert calls[0][0] == "buyer@example.com"
    assert calls[0][1] == "Your ClientCellar Premium Brief Pack is ready"
    assert "/premium-pack/view/secure-token" in calls[0][2]


def test_pricing_page_loads():
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "Pricing" in response.text


def test_pricing_premium_cta_routes_to_planner_not_checkout():
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "Create free plan" in response.text
    assert "copy-ready business documents" in response.text
    assert "data-pack-checkout" not in response.text


def test_commercial_content_routes_load():
    for path in [
        "/suppliers",
        "/about",
        "/contact",
        "/terms",
        "/privacy",
        "/privacy-policy",
        "/affiliate-disclosure",
        "/editorial-policy",
        "/supplier-partnerships",
        "/network-readiness",
        "/corporate-wine-gifts",
        "/corporate-wine-tasting-events",
        "/client-wine-gifts",
        "/staff-wine-gifts",
        "/corporate-christmas-wine-gifts",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "404" not in response.text


def test_required_affiliate_ready_guides_load():
    guide_paths = [
        "/guides/best-client-wine-gifts",
        "/guides/corporate-wine-gifts-uk",
        "/guides/best-wine-gifts-under-25",
        "/guides/best-wine-gifts-under-50",
        "/guides/best-wine-gifts-under-100",
        "/guides/champagne-gifts-for-clients",
        "/guides/red-wine-gifts-for-clients",
        "/guides/white-wine-gifts-for-clients",
        "/guides/luxury-wine-hampers-uk",
        "/guides/wine-gifts-for-christmas",
        "/guides/wine-gifts-for-thank-you",
        "/guides/wine-gifts-for-new-business",
        "/guides/wine-gifts-for-events",
        "/guides/best-wine-accessories-for-gifts",
        "/guides/how-much-to-spend-on-client-gifts",
        "/guides/client-gifting-etiquette-uk",
        "/guides/food-and-wine-hampers",
        "/guides/non-alcoholic-client-gifts",
        "/guides/personalised-wine-gifts",
        "/guides/wine-gift-baskets-uk",
    ]
    for path in guide_paths:
        response = client.get(path)
        assert response.status_code == 200
        assert "Disclosure: Some links may earn commission" in response.text
        assert "Written by ClientCellar editorial team" in response.text
        assert "Last updated: May 2026" in response.text
        assert "Planning note: ClientCellar provides guidance only" in response.text
        assert "Recommended approach" in response.text
        assert "What to check before ordering" in response.text
        assert "Best use cases" in response.text
        assert "Supplier links to consider" in response.text
        assert "In this guide" not in response.text
        assert "Quick answer" not in response.text


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
        assert "Turn this into a buying brief" in response.text


def test_sitemap_includes_public_seo_and_excludes_checkout_pages():
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    text = response.text
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<lastmod>" in text
    assert "https://www.cv-optimiser.com/" in text
    assert "https://www.cv-optimiser.com/gift-planner" in text
    assert "https://www.cv-optimiser.com/event-planner" in text
    assert "https://www.cv-optimiser.com/guides" in text
    assert "https://www.cv-optimiser.com/suppliers" in text
    assert "https://www.cv-optimiser.com/pricing" in text
    assert "https://www.cv-optimiser.com/faq" in text
    assert "https://www.cv-optimiser.com/about" in text
    assert "https://www.cv-optimiser.com/contact" in text
    assert "https://www.cv-optimiser.com/terms" in text
    assert "clientcellar.co.uk" not in text
    assert "/guides/corporate-wine-gifts-under-50" in text
    assert "/guides/best-client-wine-gifts" in text
    assert "/guides/non-alcoholic-client-gifts" in text
    assert "/guides/corporate-gifting-recipient-csv-template" in text
    assert "/guides/champagne-gifts-for-clients" in text
    assert "/guides/corporate-champagne-gifts" not in text
    assert "/corporate-wine-gifts" in text
    assert "/privacy-policy" in text
    assert "/privacy</loc>" not in text
    assert "/editorial-policy" in text
    assert "/supplier-partnerships" in text
    assert "/network-readiness" not in text
    assert "/suppliers/majestic" not in text
    assert "/checkout/success" not in text
    assert "/billing/success" not in text
    assert "/admin" not in text


def test_robots_points_to_canonical_sitemap():
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.text == "User-agent: *\nAllow: /\n\nSitemap: https://www.cv-optimiser.com/sitemap.xml\n"


def test_public_pages_self_canonicalise_to_www_cv_optimiser_without_query_or_trailing_slash():
    response = client.get("/gift-planner?utm_source=test")
    assert response.status_code == 200
    assert response.text.count('rel="canonical"') == 1
    assert '<link rel="canonical" href="https://www.cv-optimiser.com/gift-planner" />' in response.text
    assert "utm_source" not in response.text


def test_root_host_render_host_and_trailing_slash_redirect_to_canonical_domain():
    root_response = client.get("https://cv-optimiser.com/gift-planner", follow_redirects=False)
    assert root_response.status_code == 301
    assert root_response.headers["location"] == "https://www.cv-optimiser.com/gift-planner"

    render_response = client.get("https://clientcellar.onrender.com/guides?x=1", follow_redirects=False)
    assert render_response.status_code == 301
    assert render_response.headers["location"] == "https://www.cv-optimiser.com/guides?x=1"

    slash_response = client.get("/gift-planner/", follow_redirects=False)
    assert slash_response.status_code == 301
    assert slash_response.headers["location"] == "https://www.cv-optimiser.com/gift-planner"


def test_legacy_champagne_guide_redirects_to_canonical_url():
    response = client.get("/guides/corporate-champagne-gifts", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/guides/champagne-gifts-for-clients"


def test_checkout_pages_are_noindex():
    response = client.get("/checkout/success")
    assert response.status_code == 200
    assert 'name="robots" content="noindex, nofollow"' in response.text


def test_homepage_has_structured_data_and_conversion_links():
    response = client.get("/")
    assert response.status_code == 200
    assert 'application/ld+json' in response.text
    assert "Free plan first. Upgrade only if you need copy-ready business documents." in response.text
    assert "ClientCellar provides planning guidance and supplier direction only" in response.text
    assert "Plan corporate gifts" in response.text
    assert "Plan a tasting event" in response.text


def test_supplier_page_has_trust_sections():
    response = client.get("/suppliers")
    assert response.status_code == 200
    assert "Some supplier links may be affiliate or tracked links" in response.text
    assert "Supplier categories" in response.text
    assert "Important checks before ordering" in response.text
    assert "Champagne and sparkling wine retailers" in response.text


def test_public_pages_use_clientcellar_business_emails():
    pages = [
        "/contact",
        "/about",
        "/supplier-partnerships",
        "/editorial-policy",
        "/network-readiness",
    ]
    combined = ""
    for path in pages:
        response = client.get(path)
        assert response.status_code == 200
        combined += response.text

    assert "hello@clientcellar.co.uk" in combined
    assert "partners@clientcellar.co.uk" in combined
    assert "parters@clientcellar.co.uk" not in combined


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
    assert data["supplier_shortlist"]
    assert data["suppliers"] == data["supplier_shortlist"]
    assert data["supplier_recommendations"] == data["supplier_shortlist"]
    assert data["suggested_suppliers"] == data["supplier_shortlist"]
    assert data["supplier_shortlist"][0]["tracked_url"].startswith("/out/supplier/")
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
    assert data["supplier_shortlist"]
    assert data["suppliers"] == data["supplier_shortlist"]
    assert data["supplier_recommendations"] == data["supplier_shortlist"]
    assert data["suggested_suppliers"] == data["supplier_shortlist"]
    assert data["supplier_shortlist"][0]["tracked_url"].startswith("/out/supplier/")
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


def test_checkout_blocks_purchase_without_generated_plan(monkeypatch):
    monkeypatch.setattr(main, "payments_enabled", lambda: True)

    response = client.post("/api/create-checkout-session", json={"pack_type": "gift"})

    assert response.status_code == 400
    assert response.json()["redirect_url"] == "/gift-planner?message=create-plan-first"
    assert "Create a free plan first" in response.text


def test_checkout_allows_one_off_purchase_without_login_after_plan(monkeypatch):
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

    response = client.post(
        "/api/create-checkout-session",
        json={
            "pack_type": "gift",
            "email": "buyer@example.com",
            "planner_input": {"recipient_count": 10, "budget_per_recipient": 50},
            "planner_output": {"headline": "Gift plan", "supplier_category": "Wine merchant"},
        },
    )
    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.test/session"
    assert captured["metadata"]["supabase_user_id"] == ""
    assert captured["metadata"]["plan_id"] == "pack_no_user"
    assert captured["client_reference_id"] == "pack_no_user"
    assert captured["payment_intent_data"]["metadata"]["supabase_user_id"] == ""


def test_checkout_requires_email_with_generated_plan(monkeypatch):
    monkeypatch.setattr(main, "payments_enabled", lambda: True)
    monkeypatch.setattr(main, "verify_supabase_access_token", lambda token: None)

    response = client.post(
        "/api/create-checkout-session",
        json={
            "pack_type": "gift",
            "planner_input": {"recipient_count": 10, "budget_per_recipient": 50},
            "planner_output": {"headline": "Gift plan", "supplier_category": "Wine merchant"},
        },
    )

    assert response.status_code == 400
    assert response.json()["requires_email"] is True
    assert "Please enter an email before checkout" in response.text


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
        json={
            "pack_type": "gift",
            "planner_input": {"recipient_count": 10, "budget_per_recipient": 50},
            "planner_output": {"headline": "Gift plan", "supplier_category": "Wine merchant"},
        },
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
    assert captured["metadata"]["plan_id"] == "pack_123"
    assert captured["client_reference_id"] == "pack_123"
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
