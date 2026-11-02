"""Allow a quote to be priced per vehicle (private taxi, ADR 0007).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

`quotes.price_basis` has a CHECK constraint listing the allowed bases. A private road vehicle is
priced per vehicle, so `PER_VEHICLE` joins `PER_TRAVELLER` and `PER_ROOM_NIGHT`. Only the
constraint changes: no column, no row and no permission is touched. `quotes` is evidence of what a
person was shown, so it is never rebuilt or emptied here.

The constraint is swapped inside a batch block, which is plain `ALTER TABLE ... DROP/ADD
CONSTRAINT` on PostgreSQL and a table copy on SQLite (the tests run the migrations there).

The downgrade puts the old constraint back. It cannot do that if a quote already uses
`PER_VEHICLE`: those rows could not satisfy the old rule, and deleting evidence to make a
downgrade pass would be worse than refusing. So it stops with a plain message and changes nothing.
Offline (`--sql`) there is no database to ask, so the check is left out of the rendered SQL.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_quotes_price_basis"
OLD_BASES = "'PER_TRAVELLER', 'PER_ROOM_NIGHT'"
NEW_BASES = "'PER_TRAVELLER', 'PER_ROOM_NIGHT', 'PER_VEHICLE'"


def _swap(allowed: str) -> None:
    with op.batch_alter_table("quotes") as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(CONSTRAINT, f"price_basis IN ({allowed})")


def upgrade() -> None:
    _swap(NEW_BASES)


def downgrade() -> None:
    if not op.get_context().as_sql:
        used = (
            op.get_bind()
            .execute(text("SELECT COUNT(*) FROM quotes WHERE price_basis = 'PER_VEHICLE'"))
            .scalar()
        )
        if used:
            raise RuntimeError(
                f"{used} quote(s) are priced per vehicle and the older schema cannot hold them. "
                "Quotes are evidence and are not deleted, so this downgrade is refused."
            )
    _swap(OLD_BASES)
