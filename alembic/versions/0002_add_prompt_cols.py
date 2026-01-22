"""add prompt cols

Revision ID: 0002_add_prompt_cols
Revises: 0001_initial
Create Date: 2026-01-22 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002_add_prompt_cols'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add custom_prompt to users
    op.add_column('users', sa.Column('custom_prompt', sa.Text(), nullable=True))
    
    # Add attributes to contacts
    op.add_column('contacts', sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))


def downgrade() -> None:
    op.drop_column('contacts', 'attributes')
    op.drop_column('users', 'custom_prompt')
