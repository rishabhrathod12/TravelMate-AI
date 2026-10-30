"""The booking API end to end on mock providers (no network, no key). Booking stays switched off."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_booking_service import API, COMPLETE, InlineExecutor

from app.config import Settings
from app.main import create_app

KEY = "key-0000001"


def make_world(**overrides: Any) -> tuple[TestClient, str, dict[str, Any]]:
    http = TestClient(
        create_app(Settings.model_validate({**API, **overrides}), executor=InlineExecutor())
    )
    trip_id = http.post(
        "/api/v1/trips", json={"title": "Goa", "draft": COMPLETE, "rooms": 1}
    ).json()["id"]
    run = http.post(f"/api/v1/trips/{trip_id}/runs").json()
    waiting = run["waiting_for"]
    http.post(
        f"/api/v1/runs/{run['run_id']}/selections",
        json={
            "transport_id": waiting["transport"][0],
            "return_transport_id": waiting["return_transport"][0],
            "hotel_id": waiting["hotels"][0],
        },
    )
    return http, trip_id, waiting


def create(http: TestClient, trip_id: str, waiting: dict[str, Any], key: str = KEY) -> Any:
    return http.post(
        f"/api/v1/trips/{trip_id}/booking-intents",
        json={
            "category": "TRANSPORT",
            "option_id": waiting["transport"][0],
            "idempotency_key": key,
        },
    )


class TestTheFlow:
    def test_create_read_approve_and_the_refused_execute(self) -> None:
        http, trip_id, waiting = make_world()

        created = create(http, trip_id, waiting)
        assert created.status_code == 201, created.text
        intent = created.json()
        assert intent["status"] == "AWAITING_APPROVAL"
        assert intent["quote"]["source"]["provenance"] == "MOCK"
        assert intent["booking_enabled"] is False and "does not book" in intent["notice"]

        shown = http.get(f"/api/v1/booking-intents/{intent['id']}")
        assert (
            shown.status_code == 200
            and shown.json()["quote_content_hash"] == intent["quote_content_hash"]
        )

        approved = http.post(
            f"/api/v1/booking-intents/{intent['id']}/approvals",
            json={"quote_content_hash": intent["quote_content_hash"]},
        )
        assert approved.status_code == 201, approved.text
        body = approved.json()
        assert body["status"] == "APPROVED" and body["approval"]["expires_at"]

        refused = http.post(f"/api/v1/booking-intents/{intent['id']}/execute")
        assert refused.status_code == 409
        assert refused.headers["content-type"].startswith("application/problem+json")
        assert refused.json()["code"] == "booking_disabled"
        again = http.get(f"/api/v1/booking-intents/{intent['id']}").json()
        assert again["status"] == "APPROVED"

    def test_the_same_request_again_is_200_with_the_first_intent(self) -> None:
        http, trip_id, waiting = make_world()

        first = create(http, trip_id, waiting)
        again = create(http, trip_id, waiting)

        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json()["id"] == first.json()["id"]

    def test_a_reused_key_for_another_request_is_409(self) -> None:
        http, trip_id, waiting = make_world()
        create(http, trip_id, waiting)

        other = http.post(
            f"/api/v1/trips/{trip_id}/booking-intents",
            json={
                "category": "HOTEL",
                "option_id": waiting["hotels"][0],
                "idempotency_key": KEY,
            },
        )

        assert other.status_code == 409 and other.json()["code"] == "idempotency_conflict"

    def test_the_wrong_hash_is_409_and_approves_nothing(self) -> None:
        http, trip_id, waiting = make_world()
        intent = create(http, trip_id, waiting).json()

        refused = http.post(
            f"/api/v1/booking-intents/{intent['id']}/approvals",
            json={"quote_content_hash": "0" * 64},
        )

        assert refused.status_code == 409 and refused.json()["code"] == "quote_mismatch"
        assert http.get(f"/api/v1/booking-intents/{intent['id']}").json()["approval"] is None

    def test_a_malformed_hash_is_422(self) -> None:
        http, trip_id, waiting = make_world()
        intent = create(http, trip_id, waiting).json()

        bad = http.post(
            f"/api/v1/booking-intents/{intent['id']}/approvals", json={"quote_content_hash": "x"}
        )

        assert bad.status_code == 422

    def test_a_short_key_is_422(self) -> None:
        http, trip_id, waiting = make_world()

        assert create(http, trip_id, waiting, key="short").status_code == 422

    def test_an_unknown_intent_and_an_unknown_option_are_refused_in_plain_words(self) -> None:
        http, trip_id, _ = make_world()

        missing = http.get("/api/v1/booking-intents/nope")
        unknown = http.post(
            f"/api/v1/trips/{trip_id}/booking-intents",
            json={"category": "TRANSPORT", "option_id": "zzz", "idempotency_key": KEY},
        )

        assert missing.status_code == 404 and missing.json()["code"] == "intent_not_found"
        assert unknown.status_code == 422 and unknown.json()["code"] == "option_not_quotable"
        assert "zzz" not in unknown.text  # fixed wording; the caller text is never echoed

    def test_a_trip_without_research_cannot_be_quoted(self) -> None:
        http = TestClient(create_app(Settings.model_validate(API), executor=InlineExecutor()))
        trip_id = http.post(
            "/api/v1/trips", json={"title": "Goa", "draft": COMPLETE, "rooms": 1}
        ).json()["id"]

        response = http.post(
            f"/api/v1/trips/{trip_id}/booking-intents",
            json={"category": "TRANSPORT", "option_id": "x", "idempotency_key": KEY},
        )

        assert response.status_code == 409 and response.json()["code"] == "no_research"


class TestNoPaymentAnywhere:
    def test_there_is_no_payment_route_and_booking_cannot_be_switched_on(self) -> None:
        http, _, _ = make_world()
        paths = " ".join(http.get("/openapi.json").json()["paths"]).lower()

        assert not any(word in paths for word in ("pay", "charge", "card", "refund"))
        with pytest.raises(ValidationError):
            Settings.model_validate({**API, "booking_enabled": True})

    def test_booking_routes_exist_only_with_the_api(self) -> None:
        http = TestClient(create_app(Settings()))

        paths = http.get("/openapi.json").json()["paths"]

        assert not any("booking" in path for path in paths)
