"""Safe logging (SECURITY §9) and PRD AC-08: no secret appears in logs, responses or errors.

The checks use a made-up secret. Each layer is tested alone (by key, by value, by shape) and then
the whole path is run through the real app, including a request that carries the secret in a
header and an unexpected error that carries it in its message.
"""

import io
import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.observability.logs import configure_logging, get_logger, request_id_var
from app.observability.redaction import MASK, Redactor, is_sensitive_key

SECRET = "sk-FAKE-secret-value-1234567890"
API: dict[str, Any] = {
    "api_enabled": True,
    "api_dev_principal": "dev-1",
    "api_currency": "INR",
    "api_run_max_steps": 60,
    "api_run_max_tool_calls": 12,
    "api_run_max_human_rounds": 8,
    "api_max_runs_per_hour_per_owner": 5,
}


class TestTheRedactor:
    def test_a_known_secret_is_masked_wherever_it_appears(self) -> None:
        redactor = Redactor([SECRET])

        assert (
            redactor.text(f"failed with key {SECRET} at step 3")
            == f"failed with key {MASK} at step 3"
        )
        assert SECRET not in redactor.text(SECRET * 3)

    @pytest.mark.parametrize(
        "text",
        [
            "Authorization: Bearer abc.def-ghi_jkl123",
            "calling with sk-proj-abcdefghijklmnop",
            "postgresql://travelmate:hunter2@localhost:5432/db",
            "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----",
        ],
    )
    def test_secret_shapes_are_masked_even_when_nobody_listed_them(self, text: str) -> None:
        masked = Redactor().text(text)

        assert MASK in masked
        for leaked in ("abc.def-ghi_jkl123", "abcdefghijklmnop", "hunter2", "MIIEv"):
            assert leaked not in masked

    @pytest.mark.parametrize(
        "name",
        [
            "api_key",
            "OPENAI_API_KEY",
            "Authorization",
            "password",
            "db_password",
            "access_token",
            "client_secret",
            "Cookie",
            "traveller_name",
            "passenger",
            "email",
            "phone",
            "key",
        ],
    )
    def test_sensitive_field_names_mask_their_whole_value(self, name: str) -> None:
        assert is_sensitive_key(name) is True
        assert Redactor().value("anything at all", key=name) == MASK

    @pytest.mark.parametrize(
        "name", ["run_id", "trip_id", "status", "route", "duration_ms", "monkey", "keyboard"]
    )
    def test_ordinary_field_names_are_left_alone(self, name: str) -> None:
        assert is_sensitive_key(name) is False

    def test_nested_data_is_masked_at_every_depth(self) -> None:
        redactor = Redactor([SECRET])

        masked = redactor.value({"a": [{"b": f"x {SECRET}"}, {"api_key": "v"}], "n": 3})

        assert masked == {"a": [{"b": f"x {MASK}"}, {"api_key": MASK}], "n": 3}

    def test_very_short_values_are_not_treated_as_secrets(self) -> None:
        assert Redactor(["ab", "  "]).text("ab cd") == "ab cd"

    def test_a_secret_that_contains_another_is_masked_whole(self) -> None:
        assert Redactor(["abcd", "abcdefgh"]).text("abcdefgh") == MASK


class TestTheLogLines:
    def logger_and_stream(self, secrets: list[str]) -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        configure_logging("INFO", secrets, stream)
        return get_logger("test"), stream

    def lines(self, stream: io.StringIO) -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line]

    def test_every_line_is_json_with_a_time_a_level_and_the_request_id(self) -> None:
        log, stream = self.logger_and_stream([])
        token = request_id_var.set("req-abc12345")

        log.info("hello", extra={"run_id": "r1"})
        request_id_var.reset(token)

        entry = self.lines(stream)[0]
        assert entry["message"] == "hello" and entry["level"] == "INFO"
        assert entry["request_id"] == "req-abc12345" and entry["run_id"] == "r1"
        assert entry["logger"] == "travelmate.test" and "T" in entry["time"]

    def test_a_secret_in_a_message_an_argument_or_a_field_never_reaches_the_output(self) -> None:
        log, stream = self.logger_and_stream([SECRET])

        log.info("key is %s", SECRET)
        log.info("plain", extra={"note": f"see {SECRET}", "api_key": "other-value-here"})
        log.warning(f"Authorization: Bearer {SECRET}")

        output = stream.getvalue()
        assert SECRET not in output and "other-value-here" not in output
        assert output.count(MASK) >= 3

    def test_a_secret_inside_an_exception_traceback_is_masked(self) -> None:
        log, stream = self.logger_and_stream([SECRET])

        try:
            raise RuntimeError(f"upstream said {SECRET}")
        except RuntimeError:
            log.exception("it failed")

        output = stream.getvalue()
        assert SECRET not in output
        assert "RuntimeError" in output  # the type and place are still useful

    def test_reconfiguring_replaces_the_handler_instead_of_doubling_lines(self) -> None:
        log, stream = self.logger_and_stream([])
        configure_logging("INFO", [], stream)

        log.info("once")

        assert len(self.lines(stream)) == 1

    def test_logs_do_not_flow_to_the_root_logger_unredacted(self) -> None:
        self.logger_and_stream([])

        assert logging.getLogger("travelmate").propagate is False


class TestTheWholeAppNeverLeaksTheSecret:
    """AC-08: a known fake secret does not appear in captured log output or in any response."""

    def run_app(self, capsys: pytest.CaptureFixture[str]) -> tuple[str, list[str]]:
        settings = Settings.model_validate({**API, "openai_api_key": SecretStr(SECRET)})
        app = create_app(settings)
        http = TestClient(app, raise_server_exceptions=False)
        bodies: list[str] = []

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(f"the upstream rejected {SECRET}")

        app.state.trip_service.get_trip = boom
        trip = http.post(
            "/api/v1/trips",
            json={"title": "t", "draft": {"origin": "Indore"}},
            headers={"Authorization": f"Bearer {SECRET}", "X-Api-Key": SECRET},
        )
        bodies.append(trip.text)
        bodies.append(
            http.get("/api/v1/trips/x", headers={"Authorization": f"Bearer {SECRET}"}).text
        )
        bodies.append(http.get(f"/api/v1/trips/{SECRET}").text)
        bodies.append(http.get("/openapi.json").text)
        bodies.append(http.get("/health").text)
        return capsys.readouterr().err, bodies

    def test_the_secret_is_in_no_log_line_and_no_response(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        logs, bodies = self.run_app(capsys)

        assert logs, "the app should have logged its requests"
        assert SECRET not in logs
        for body in bodies:
            assert SECRET not in body

    def test_requests_are_logged_by_route_template_status_and_time_only(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        logs, _ = self.run_app(capsys)

        requests = [
            json.loads(line) for line in logs.splitlines() if '"message": "request"' in line
        ]
        assert requests
        for entry in requests:
            assert set(entry) >= {"method", "route", "status", "duration_ms", "request_id"}
            assert "?" not in entry["route"] and SECRET not in entry["route"]
        assert any(entry["route"] == "/api/v1/trips/{trip_id}" for entry in requests)

    def test_an_unexpected_error_is_logged_with_its_request_id_but_not_its_secret(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        logs, _ = self.run_app(capsys)

        errors = [json.loads(line) for line in logs.splitlines() if '"level": "ERROR"' in line]
        assert errors and all(e["request_id"] for e in errors)
        assert any("RuntimeError" in e.get("exception", "") for e in errors)

    def test_the_settings_never_print_the_key(self) -> None:
        settings = Settings.model_validate({**API, "openai_api_key": SecretStr(SECRET)})

        assert SECRET not in repr(settings) and SECRET not in str(settings)


class TestARealServer:
    """AC-08 against a running uvicorn, not just the test client.

    Starlette re-raises an unhandled error after it has answered, and uvicorn then logs the
    traceback itself. That log must be masked too.
    """

    def serve_and_break(self, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
        import socket
        import threading
        import time
        import urllib.error
        import urllib.request

        import uvicorn

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        def factory() -> Any:
            app = create_app(Settings.model_validate({**API, "openai_api_key": SecretStr(SECRET)}))

            def boom(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError(f"the upstream rejected {SECRET}")

            app.state.trip_service.get_trip = boom
            return app

        # As with the real command, uvicorn sets up its logging before the app is built.
        config = uvicorn.Config(
            factory, factory=True, host="127.0.0.1", port=port, log_level="info"
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "the test server did not start"
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/trips/abc",
                headers={"Authorization": f"Bearer {SECRET}"},
            )
            try:
                urllib.request.urlopen(request, timeout=10)  # noqa: S310 (a local test server)
                raise AssertionError("expected a 500")
            except urllib.error.HTTPError as error:
                status, body = error.code, error.read().decode()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        return status, body, capsys.readouterr().err

    def test_the_secret_is_in_neither_the_response_nor_the_servers_own_log(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status, body, logs = self.serve_and_break(capsys)

        assert status == 500
        assert SECRET not in body
        assert "RuntimeError" in logs, "the failure should still be logged"
        assert SECRET not in logs
