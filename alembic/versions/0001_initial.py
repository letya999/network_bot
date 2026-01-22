"""Initial migration

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('profile_data', sa.JSON(), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    # Contacts table
    op.create_table('contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('company', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('telegram_username', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('linkedin_url', sa.String(length=500), nullable=True),
        sa.Column('event_name', sa.String(length=255), nullable=True),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('introduced_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('what_looking_for', sa.Text(), nullable=True),
        sa.Column('can_help_with', sa.Text(), nullable=True),
        sa.Column('topics', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('agreements', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('follow_up_action', sa.Text(), nullable=True),
        sa.Column('raw_transcript', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('osint_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['introduced_by_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contacts_user_id'), 'contacts', ['user_id'], unique=False)

    # Interactions table
    op.create_table('interactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('date', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interactions_contact_id'), 'interactions', ['contact_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_interactions_contact_id'), table_name='interactions')
    op.drop_table('interactions')
    op.drop_index(op.f('ix_contacts_user_id'), table_name='contacts')
    op.drop_table('contacts')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')
