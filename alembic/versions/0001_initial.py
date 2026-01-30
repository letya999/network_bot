"""Initial migration

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-30 14:00:00.000000

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
    # 1. Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('profile_data', sa.JSON(), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('custom_prompt', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    # 3. Contacts table
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
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['introduced_by_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contacts_user_id'), 'contacts', ['user_id'], unique=False)
    
    # Composite indexes for contacts
    op.create_index('ix_contact_user_status', 'contacts', ['user_id', 'status'], unique=False)
    op.create_index('ix_contact_user_created', 'contacts', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_contact_user_name', 'contacts', ['user_id', 'name'], unique=False)
    op.create_index('ix_contact_user_event_date', 'contacts', ['user_id', 'event_date'], unique=False)
    
    # GIN indexes for contacts (requires pg_trgm)
    op.create_index('ix_contacts_name_trgm', 'contacts', ['name'], postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.create_index('ix_contacts_company_trgm', 'contacts', ['company'], postgresql_using='gin', postgresql_ops={'company': 'gin_trgm_ops'})

    # 4. Interactions table
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

    # 5. Reminders table
    op.create_table('reminders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'COMPLETED', 'CANCELLED', name='reminderstatus'), nullable=False),
        sa.Column('is_recurring', sa.Boolean(), nullable=True),
        sa.Column('recurrence_rule', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reminders_contact_id'), 'reminders', ['contact_id'], unique=False)
    op.create_index(op.f('ix_reminders_due_at'), 'reminders', ['due_at'], unique=False)
    op.create_index(op.f('ix_reminders_user_id'), 'reminders', ['user_id'], unique=False)
    op.create_index('ix_reminder_user_status_due', 'reminders', ['user_id', 'status', 'due_at'], unique=False)

    # 6. Matches table
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
    # Drop Matches
    op.drop_index(op.f('ix_matches_user_id'), table_name='matches')
    op.drop_table('matches')

    # Drop Reminders
    op.drop_index('ix_reminder_user_status_due', table_name='reminders')
    op.drop_index(op.f('ix_reminders_user_id'), table_name='reminders')
    op.drop_index(op.f('ix_reminders_due_at'), table_name='reminders')
    op.drop_index(op.f('ix_reminders_contact_id'), table_name='reminders')
    op.drop_table('reminders')
    # Try to drop the enum type
    op.execute("DROP TYPE IF EXISTS reminderstatus")

    # Drop Interactions
    op.drop_index(op.f('ix_interactions_contact_id'), table_name='interactions')
    op.drop_table('interactions')

    # Drop Contacts
    op.drop_index('ix_contacts_company_trgm', table_name='contacts')
    op.drop_index('ix_contacts_name_trgm', table_name='contacts')
    op.drop_index('ix_contact_user_event_date', table_name='contacts')
    op.drop_index('ix_contact_user_name', table_name='contacts')
    op.drop_index('ix_contact_user_created', table_name='contacts')
    op.drop_index('ix_contact_user_status', table_name='contacts')
    op.drop_index(op.f('ix_contacts_user_id'), table_name='contacts')
    op.drop_table('contacts')

    # Drop Users
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')

    # Drop Extension
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
