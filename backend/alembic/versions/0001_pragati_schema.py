"""PRAGATI initial schema (creates all PRAGATI tables from the model metadata).

Using metadata.create_all keeps this baseline in lock-step with app.models. Later revisions should be
generated with `alembic revision --autogenerate` and contain explicit operations.

Revision ID: 0001
Revises:
"""
from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
