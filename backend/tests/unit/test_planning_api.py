"""The planning API end to end on mock providers and a scripted model (no network, no key).

Covers every M8 endpoint, Problem Details errors, ownership, the background run with polling, the
limits and the settings guards. Runs execute inline unless a test says otherwise, so results are
immediate and the tests never sleep.
"""

import time
from concurrent.futures import Executor, Future
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.planning import get_principal
from app.config import Settings
from app.main import create_app
from app.workflow.tracing import ThirdPartyTracingEnabled

API: dict[str, Any] = {
    "api_enabled": True,
    "api_dev_principal": "dev-1",
    "api_currency": "INR",
    "api_run_max_steps": 60,
    "api_run_max_tool_calls": 12,
    "api_run_max_human_rounds": 8,
    "api_max_runs_per_hour_per_owner": 5,
}
COMPLETE = {
    "origin": "Indore",
    "destination": "Goa",
    "trip_type": "ROUND_TRIP",
    "departure_date": "2026-12-01",
    "return_date": "2026-12-05",
    "traveller_count": 2,
}
SECRET = "sk-FAKE-secret-value-1234567890"


class InlineExecutor(Executor):
    """Runs work at once, in the caller's thread."""

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:  # a test double: hand the failure to the future
            future.set_exception(error)
        return future


class IdleExecutor(Executor):
    """Accepts work and never runs it, so a run stays 'running'."""

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        return Future()


def client_for(executor: Executor | None = None, **overrides: Any) -> TestClient:
    app = create_app(
        Settings.model_validate({**API, **overrides}),
        executor=executor if executor is not None else InlineExecutor(),
    )
    return TestClient(app)


def make_trip(http: TestClient, draft: dict[str, Any] | None = None, rooms: int | None = 1) -> str:
    response = http.post(
        "/api/v1/trips",
        json={"title": "Goa trip", "draft": COMPLETE if draft is None else draft, "rooms": rooms},
    )
    assert response.status_code == 201, response.text
    trip_id: str = response.json()["id"]
    return trip_id


def start(http: TestClient, trip_id: str) -> dict[str, Any]:
    response = http.post(f"/api/v1/trips/{trip_id}/runs")
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


def choice(run: dict[str, Any]) -> dict[str, Any]:
    waiting = run["waiting_for"]
    return {
        "transport_id": waiting["transport"][0],
        "return_transport_id": waiting["return_transport"][0],
        "hotel_id": waiting["hotels"][0],
    }


class TestSwitchedOffByDefault:
    def test_a_normal_start_has_no_planning_routes_but_still_has_request_ids(self) -> None:
        http = TestClient(create_app(Settings()))

        assert http.post("/api/v1/trips", json={}).status_code == 404
        assert not any("/trips" in path for path in http.get("/openapi.json").json()["paths"])
        health = http.get("/health")
        assert health.status_code == 200
        assert len(health.headers["X-Request-ID"]) >= 8

    def test_the_api_cannot_start_in_production(self) -> None:
        with pytest.raises(ValidationError, match="production"):
            Settings.model_validate({**API, "app_env": "production"})

    @pytest.mark.parametrize(
        "missing",
        [
            "api_dev_principal",
            "api_currency",
            "api_run_max_steps",
            "api_run_max_tool_calls",
            "api_run_max_human_rounds",
            "api_max_runs_per_hour_per_owner",
        ],
    )
    def test_every_setting_is_required_when_the_api_is_on(self, missing: str) -> None:
        values = {k: v for k, v in API.items() if k != missing}

        with pytest.raises(ValidationError):
            Settings.model_validate(values)

    def test_a_bad_currency_and_a_zero_limit_are_refused(self) -> None:
        for bad in ({"api_currency": "RS"}, {"api_run_max_steps": 0}, {"api_dev_principal": " "}):
            with pytest.raises(ValidationError):
                Settings.model_validate({**API, **bad})

    def test_tracing_switched_on_stops_the_app_starting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGSMITH_TRACING", "true")

        with pytest.raises(ThirdPartyTracingEnabled):
            create_app(Settings.model_validate(API), executor=InlineExecutor())


class TestTheFullFlow:
    def test_trip_run_selection_itinerary_and_cost_estimate(self) -> None:
        http = client_for()

        trip_id = make_trip(http)
        run = start(http, trip_id)
        assert run["trip_id"] == trip_id
        assert run["status"] == "awaiting_selection"

        read = http.get(f"/api/v1/runs/{run['run_id']}").json()
        research = read["research"]
        assert research["transport"]["options"] and research["return_transport"]["options"]
        assert research["hotels"]["options"] and research["weather"]["forecast"]["days"]
        assert read["provider_calls"] == 4 and read["llm_calls"] == 0

        chosen = http.post(f"/api/v1/runs/{run['run_id']}/selections", json=choice(run))
        assert chosen.status_code == 202
        done = http.get(f"/api/v1/runs/{run['run_id']}").json()
        assert done["status"] == "completed"
        assert done["summary"]["itinerary"] is not None and done["errors"] == []

        estimate = http.get(f"/api/v1/runs/{run['run_id']}/cost-estimate")
        assert estimate.status_code == 200
        body = estimate.json()
        assert body["provenance"] == "MOCK"
        assert body["total"]["currency"] == "INR" and body["total"]["amount_minor"] > 0
        assert body["total"]["amount_minor"] == sum(
            line["amount"]["amount_minor"] for line in body["estimate"]["lines"]
        )
        assert body["is_incomplete"] is False

        first = http.get(f"/api/v1/trips/{trip_id}/itinerary").json()
        assert first["version"] == 1 and first["created_by"] == "agent"
        assert [d["day_number"] for d in first["itinerary"]["days"]] == [1, 2, 3, 4, 5]

        edited = first["itinerary"]
        edited["days"][1]["items"][0]["title"] = "My own idea"
        saved = http.post(f"/api/v1/trips/{trip_id}/itinerary/versions", json={"itinerary": edited})
        assert saved.status_code == 201
        assert saved.json()["version"] == 2 and saved.json()["created_by"] == "user"
        assert http.get(f"/api/v1/trips/{trip_id}/itinerary").json()["version"] == 2

        trip = http.get(f"/api/v1/trips/{trip_id}").json()
        assert trip["status"] == "planned" and trip["latest_run_id"] == run["run_id"]
        assert trip["latest_run_status"] == "completed" and trip["itinerary_version"] == 2
        assert trip["selection"]["transport_id"] == choice(run)["transport_id"]

    def test_the_scripted_itinerary_links_day_one_to_the_chosen_options(self) -> None:
        http = client_for()
        run = start(http, make_trip(http))
        http.post(f"/api/v1/runs/{run['run_id']}/selections", json=choice(run))

        done = http.get(f"/api/v1/runs/{run['run_id']}").json()

        day_one = done["summary"]["itinerary"]["days"][0]["items"]
        linked = {item["option_id"] for item in day_one if item["option_id"]}
        assert linked == {choice(run)["transport_id"], choice(run)["hotel_id"]}
        assert "not a model" in done["summary"]["itinerary"]["notes"]

    def test_missing_inputs_ask_questions_and_make_no_provider_call(self) -> None:
        http = client_for()
        run = start(http, make_trip(http, {"origin": "Indore"}))

        assert run["status"] == "awaiting_clarification"
        assert run["waiting_for"]["kind"] == "CLARIFICATION"
        assert "Where would you like to go?" in run["waiting_for"]["questions"]
        assert run["provider_calls"] == 0

        answered = http.post(
            f"/api/v1/runs/{run['run_id']}/clarifications", json={"draft": COMPLETE}
        )
        assert answered.status_code == 202
        assert http.get(f"/api/v1/runs/{run['run_id']}").json()["status"] == "awaiting_selection"

    def test_a_one_way_trip_has_no_hotel_stay(self) -> None:
        http = client_for()
        one_way = {k: v for k, v in COMPLETE.items() if k != "return_date"} | {
            "trip_type": "ONE_WAY"
        }
        run = start(http, make_trip(http, one_way))

        assert run["provider_calls"] == 2
        assert run["waiting_for"]["hotels"] == []

    def test_the_status_of_a_run_that_has_not_finished_is_running(self) -> None:
        http = client_for(IdleExecutor())

        run = start(http, make_trip(http))

        assert run["status"] == "running" and run["waiting_for"] is None
        assert http.get(f"/api/v1/runs/{run['run_id']}").json()["status"] == "running"
        assert http.get(f"/api/v1/runs/{run['run_id']}/cost-estimate").status_code == 409

    def test_starting_a_run_returns_where_to_poll(self) -> None:
        http = client_for()
        trip_id = make_trip(http)

        response = http.post(f"/api/v1/trips/{trip_id}/runs")

        assert response.headers["Location"] == f"/api/v1/runs/{response.json()['run_id']}"


class TestRealBackgroundRuns:
    def test_a_run_started_without_an_inline_executor_finishes_in_the_background(self) -> None:
        app = create_app(Settings.model_validate(API))
        with TestClient(app) as http:
            run = start(http, make_trip(http))
            deadline = time.monotonic() + 10
            status = run["status"]
            while status == "running" and time.monotonic() < deadline:
                time.sleep(0.05)
                status = http.get(f"/api/v1/runs/{run['run_id']}").json()["status"]

            assert status == "awaiting_selection"


class TestWrongState:
    def test_a_selection_while_a_clarification_is_wanted_is_refused(self) -> None:
        http = client_for()
        run = start(http, make_trip(http, {"origin": "Indore"}))

        response = http.post(f"/api/v1/runs/{run['run_id']}/selections", json={})

        assert response.status_code == 409
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_a_clarification_for_a_finished_run_is_refused(self) -> None:
        http = client_for()
        run = start(http, make_trip(http))
        http.post(f"/api/v1/runs/{run['run_id']}/selections", json=choice(run))

        again = http.post(f"/api/v1/runs/{run['run_id']}/clarifications", json={"draft": COMPLETE})

        assert again.status_code == 409

    def test_a_second_answer_to_a_run_that_is_working_is_refused(self) -> None:
        http = client_for(IdleExecutor())
        run = start(http, make_trip(http))

        response = http.post(f"/api/v1/runs/{run['run_id']}/selections", json={})

        assert response.status_code == 409

    def test_a_second_run_on_a_trip_that_is_still_running_is_refused(self) -> None:
        http = client_for(IdleExecutor())
        trip_id = make_trip(http)
        start(http, trip_id)

        assert http.post(f"/api/v1/trips/{trip_id}/runs").status_code == 409

    def test_the_itinerary_before_any_run_is_not_found(self) -> None:
        http = client_for()
        trip_id = make_trip(http)

        response = http.get(f"/api/v1/trips/{trip_id}/itinerary")

        assert response.status_code == 404


class TestOwnership:
    def test_another_person_cannot_see_or_change_a_trip_or_a_run(self) -> None:
        app = create_app(Settings.model_validate(API), executor=InlineExecutor())
        http = TestClient(app)
        trip_id = make_trip(http)
        run = start(http, trip_id)

        app.dependency_overrides[get_principal] = lambda: "someone-else"

        probes: list[tuple[str, str, dict[str, Any] | None]] = [
            ("get", f"/api/v1/trips/{trip_id}", None),
            ("post", f"/api/v1/trips/{trip_id}/runs", None),
            ("get", f"/api/v1/trips/{trip_id}/itinerary", None),
            ("get", f"/api/v1/runs/{run['run_id']}", None),
            ("get", f"/api/v1/runs/{run['run_id']}/cost-estimate", None),
            ("post", f"/api/v1/runs/{run['run_id']}/selections", {}),
            ("post", f"/api/v1/runs/{run['run_id']}/clarifications", {"draft": COMPLETE}),
            ("post", f"/api/v1/trips/{trip_id}/itinerary/versions", {"itinerary": {"days": []}}),
        ]
        for method, url, body in probes:
            response = getattr(http, method)(url, **({"json": body} if body is not None else {}))
            assert response.status_code in (404, 422), (url, response.status_code)
            assert trip_id not in response.text and run["run_id"] not in response.text

    def test_a_missing_trip_and_someone_elses_look_the_same(self) -> None:
        app = create_app(Settings.model_validate(API), executor=InlineExecutor())
        http = TestClient(app)
        trip_id = make_trip(http)
        app.dependency_overrides[get_principal] = lambda: "someone-else"

        theirs = http.get(f"/api/v1/trips/{trip_id}")
        missing = http.get("/api/v1/trips/no-such-trip")

        assert theirs.status_code == missing.status_code == 404
        assert theirs.json()["detail"] == missing.json()["detail"]


class TestProblemDetails:
    def test_an_error_has_the_rfc_9457_shape_and_the_request_id(self) -> None:
        http = client_for()

        response = http.get("/api/v1/trips/no-such-trip", headers={"X-Request-ID": "abcdef123456"})

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert set(body) == {"type", "title", "status", "detail", "request_id"}
        assert body["status"] == 404 and body["request_id"] == "abcdef123456"
        assert response.headers["X-Request-ID"] == "abcdef123456"
        assert "no-such-trip" not in response.text

    def test_a_validation_error_names_the_field_and_not_the_value(self) -> None:
        http = client_for()

        response = http.post(
            "/api/v1/trips",
            json={"title": "t", "draft": {"traveller_count": "abc-secret-value"}},
        )

        assert response.status_code == 422
        body = response.json()
        assert any(e["field"] == "draft.traveller_count" for e in body["errors"])
        assert "abc-secret-value" not in response.text

    def test_unknown_fields_are_refused(self) -> None:
        http = client_for()

        response = http.post("/api/v1/trips", json={"title": "t", "draft": {"booking": "yes"}})

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "body",
        [
            {"title": "", "draft": COMPLETE},
            {"title": "x" * 121, "draft": COMPLETE},
            {"title": "t", "draft": {**COMPLETE, "traveller_count": 10}},
            {"title": "t", "draft": {**COMPLETE, "preferences": "x" * 501}},
            {"title": "t", "draft": {"destination": "Goa", "trip_days": 5}},
            {"title": "t", "draft": COMPLETE, "rooms": 10},
        ],
    )
    def test_a_trip_breaking_the_owners_limits_is_refused(self, body: dict[str, Any]) -> None:
        http = client_for()

        assert http.post("/api/v1/trips", json=body).status_code == 422

    def test_an_unexpected_error_is_a_generic_500_with_no_detail(self) -> None:
        app = create_app(Settings.model_validate(API), executor=InlineExecutor())
        http = TestClient(app, raise_server_exceptions=False)

        def explode() -> Any:
            raise RuntimeError(f"database password is {SECRET}")

        app.state.trip_service.get_trip = lambda *a, **k: explode()

        response = http.get("/api/v1/trips/anything")

        assert response.status_code == 500
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "database" not in response.text and SECRET not in response.text
        assert response.json()["request_id"] == response.headers["X-Request-ID"]

    def test_an_unknown_path_and_a_wrong_method_are_problems_too(self) -> None:
        http = client_for()

        missing = http.get("/api/v1/nope")
        wrong = http.delete("/api/v1/trips")

        assert missing.status_code == 404 and wrong.status_code == 405
        for response in (missing, wrong):
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["request_id"]

    def test_a_request_id_a_caller_supplies_must_be_plain(self) -> None:
        http = client_for()

        unsafe = http.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
        plain = http.get("/health", headers={"X-Request-ID": "caller-id-0001"})

        assert unsafe.headers["X-Request-ID"] != "bad id\nwith newline"
        assert plain.headers["X-Request-ID"] == "caller-id-0001"


class TestLimits:
    def test_the_hourly_run_limit_is_per_owner(self) -> None:
        http = client_for(api_max_runs_per_hour_per_owner=2)
        trips = [make_trip(http) for _ in range(3)]

        statuses = [http.post(f"/api/v1/trips/{t}/runs").status_code for t in trips]

        assert statuses == [202, 202, 429]

    def test_a_run_over_its_tool_call_limit_stops_with_a_reason(self) -> None:
        http = client_for(api_run_max_tool_calls=1)

        run = start(http, make_trip(http))

        assert run["status"] == "stopped_limit"
        assert "tool calls" in run["limit_reason"]
        assert http.get(f"/api/v1/runs/{run['run_id']}/cost-estimate").status_code == 409

    def test_a_run_over_its_step_limit_stops_too(self) -> None:
        http = client_for(api_run_max_steps=2)

        run = start(http, make_trip(http))

        assert run["status"] == "stopped_limit" and "steps" in run["limit_reason"]


class TestSavedItineraries:
    def saved_base(self, http: TestClient) -> tuple[str, dict[str, Any], dict[str, Any]]:
        trip_id = make_trip(http)
        run = start(http, trip_id)
        http.post(f"/api/v1/runs/{run['run_id']}/selections", json=choice(run))
        itinerary = http.get(f"/api/v1/trips/{trip_id}/itinerary").json()["itinerary"]
        return trip_id, run, itinerary

    def post(self, http: TestClient, trip_id: str, itinerary: dict[str, Any]) -> Any:
        return http.post(
            f"/api/v1/trips/{trip_id}/itinerary/versions", json={"itinerary": itinerary}
        )

    def test_gaps_in_the_day_numbers_are_refused(self) -> None:
        http = client_for()
        trip_id, _, itinerary = self.saved_base(http)
        itinerary["days"][2]["day_number"] = 9

        assert self.post(http, trip_id, itinerary).status_code == 422

    def test_a_reference_to_an_option_that_is_not_in_the_run_is_refused(self) -> None:
        http = client_for()
        trip_id, _, itinerary = self.saved_base(http)
        itinerary["days"][0]["items"][0]["option_id"] = "invented-option"

        response = self.post(http, trip_id, itinerary)

        assert response.status_code == 422 and "invented-option" not in response.text

    def test_a_reference_to_an_option_in_the_run_is_accepted(self) -> None:
        http = client_for()
        trip_id, run, itinerary = self.saved_base(http)
        itinerary["days"][1]["items"][0]["option_id"] = choice(run)["hotel_id"]

        assert self.post(http, trip_id, itinerary).status_code == 201

    def test_too_many_items_and_too_much_text_are_refused(self) -> None:
        http = client_for()
        trip_id, _, itinerary = self.saved_base(http)
        crowded = {
            **itinerary,
            "days": [{**itinerary["days"][0], "items": itinerary["days"][0]["items"] * 10}],
        }
        long_text = {**itinerary, "notes": "x" * 501}

        assert self.post(http, trip_id, crowded).status_code == 422
        assert self.post(http, trip_id, long_text).status_code == 422

    def test_an_empty_itinerary_is_refused(self) -> None:
        http = client_for()
        trip_id, _, _ = self.saved_base(http)

        assert self.post(http, trip_id, {"days": []}).status_code == 422

    def test_the_saved_version_keeps_the_agent_version_too(self) -> None:
        http = client_for()
        trip_id, _, itinerary = self.saved_base(http)

        self.post(http, trip_id, itinerary)

        assert http.get(f"/api/v1/trips/{trip_id}/itinerary").json()["version"] == 2


class TestNothingBookingRelated:
    def test_planning_responses_never_claim_a_booking_or_payment(self) -> None:
        http = client_for()
        run = start(http, make_trip(http))
        http.post(f"/api/v1/runs/{run['run_id']}/selections", json=choice(run))
        paths = " ".join(http.get("/openapi.json").json()["paths"]).lower()
        text = http.get(f"/api/v1/runs/{run['run_id']}").text.lower()

        for word in ("payment", "charge", "card"):
            assert word not in paths
        for word in ("booked", "payment", "approved", "confirmed"):
            assert word not in text

    def test_a_date_in_the_request_is_a_plain_calendar_date(self) -> None:
        http = client_for()
        trip = http.get(f"/api/v1/trips/{make_trip(http)}").json()

        assert date.fromisoformat(trip["draft"]["departure_date"]) == date(2026, 12, 1)
