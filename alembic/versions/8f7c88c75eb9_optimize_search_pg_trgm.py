"""optimize_search_pg_trgm_and_add_matches

Revision ID: 8f7c88c75eb9
Revises: 0003_add_composite_indexes
Create Date: 2026-01-30 10:43:25.234600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8f7c88c75eb9'
down_revision: Union[str, None] = '0003_add_composite_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Add GIN indexes for fast text search
    # Note: This requires the table/column to be text/varchar. 
    op.create_index(
        'ix_contacts_name_trgm',
        'contacts',
        ['name'],
        postgresql_using='gin',
        postgresql_ops={'name': 'gin_trgm_ops'}
    )
    op.create_index(
        'ix_contacts_company_trgm',
        'contacts',
        ['company'],
        postgresql_using='gin',
        postgresql_ops={'company': 'gin_trgm_ops'}
    )

    # 3. Create Matches table
    op.create_table('matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('contact_a_id', sa.UUID(), nullable=False),
        sa.Column('contact_b_id', sa.UUID(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('synergy_summary', sa.Text(), nullable=True),
        sa.Column('suggested_pitch', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contact_a_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['contact_b_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contact_a_id', 'contact_b_id', name='uq_match_contacts')
    )
    op.create_index(op.f('ix_matches_user_id'), 'matches', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_matches_user_id'), table_name='matches')
    op.drop_table('matches')
    
    op.drop_index('ix_contacts_company_trgm', table_name='contacts')
    op.drop_index('ix_contacts_name_trgm', table_name='contacts')
    
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
