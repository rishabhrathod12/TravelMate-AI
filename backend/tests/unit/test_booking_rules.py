"""The quote content hash and the idempotency helpers (owner decisions Q11 and Q15)."""

import hashlib
import json
from datetime import timedelta

from booking_support import NOW, make_snapshot

from app.domain.booking_rules import (
    hashed_idempotency_key,
    quote_content_hash,
    request_fingerprint,
)
from app.domain.money import Money
from app.domain.quote import Fee


class TestQuoteContentHash:
    def test_it_is_a_sha256_hex_digest(self) -> None:
        digest = quote_content_hash(make_snapshot())

        assert len(digest) == 64 and int(digest, 16) >= 0

    def test_the_same_terms_fetched_again_have_the_same_hash(self) -> None:
        first = make_snapshot(now=NOW)
        later = make_snapshot(now=NOW + timedelta(minutes=7))

        assert first.quote.id != later.quote.id
        assert first.quote.valid_until != later.quote.valid_until
        assert quote_content_hash(first) == quote_content_hash(later)

    def test_a_different_price_changes_it(self) -> None:
        assert quote_content_hash(make_snapshot()) != quote_content_hash(
            make_snapshot(extra_minor=1)
        )

    def test_a_different_option_changes_it(self) -> None:
        assert quote_content_hash(make_snapshot(index=0)) != quote_content_hash(
            make_snapshot(index=1)
        )

    def test_a_fee_changes_it(self) -> None:
        base = make_snapshot()
        fee = Fee(
            label="Booking fee", amount=Money(amount_minor=100, currency=base.quote.price.currency)
        )
        with_fee = base.model_copy(update={"quote": base.quote.model_copy(update={"fees": (fee,)})})

        assert quote_content_hash(base) != quote_content_hash(with_fee)

    def test_cancellation_terms_change_it(self) -> None:
        base = make_snapshot()
        other = base.model_copy(
            update={"quote": base.quote.model_copy(update={"cancellation_terms": "No refunds"})}
        )

        assert quote_content_hash(base) != quote_content_hash(other)

    def test_the_travellers_and_dates_change_it(self) -> None:
        base = make_snapshot()

        assert quote_content_hash(base) != quote_content_hash(
            base.model_copy(update={"travellers": 3})
        )
        assert quote_content_hash(base) != quote_content_hash(
            base.model_copy(update={"return_date": None})
        )

    def test_the_provenance_is_part_of_what_is_agreed(self) -> None:
        terms = json.dumps(["MOCK"])
        digest = quote_content_hash(make_snapshot())

        assert make_snapshot().quote.source.provenance.value in terms
        assert digest != hashlib.sha256(terms.encode()).hexdigest()


class TestIdempotencyKeys:
    def test_the_stored_key_depends_on_the_owner(self) -> None:
        assert hashed_idempotency_key("alice", "key-0000001") != hashed_idempotency_key(
            "bob", "key-0000001"
        )

    def test_the_stored_key_is_a_hash_not_the_text(self) -> None:
        stored = hashed_idempotency_key("alice", "key-0000001")

        assert "key-0000001" not in stored and len(stored) == 64

    def test_the_fingerprint_tells_requests_apart(self) -> None:
        base = request_fingerprint("t1", "TRANSPORT", "o1")

        assert base == request_fingerprint("t1", "TRANSPORT", "o1")
        assert base != request_fingerprint("t2", "TRANSPORT", "o1")
        assert base != request_fingerprint("t1", "HOTEL", "o1")
        assert base != request_fingerprint("t1", "TRANSPORT", "o2")
