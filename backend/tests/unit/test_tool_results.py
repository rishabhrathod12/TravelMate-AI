"""An empty tool result must always say why (PRD §9); a failure is data, not an exception."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.tools.results import (
    HotelSearchResult,
    ToolError,
    ToolErrorKind,
    TransportSearchResult,
    WeatherResult,
)

SOURCE: dict[str, Any] = {
    "provenance": "MOCK",
    "provider_name": "mock-weather",
    "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
    "freshness_window_seconds": 900,
}


def an_error() -> ToolError:
    return ToolError(provider_name="p", kind=ToolErrorKind.TIMEOUT, message="p: slow")


def forecast(days: int) -> dict[str, Any]:
    return {
        "location": {"name": "Goa"},
        "requested_start": date(2026, 12, 1),
        "requested_end": date(2026, 12, 2),
        "days": [{"day": date(2026, 12, 1 + n), "summary": "Sunny (mock)"} for n in range(days)],
        "source": SOURCE,
    }


class TestToolError:
    def test_holds_the_provider_the_kind_and_the_message(self) -> None:
        error = an_error()

        assert (error.provider_name, error.kind, error.message) == (
            "p",
            ToolErrorKind.TIMEOUT,
            "p: slow",
        )

    @pytest.mark.parametrize("field", ["provider_name", "message"])
    def test_text_fields_must_not_be_blank(self, field: str) -> None:
        data = {"provider_name": "p", "kind": "TIMEOUT", "message": "m", field: " "}

        with pytest.raises(ValidationError, match=field):
            ToolError.model_validate(data)

    def test_the_kinds_cover_every_provider_failure(self) -> None:
        assert {k.value for k in ToolErrorKind} == {
            "UNAVAILABLE",
            "RATE_LIMITED",
            "TIMEOUT",
            "INVALID_RESPONSE",
            "PROVIDER_ERROR",
        }


@pytest.mark.parametrize("result_class", [TransportSearchResult, HotelSearchResult])
class TestOptionResults:
    def test_empty_without_a_reason_is_not_allowed(self, result_class: Any) -> None:
        with pytest.raises(ValidationError, match="must say why"):
            result_class()

    def test_empty_with_a_reason_is_fine(self, result_class: Any) -> None:
        assert result_class(empty_reason="nothing for this route").options == ()

    def test_an_error_explains_the_emptiness_by_itself(self, result_class: Any) -> None:
        result = result_class(errors=(an_error(),))

        assert result.empty_reason is None
        assert result.errors[0].kind is ToolErrorKind.TIMEOUT

    def test_a_reason_next_to_an_error_is_rejected(self, result_class: Any) -> None:
        with pytest.raises(ValidationError, match="only for an empty result with no error"):
            result_class(errors=(an_error(),), empty_reason="also nothing")

    def test_a_blank_reason_is_rejected(self, result_class: Any) -> None:
        with pytest.raises(ValidationError, match="empty_reason"):
            result_class(empty_reason="  ")

    def test_unknown_fields_are_rejected(self, result_class: Any) -> None:
        with pytest.raises(ValidationError, match="booking"):
            result_class(empty_reason="x", booking="yes")


class TestWeatherResult:
    def test_a_forecast_with_days_needs_no_reason(self) -> None:
        result = WeatherResult.model_validate({"forecast": forecast(2)})

        assert result.forecast is not None and result.empty_reason is None

    def test_a_forecast_with_no_days_must_say_why(self) -> None:
        with pytest.raises(ValidationError, match="must say why"):
            WeatherResult.model_validate({"forecast": forecast(0)})

    def test_a_forecast_with_no_days_is_kept_with_its_reason(self) -> None:
        result = WeatherResult.model_validate({"forecast": forecast(0), "empty_reason": "none"})

        assert result.forecast is not None
        assert len(result.forecast.missing_dates) == 2

    def test_nothing_at_all_must_say_why(self) -> None:
        with pytest.raises(ValidationError, match="must say why"):
            WeatherResult()

    def test_an_error_alone_is_enough(self) -> None:
        result = WeatherResult(errors=(an_error(),))

        assert result.forecast is None

    def test_a_reason_next_to_data_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="only for an empty result"):
            WeatherResult.model_validate({"forecast": forecast(2), "empty_reason": "odd"})


def test_results_are_immutable() -> None:
    result = TransportSearchResult(empty_reason="x")

    with pytest.raises(ValidationError, match="frozen"):
        result.empty_reason = "y"
