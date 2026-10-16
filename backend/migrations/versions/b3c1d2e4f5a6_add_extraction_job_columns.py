"""add extraction job columns

The extraction job now gets only an upload's id (a Cloud Task holds at most ~1 MB, and PDFs
can be 10 MB), so everything Claude needs is saved at upload time:

  - tables_json: the PDF's tables, next to the raw_text that was already saved
  - extraction_claimed_at: set by the job that claims the upload, only while it's still unset,
    so a retried job can't call Claude a second time

Both nullable: existing uploads have no tables saved and were never claimed.

Revision ID: b3c1d2e4f5a6
Revises: 7339f928223f
Create Date: 2026-10-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = '7339f928223f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tables_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('extraction_claimed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.drop_column('extraction_claimed_at')
        batch_op.drop_column('tables_json')
