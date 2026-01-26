"""Add composite indexes for performance optimization

Revision ID: 0003_add_composite_indexes
Revises: 9f089af7cac4
Create Date: 2026-01-26 11:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_add_composite_indexes'
down_revision = '9f089af7cac4'
branch_labels = None
depends_on = None


def upgrade():
    """Add composite indexes for optimizing common query patterns"""
    
    # Contact table indexes
    op.create_index(
        'ix_contact_user_status',
        'contacts',
        ['user_id', 'status'],
        unique=False
    )
    op.create_index(
        'ix_contact_user_created',
        'contacts',
        ['user_id', 'created_at'],
        unique=False
    )
    op.create_index(
        'ix_contact_user_name',
        'contacts',
        ['user_id', 'name'],
        unique=False
    )
    op.create_index(
        'ix_contact_user_event_date',
        'contacts',
        ['user_id', 'event_date'],
        unique=False
    )
    
    # Reminder table index
    op.create_index(
        'ix_reminder_user_status_due',
        'reminders',
        ['user_id', 'status', 'due_at'],
        unique=False
    )


def downgrade():
    """Remove composite indexes"""
    
    # Drop reminder index
    op.drop_index('ix_reminder_user_status_due', table_name='reminders')
    
    # Drop contact indexes
    op.drop_index('ix_contact_user_event_date', table_name='contacts')
    op.drop_index('ix_contact_user_name', table_name='contacts')
    op.drop_index('ix_contact_user_created', table_name='contacts')
    op.drop_index('ix_contact_user_status', table_name='contacts')
