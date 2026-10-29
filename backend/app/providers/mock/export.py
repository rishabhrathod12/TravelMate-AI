"""The mock transport fixtures as JSON for the frontend demo (one source of truth).

The frontend prototype has no backend to call yet (only `GET /health` exists), so it needs the
same fictional services. Instead of keeping a second hand-written copy that can drift, the
templates in `fixtures.MOCK_SERVICES` are exported to a committed file, and a test fails if
that file is out of date. Regenerate it with `backend/scripts/export_demo_fixtures.py`.

The export holds templates, not dated options: the frontend applies the traveller's departure
date, as the mock provider does.
"""

import json
from typing import Any

from app.providers.mock.fixtures import CURRENCY, MOCK_SERVICES, MOCK_TEXT_NOTE, MockService

EXPORT_RELATIVE_PATH = "frontend/src/demo/transportFixtures.json"


def _template(service: MockService) -> dict[str, Any]:
    return {
        "key": service.key,
        "mode": service.mode.value,
        "operator_name": service.operator_name,
        "service_label": service.service_label,
        "departs": {"hour": service.departs[0], "minute": service.departs[1]},
        "arrives": {
            "day_offset": service.arrives_day_offset,
            "hour": service.arrives[0],
            "minute": service.arrives[1],
        },
        "stops": service.stops,
        "price_minor": service.price_minor,
        "currency": CURRENCY,
        "availability": service.availability.value,
        "cancellation_terms": service.cancellation_terms,
        "detail": service.detail,
    }


def export_transport_fixtures() -> str:
    """The exact text of the committed file, with a trailing newline."""
    document = {
        "note": (
            "Generated from backend/app/providers/mock/fixtures.py. Do not edit by hand. "
            "Every value is fictional demo data labelled MOCK."
        ),
        "mock_text_note": MOCK_TEXT_NOTE,
        "services": [_template(service) for service in MOCK_SERVICES],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
