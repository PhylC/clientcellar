import json
import re
import sys
from pathlib import Path
from html.parser import HTMLParser

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from data.supplier_links import getSupplierLink, validate_supplier_links
from main import app


client = TestClient(app)


class GuideIntentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.in_grid = False
        self.grid_parent_is_paragraph = False
        self.card_count = 0
        self.labels: list[str] = []
        self._capture_label = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        classes = (dict(attrs).get("class") or "").split()
        if "guide-intent-grid" in classes:
            self.in_grid = True
            self.grid_parent_is_paragraph = any(item == "p" for item in self.stack)
        if self.in_grid and tag == "a" and "guide-intent-card" in classes:
            self.card_count += 1
        if self.in_grid and tag == "strong":
            self._capture_label = True
        self.stack.append(tag)

    def handle_endtag(self, tag: str):
        if tag == "strong":
            self._capture_label = False
        if self.stack:
            self.stack.pop()
        if self.in_grid and tag == "div" and not any(item == "a" for item in self.stack):
            self.in_grid = False

    def handle_data(self, data: str):
        if self._capture_label:
            label = data.strip()
            if label:
                self.labels.append(label)


def structured_data_items(html: str) -> list[dict]:
    return [
        json.loads(match.group(1))
        for match in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            flags=re.DOTALL,
        )
    ]


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
    assert "Your recommendation" in response.text
    assert "Why this recommendation?" in response.text
    assert "Detailed supplier notes" in response.text
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
        "/guides/christmas-corporate-wine-gifts",
        "/guides/wine-gift-hampers-uk",
        "/guides/corporate-gift-ideas-for-clients",
        "/guides/wine-gifts-for-customers",
        "/guides/luxury-corporate-wine-gifts",
        "/guides/client-thank-you-wine-gifts",
        "/guides/business-gift-wine-etiquette",
        "/guides/corporate-event-wine-planning",
        "/guides/champagne-gifts-for-clients",
        "/guides/red-wine-gifts-for-clients",
        "/guides/white-wine-gifts-for-clients",
        "/guides/luxury-wine-hampers-uk",
        "/guides/wine-gifts-for-new-business",
        "/guides/wine-gifts-for-events",
        "/guides/best-wine-accessories-for-gifts",
        "/guides/how-much-to-spend-on-client-gifts",
        "/guides/client-gifting-etiquette-uk",
        "/guides/food-and-wine-hampers",
        "/guides/non-alcoholic-client-gifts",
        "/guides/personalised-wine-gifts",
    ]
    enhanced_paths = {
        f"/guides/{slug}"
        for slug, guide in main.GUIDES.items()
        if guide.get("enhanced")
    }
    for path in guide_paths:
        response = client.get(path)
        assert response.status_code == 200
        assert "Disclosure: Some links may earn commission" in response.text
        assert "Written by ClientCellar editorial team" in response.text
        assert "Last updated: May 2026" in response.text
        assert "Planning note: ClientCellar provides guidance only" in response.text
        if path in enhanced_paths:
            assert "ClientCellar guide" in response.text
            assert "guide-opening-section" in response.text
            assert "Quick answer" not in response.text
            assert "guide-quick-answer" not in response.text
            assert "Best fit comparison" in response.text
            assert "Supplier routes to consider" in response.text
            assert "Editorial policy" in response.text
            assert "<built-in method copy" not in response.text
            assert "dict object" not in response.text
            assert "<svg" not in response.text
            assert "guide-article-image" not in response.text
        else:
            assert "Recommended approach" in response.text
            assert "What to check before ordering" in response.text
            assert "Best use cases" in response.text
            assert "Supplier links to consider" in response.text
        assert "In this guide" not in response.text


def test_duplicate_seo_urls_redirect_permanently():
    redirect_client = TestClient(app, follow_redirects=False)
    redirects = {
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
    for source, destination in redirects.items():
        response = redirect_client.get(source)
        assert response.status_code == 301
        assert response.headers["location"] == f"https://clientcellar.co.uk{destination}"


def test_guides_start_here_renders_as_structured_cards():
    response = client.get("/guides")
    assert response.status_code == 200
    assert "guide-start-section" in response.text
    assert "guide-intent-grid" in response.text

    parser = GuideIntentParser()
    parser.feed(response.text)

    expected_labels = [
        "I need a client gift",
        "I am planning Christmas gifts",
        "I have a fixed budget",
        "I am buying for a team",
        "I am planning an event",
        "I need etiquette advice",
    ]
    assert parser.card_count == 6
    assert parser.labels == expected_labels
    assert parser.grid_parent_is_paragraph is False

    inline_blob = re.compile(
        r"I need a client gift\\s+Start here if.*I am planning Christmas gifts",
        flags=re.DOTALL,
    )
    assert not inline_blob.search(response.text)


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
        assert "ClientCellar guide" in response.text
        assert "guide-opening-section" in response.text
        assert "Supplier routes to consider" in response.text


def test_enhanced_guides_render_editorial_blocks_without_placeholder_images():
    message_expectations = {
        "/guides/corporate-wine-gifts-uk": "Please accept this gift as a token of our appreciation.",
        "/guides/client-wine-gifts": "Thank you again for the energy and clarity your team brought to the project.",
        "/guides/christmas-corporate-wine-gifts": "Thank you for your partnership this year.",
    }
    for path in [
        "/guides/corporate-wine-gifts-uk",
        "/guides/best-wine-gifts-under-50",
        "/guides/christmas-corporate-wine-gifts",
        "/guides/wine-gift-hampers-uk",
        "/guides/best-client-wine-gifts",
        "/guides/best-wine-gifts-under-25",
        "/guides/best-wine-gifts-under-100",
        "/guides/corporate-gift-ideas-for-clients",
        "/guides/wine-gifts-for-customers",
        "/guides/luxury-corporate-wine-gifts",
        "/guides/client-thank-you-wine-gifts",
        "/guides/business-gift-wine-etiquette",
        "/guides/corporate-event-wine-planning",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "guide-best-fit-summary" in response.text
        assert "guide-opening-section" in response.text
        assert "Quick answer" not in response.text
        assert "guide-quick-answer" not in response.text
        assert "<built-in method copy" not in response.text
        assert "dict object" not in response.text
        assert "<svg" not in response.text
        assert "guide-article-image" not in response.text
        if path in message_expectations:
            assert message_expectations[path] in response.text


def test_guide_faq_sections_include_matching_faq_schema():
    response = client.get("/guides/corporate-wine-gifts-uk")
    assert response.status_code == 200
    assert "FAQs" in response.text
    assert "What is a good corporate wine gift in the UK?" in response.text

    faq_schemas = [
        item
        for item in structured_data_items(response.text)
        if item.get("@type") == "FAQPage"
    ]

    assert len(faq_schemas) == 1
    questions = [item["name"] for item in faq_schemas[0]["mainEntity"]]
    answers = [item["acceptedAnswer"]["text"] for item in faq_schemas[0]["mainEntity"]]
    assert "What is a good corporate wine gift in the UK?" in questions
    assert "How much should I spend on a client wine gift?" in questions
    assert "Should I send one bottle or a case?" in questions
    assert all(answer in response.text for answer in answers)
    assert not any("review" in json.dumps(item).lower() or "rating" in json.dumps(item).lower() for item in faq_schemas)


def test_seo_landing_faq_sections_include_matching_faq_schema():
    response = client.get("/corporate-wine-gifts")
    assert response.status_code == 200
    assert "Common questions" in response.text

    faq_schemas = [
        item
        for item in structured_data_items(response.text)
        if item.get("@type") == "FAQPage"
    ]

    assert len(faq_schemas) == 1
    questions = [item["name"] for item in faq_schemas[0]["mainEntity"]]
    answers = [item["acceptedAnswer"]["text"] for item in faq_schemas[0]["mainEntity"]]
    assert "What is a sensible budget for corporate wine gifts?" in questions
    assert "Does ClientCellar sell the wine?" in questions
    assert all(question in response.text for question in questions)
    assert all(answer in response.text for answer in answers)
    assert not any("review" in json.dumps(item).lower() or "rating" in json.dumps(item).lower() for item in faq_schemas)


def test_sitemap_includes_public_seo_and_excludes_checkout_pages():
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    text = response.text
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<lastmod>" in text
    assert "https://clientcellar.co.uk/" in text
    assert "https://clientcellar.co.uk/gift-planner" in text
    assert "https://clientcellar.co.uk/event-planner" in text
    assert "https://clientcellar.co.uk/guides" in text
    assert "https://clientcellar.co.uk/suppliers" in text
    assert "https://clientcellar.co.uk/supplier-directory" in text
    assert "https://clientcellar.co.uk/uk-wine-gift-suppliers" not in text
    assert "https://clientcellar.co.uk/pricing" in text
    assert "https://clientcellar.co.uk/faq" in text
    assert "https://clientcellar.co.uk/about" in text
    assert "https://clientcellar.co.uk/contact" not in text
    assert "https://clientcellar.co.uk/terms" in text
    assert "www.clientcellar.co.uk" not in text
    assert "cv-optimiser.com" not in text
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
    assert response.text == "User-agent: *\nAllow: /\n\nSitemap: https://clientcellar.co.uk/sitemap.xml\n"


def test_supplier_link_config_covers_major_visible_suppliers():
    assert validate_supplier_links() == []
    for supplier_id in [
        "virgin-wines",
        "marks-spencer-corporate",
        "fortnum-mason",
        "john-lewis-hampers",
        "selfridges-hampers",
        "harrods-hampers",
        "majestic",
        "laithwaites",
        "hotel-chocolat",
        "amazon",
        "slurp",
        "hay-wines",
        "wine-direct",
        "great-wine-co",
    ]:
        link = getSupplierLink(supplier_id)
        assert link is not None
        assert link.canonical_base_url.startswith("https://")
        assert link.url is None or link.url.startswith("https://")


def test_public_pages_self_canonicalise_to_clientcellar_without_query_or_trailing_slash():
    response = client.get("/gift-planner?utm_source=test")
    assert response.status_code == 200
    assert response.text.count('rel="canonical"') == 1
    assert '<link rel="canonical" href="https://clientcellar.co.uk/gift-planner" />' in response.text
    assert "utm_source" not in response.text


def test_http_www_render_host_and_trailing_slash_redirect_to_canonical_domain_once():
    root_http_response = client.get("http://clientcellar.co.uk", follow_redirects=False)
    assert root_http_response.status_code == 301
    assert root_http_response.headers["location"] == "https://clientcellar.co.uk/"

    root_https_www_response = client.get("https://www.clientcellar.co.uk", follow_redirects=False)
    assert root_https_www_response.status_code == 301
    assert root_https_www_response.headers["location"] == "https://clientcellar.co.uk/"

    root_http_www_response = client.get("http://www.clientcellar.co.uk", follow_redirects=False)
    assert root_http_www_response.status_code == 301
    assert root_http_www_response.headers["location"] == "https://clientcellar.co.uk/"

    http_response = client.get("http://clientcellar.co.uk/gift-planner", follow_redirects=False)
    assert http_response.status_code == 301
    assert http_response.headers["location"] == "https://clientcellar.co.uk/gift-planner"

    www_response = client.get("https://www.clientcellar.co.uk/gift-planner", follow_redirects=False)
    assert www_response.status_code == 301
    assert www_response.headers["location"] == "https://clientcellar.co.uk/gift-planner"

    render_response = client.get("https://clientcellar.onrender.com/guides?x=1", follow_redirects=False)
    assert render_response.status_code == 301
    assert render_response.headers["location"] == "https://clientcellar.co.uk/guides?x=1"

    slash_response = client.get("https://clientcellar.co.uk/gift-planner/", follow_redirects=False)
    assert slash_response.status_code == 301
    assert slash_response.headers["location"] == "https://clientcellar.co.uk/gift-planner"

    combined_response = client.get("http://www.clientcellar.co.uk/gift-planner/?x=1", follow_redirects=False)
    assert combined_response.status_code == 301
    assert combined_response.headers["location"] == "https://clientcellar.co.uk/gift-planner?x=1"

    canonical_response = client.get("https://clientcellar.co.uk/gift-planner", follow_redirects=False)
    assert canonical_response.status_code == 200


def test_proxy_headers_redirect_www_http_to_canonical_in_one_hop():
    response = client.get(
        "http://internal-render-host/gift-planner/?utm_source=test",
        headers={"x-forwarded-host": "www.clientcellar.co.uk", "x-forwarded-proto": "http"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://clientcellar.co.uk/gift-planner?utm_source=test"

    forwarded_response = client.get(
        "http://internal-render-host/pricing/",
        headers={"forwarded": 'for=203.0.113.1;proto=http;host="www.clientcellar.co.uk"'},
        follow_redirects=False,
    )
    assert forwarded_response.status_code == 301
    assert forwarded_response.headers["location"] == "https://clientcellar.co.uk/pricing"


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
    assert "Better wine gifts and event drinks, without the guesswork" in response.text
    assert "/images/clientcellar/homepage-wine-gift-hero.webp" in response.text
    assert "Corporate wine gift box with bottle, glass and thank-you card" in response.text
    assert "ClientCellar recommendations are editorially selected" in response.text
    assert "Plan a client gift" in response.text
    assert "Plan event drinks" in response.text
    assert "/supplier-directory" in response.text
    assert "Popular guides" in response.text
    assert "Need a more detailed shortlist?" in response.text


def test_supplier_page_has_trust_sections():
    response = client.get("/suppliers")
    assert response.status_code == 200
    assert "Some supplier links may become affiliate" in response.text
    assert "Supplier categories" in response.text
    assert "Important checks before ordering" in response.text
    assert "Champagne and sparkling wine retailers" in response.text


def test_supplier_directory_page_is_editorial_and_affiliate_ready():
    response = client.get("/supplier-directory")
    assert response.status_code == 200
    assert "UK wine gift supplier directory" in response.text
    assert "How this directory works" in response.text
    assert "Listings are editorially selected" in response.text
    assert "View Majestic corporate gifting" in response.text
    assert "View Virgin Wines corporate gifting" in response.text
    assert "View Wine Direct corporate gifts" in response.text
    assert 'data-supplier-directory' in response.text
    assert 'data-supplier-card' in response.text
    assert "/images/clientcellar/supplier-corporate-gifts.webp" in response.text
    assert "/images/clientcellar/supplier-premium-hampers.webp" in response.text
    assert 'rel="noopener noreferrer sponsored"' in response.text
    assert "Official partner" not in response.text

    item_lists = [item for item in structured_data_items(response.text) if item.get("@type") == "ItemList"]
    assert len(item_lists) == 1
    names = [item["name"] for item in item_lists[0]["itemListElement"]]
    assert "Majestic" in names
    assert "Great Wine Co." in names


def test_supplier_directory_aliases_redirect_to_canonical_page():
    for path in ["/uk-wine-gift-suppliers", "/wine-gift-suppliers-uk"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/supplier-directory"


def test_clientcellar_image_assets_are_served_and_used_on_key_pages():
    for path in [
        "/images/clientcellar/homepage-wine-gift-hero.webp",
        "/images/clientcellar/gift-planner-header.webp",
        "/images/clientcellar/event-planner-header.webp",
        "/images/clientcellar/premium-brief-example.webp",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"] in {"image/webp", "image/webp; charset=utf-8"}

    gift = client.get("/gift-planner").text
    event = client.get("/event-planner").text
    guides = client.get("/guides").text
    example = client.get("/example-premium-brief-pack").text
    assert "/images/clientcellar/gift-planner-header.webp" in gift
    assert "Wine gift box with ribbon and thank-you card" in gift
    assert "/images/clientcellar/event-planner-header.webp" in event
    assert "Wine glasses on a business dinner table" in event
    assert "/images/clientcellar/guides/corporate-wine-gifts-uk.webp" in guides
    assert "/images/clientcellar/guides/best-wine-gifts-under-50.webp" in guides
    assert "/images/clientcellar/premium-brief-example.webp" in example


def test_guide_detail_pages_use_mapped_hero_images():
    examples = [
        (
            "/guides/corporate-wine-gifts-uk",
            "/images/clientcellar/guides/corporate-wine-gifts-uk.webp",
            "Wine bottle and gift box for corporate gifting",
        ),
        (
            "/guides/best-wine-gifts-under-50",
            "/images/clientcellar/guides/best-wine-gifts-under-50.webp",
            "Simple wine gift setup for budget-friendly client gifting",
        ),
        (
            "/guides/christmas-corporate-wine-gifts",
            "/images/clientcellar/guides/christmas-corporate-wine-gifts.webp",
            "Festive wine gift hamper for client Christmas gifts",
        ),
        (
            "/guides/corporate-event-wine-planning",
            "/images/clientcellar/guides/corporate-event-wine-planning.webp",
            "Wine glasses on a table for event drinks planning",
        ),
        (
            "/guides/champagne-gifts-for-clients",
            "/images/clientcellar/guides/champagne-gifts-for-clients.webp",
            "Champagne bottle in an ice bucket for client gifting",
        ),
    ]

    for path, image, alt in examples:
        response = client.get(path)
        assert response.status_code == 200
        assert "guide-hero-inner" in response.text
        assert "guide-hero__visual" in response.text
        assert image in response.text
        assert alt in response.text


def test_related_guide_cards_include_thumbnails():
    guide_response = client.get("/guides/corporate-wine-gifts-uk")
    assert guide_response.status_code == 200
    assert "related-guide-thumb" in guide_response.text
    assert "/images/clientcellar/guides/best-client-wine-gifts.webp" in guide_response.text

    seo_response = client.get("/client-christmas-gifts-uk")
    assert seo_response.status_code == 200
    assert "related-guide-thumb" in seo_response.text
    assert "/images/clientcellar/guides/christmas-corporate-wine-gifts.webp" in seo_response.text


def test_clientcellar_brand_assets_are_served_and_referenced():
    for path, content_type in [
        ("/images/clientcellar/clientcellar-logo-lockup-360.webp", "image/webp"),
        ("/images/clientcellar/clientcellar-logo-lockup-280.webp", "image/webp"),
        ("/images/clientcellar/clientcellar-icon.webp", "image/webp"),
        ("/images/clientcellar/favicon-32x32.png", "image/png"),
        ("/images/clientcellar/favicon-48x48.png", "image/png"),
        ("/images/clientcellar/apple-touch-icon.png", "image/png"),
        ("/images/clientcellar/icon-192x192.png", "image/png"),
        ("/images/clientcellar/icon-512x512.png", "image/png"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].split(";")[0] == content_type

    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "/images/clientcellar/clientcellar-logo-lockup-360.webp" in html
    assert "/images/clientcellar/clientcellar-logo-lockup-280.webp" in html
    assert "/images/clientcellar/clientcellar-icon.webp" in html
    assert 'alt="ClientCellar"' in html
    assert 'alt="ClientCellar logo"' in html
    assert 'rel="icon" type="image/png" sizes="32x32"' in html
    assert 'rel="apple-touch-icon" sizes="180x180"' in html
    assert 'property="og:site_name" content="ClientCellar"' in html
    assert 'property="og:image" content="https://clientcellar.co.uk/images/clientcellar/clientcellar-logo-lockup.webp"' in html


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
    assert "Premium Brief Pack support" in client.get("/contact").text
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
