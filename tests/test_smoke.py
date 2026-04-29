import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
