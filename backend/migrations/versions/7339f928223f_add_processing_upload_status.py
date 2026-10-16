"""add processing upload status

Uploads are now saved *before* Claude runs, with status 'processing', so the CHECK constraint
on uploads.status has to allow the new value. Alembic's autogenerate can't see CHECK
constraint changes, so this one is written by hand. On SQLite, batch mode rebuilds the table
(copy, drop, rename), because SQLite can't change a constraint in place.

The values are written out here rather than imported from app.domain: a migration describes
the schema at one point in time, and must not change when the app's code changes later.

Revision ID: 7339f928223f
Revises: e6f01ca19a79
Create Date: 2026-10-15 17:55:13.400237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7339f928223f'
down_revision: Union[str, Sequence[str], None] = 'e6f01ca19a79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upload_status(*values: str) -> sa.Enum:
    # Matches models.status_column_type: VARCHAR(20) plus a CHECK constraint named upload_status.
    return sa.Enum(*values, name='upload_status', native_enum=False, create_constraint=True, length=20)


OLD = upload_status('extracted', 'failed')
NEW = upload_status('processing', 'extracted', 'failed')


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.alter_column('status', existing_type=OLD, type_=NEW, existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # The old constraint doesn't allow 'processing', so those rows have to become something it does.
    op.execute(
        "UPDATE uploads SET status = 'failed', error_message = 'Extraction was interrupted.' "
        "WHERE status = 'processing'"
    )
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.alter_column('status', existing_type=NEW, type_=OLD, existing_nullable=False)
