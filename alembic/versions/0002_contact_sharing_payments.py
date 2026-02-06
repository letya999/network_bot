"""Contact sharing, payments, and subscriptions

Revision ID: 0002_contact_sharing
Revises: 0001_initial
Create Date: 2026-02-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_contact_sharing'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Subscriptions table
    op.create_table('subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='free'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('provider_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('provider_customer_id', sa.String(length=255), nullable=True),
        sa.Column('price_amount', sa.Numeric(precision=10, scale=2), server_default='0', nullable=True),
        sa.Column('price_currency', sa.String(length=3), server_default='RUB', nullable=True),
        sa.Column('billing_cycle_days', sa.Integer(), server_default='30', nullable=True),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_payment_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)

    # 2. Payments table
    op.create_table('payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('payment_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='RUB'),
        sa.Column('provider_payment_id', sa.String(length=255), nullable=True),
        sa.Column('provider_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_share_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_user_id'), 'payments', ['user_id'], unique=False)

    # 3. Contact shares table
    op.create_table('contact_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visibility', sa.String(length=50), nullable=False, server_default='public'),
        sa.Column('allowed_user_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('visible_fields', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('hidden_fields', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('price_amount', sa.String(length=20), server_default='0', nullable=True),
        sa.Column('price_currency', sa.String(length=3), server_default='RUB', nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('share_token', sa.String(length=64), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('view_count', sa.String(length=20), server_default='0', nullable=True),
        sa.Column('purchase_count', sa.String(length=20), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contact_shares_contact_id'), 'contact_shares', ['contact_id'], unique=False)
    op.create_index(op.f('ix_contact_shares_owner_id'), 'contact_shares', ['owner_id'], unique=False)
    op.create_index(op.f('ix_contact_shares_share_token'), 'contact_shares', ['share_token'], unique=True)
    op.create_index('ix_share_owner_active', 'contact_shares', ['owner_id', 'is_active'], unique=False)
    op.create_index('ix_share_visibility', 'contact_shares', ['visibility', 'is_active'], unique=False)

    # Add FK for payments.contact_share_id (now that contact_shares exists)
    op.create_foreign_key('fk_payments_contact_share', 'payments', 'contact_shares', ['contact_share_id'], ['id'])

    # 4. Contact purchases table
    op.create_table('contact_purchases',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('buyer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('seller_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('copied_contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('payment_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('amount_paid', sa.String(length=20), server_default='0', nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='RUB', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['share_id'], ['contact_shares.id']),
        sa.ForeignKeyConstraint(['buyer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id']),
        sa.ForeignKeyConstraint(['copied_contact_id'], ['contacts.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contact_purchases_share_id'), 'contact_purchases', ['share_id'], unique=False)
    op.create_index(op.f('ix_contact_purchases_buyer_id'), 'contact_purchases', ['buyer_id'], unique=False)
    op.create_index('ix_purchase_buyer', 'contact_purchases', ['buyer_id', 'share_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_purchase_buyer', table_name='contact_purchases')
    op.drop_index(op.f('ix_contact_purchases_buyer_id'), table_name='contact_purchases')
    op.drop_index(op.f('ix_contact_purchases_share_id'), table_name='contact_purchases')
    op.drop_table('contact_purchases')

    op.drop_constraint('fk_payments_contact_share', 'payments', type_='foreignkey')

    op.drop_index('ix_share_visibility', table_name='contact_shares')
    op.drop_index('ix_share_owner_active', table_name='contact_shares')
    op.drop_index(op.f('ix_contact_shares_share_token'), table_name='contact_shares')
    op.drop_index(op.f('ix_contact_shares_owner_id'), table_name='contact_shares')
    op.drop_index(op.f('ix_contact_shares_contact_id'), table_name='contact_shares')
    op.drop_table('contact_shares')

    op.drop_index(op.f('ix_payments_user_id'), table_name='payments')
    op.drop_table('payments')

    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
