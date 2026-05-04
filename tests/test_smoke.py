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
    assert "supplier_shortlist" in response.json()


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
    assert "event_structure" in response.json()


def test_premium_status_defaults_to_free():
    response = client.get("/api/premium-status")
    assert response.status_code == 200
    data = response.json()
    assert data["loggedIn"] is False
    assert data["authenticated"] is False
    assert data["plan"] == "free"
    assert data["isPremium"] is False
    assert data["premium"] is False


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
    assert "Premium features require an account" in response.text
