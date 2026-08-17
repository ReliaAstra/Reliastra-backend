"""create model tables that were never migrated

Revision ID: 0013_missing_model_tables
Revises: 0012_user_admin_fields
Create Date: 2026-08-17

The ORM declares 14 tables (admin panel, feedback, campaigns, sessions,
announcements, in-app notifications, health/error logging) that have NO
migration. Any endpoint touching them fails with
``relation does not exist``. This migration creates them from the model
metadata (generated via alembic autogenerate, stripped of destructive
diff noise against pre-existing tables).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_missing_model_tables"
down_revision = "0012_user_admin_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admin_audit_logs',
    sa.Column('admin_user_id', sa.UUID(), nullable=True),
    sa.Column('admin_email', sa.String(length=255), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('entity_type', sa.String(length=100), nullable=True),
    sa.Column('entity_id', sa.String(length=255), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admin_audit_logs_action'), 'admin_audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_admin_user_id'), 'admin_audit_logs', ['admin_user_id'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_created_at'), 'admin_audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_entity_type'), 'admin_audit_logs', ['entity_type'], unique=False)
    op.create_table('announcements',
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=False),
    sa.Column('placement', sa.String(length=50), nullable=False),
    sa.Column('target_plans', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('target_segment', sa.String(length=50), nullable=True),
    sa.Column('action_url', sa.String(length=500), nullable=True),
    sa.Column('action_label', sa.String(length=100), nullable=True),
    sa.Column('is_dismissible', sa.Boolean(), nullable=False),
    sa.Column('bg_color', sa.String(length=20), nullable=True),
    sa.Column('text_color', sa.String(length=20), nullable=True),
    sa.Column('impression_count', sa.Integer(), nullable=False),
    sa.Column('dismissal_count', sa.Integer(), nullable=False),
    sa.Column('click_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_announcements_is_active'), 'announcements', ['is_active'], unique=False)
    op.create_table('app_error_logs',
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('component', sa.String(length=100), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('stack_trace', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=255), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('org_id', sa.UUID(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_error_logs_component'), 'app_error_logs', ['component'], unique=False)
    op.create_index(op.f('ix_app_error_logs_created_at'), 'app_error_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_app_error_logs_is_resolved'), 'app_error_logs', ['is_resolved'], unique=False)
    op.create_index(op.f('ix_app_error_logs_level'), 'app_error_logs', ['level'], unique=False)
    op.create_index(op.f('ix_app_error_logs_org_id'), 'app_error_logs', ['org_id'], unique=False)
    op.create_index(op.f('ix_app_error_logs_request_id'), 'app_error_logs', ['request_id'], unique=False)
    op.create_index(op.f('ix_app_error_logs_user_id'), 'app_error_logs', ['user_id'], unique=False)
    op.create_table('email_campaigns',
    sa.Column('campaign_name', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=True),
    sa.Column('segment', sa.String(length=100), nullable=True),
    sa.Column('recipient_count', sa.Integer(), nullable=False),
    sa.Column('sent_count', sa.Integer(), nullable=False),
    sa.Column('opened_count', sa.Integer(), nullable=False),
    sa.Column('clicked_count', sa.Integer(), nullable=False),
    sa.Column('bounced_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('utm_campaign', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_campaigns_status'), 'email_campaigns', ['status'], unique=False)
    op.create_table('feedback_tickets',
    sa.Column('ticket_number', sa.String(length=50), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('assigned_to', sa.UUID(), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_tickets_assigned_to'), 'feedback_tickets', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_feedback_tickets_category'), 'feedback_tickets', ['category'], unique=False)
    op.create_index(op.f('ix_feedback_tickets_created_at'), 'feedback_tickets', ['created_at'], unique=False)
    op.create_index(op.f('ix_feedback_tickets_priority'), 'feedback_tickets', ['priority'], unique=False)
    op.create_index(op.f('ix_feedback_tickets_status'), 'feedback_tickets', ['status'], unique=False)
    op.create_index(op.f('ix_feedback_tickets_ticket_number'), 'feedback_tickets', ['ticket_number'], unique=True)
    op.create_index(op.f('ix_feedback_tickets_user_id'), 'feedback_tickets', ['user_id'], unique=False)
    op.create_table('in_app_notifications',
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('notification_type', sa.String(length=50), nullable=False),
    sa.Column('action_url', sa.String(length=500), nullable=True),
    sa.Column('action_label', sa.String(length=100), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_dismissible', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_in_app_notifications_created_at'), 'in_app_notifications', ['created_at'], unique=False)
    op.create_table('plan_change_histories',
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('changed_by', sa.UUID(), nullable=True),
    sa.Column('from_plan', sa.String(length=50), nullable=False),
    sa.Column('to_plan', sa.String(length=50), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('admin_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plan_change_histories_created_at'), 'plan_change_histories', ['created_at'], unique=False)
    op.create_index(op.f('ix_plan_change_histories_org_id'), 'plan_change_histories', ['org_id'], unique=False)
    op.create_table('system_health_alerts',
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('component', sa.String(length=100), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_resolved', sa.Boolean(), nullable=False),
    sa.Column('acknowledged', sa.Boolean(), nullable=False),
    sa.Column('acknowledged_by', sa.UUID(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_health_alerts_component'), 'system_health_alerts', ['component'], unique=False)
    op.create_index(op.f('ix_system_health_alerts_created_at'), 'system_health_alerts', ['created_at'], unique=False)
    op.create_index(op.f('ix_system_health_alerts_is_resolved'), 'system_health_alerts', ['is_resolved'], unique=False)
    op.create_index(op.f('ix_system_health_alerts_severity'), 'system_health_alerts', ['severity'], unique=False)
    op.create_table('user_activity_logs',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_activity_logs_action'), 'user_activity_logs', ['action'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_created_at'), 'user_activity_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_user_id'), 'user_activity_logs', ['user_id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('session_token_hash', sa.String(length=255), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('login_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_sessions_session_token_hash'), 'user_sessions', ['session_token_hash'], unique=False)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('announcement_dismissals',
    sa.Column('announcement_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_dismissal')
    )
    op.create_index(op.f('ix_announcement_dismissals_announcement_id'), 'announcement_dismissals', ['announcement_id'], unique=False)
    op.create_index(op.f('ix_announcement_dismissals_user_id'), 'announcement_dismissals', ['user_id'], unique=False)
    op.create_table('email_campaign_recipients',
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bounced_reason', sa.Text(), nullable=True),
    sa.Column('tracking_pixel_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['email_campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_campaign_recipients_campaign_id'), 'email_campaign_recipients', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_email_campaign_recipients_status'), 'email_campaign_recipients', ['status'], unique=False)
    op.create_index(op.f('ix_email_campaign_recipients_user_id'), 'email_campaign_recipients', ['user_id'], unique=False)
    op.create_table('feedback_messages',
    sa.Column('ticket_id', sa.UUID(), nullable=False),
    sa.Column('sender_type', sa.String(length=30), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('sender_name', sa.String(length=150), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('is_internal_note', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['ticket_id'], ['feedback_tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_messages_created_at'), 'feedback_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_feedback_messages_ticket_id'), 'feedback_messages', ['ticket_id'], unique=False)
    op.create_table('in_app_notification_deliveries',
    sa.Column('notification_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('is_clicked', sa.Boolean(), nullable=False),
    sa.Column('is_dismissed', sa.Boolean(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['in_app_notifications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_in_app_notification_deliveries_notification_id'), 'in_app_notification_deliveries', ['notification_id'], unique=False)
    op.create_index(op.f('ix_in_app_notification_deliveries_user_id'), 'in_app_notification_deliveries', ['user_id'], unique=False)

def downgrade() -> None:
    for table in [
        "in_app_notification_deliveries",
        "feedback_messages",
        "email_campaign_recipients",
        "announcement_dismissals",
        "user_sessions",
        "user_activity_logs",
        "system_health_alerts",
        "plan_change_histories",
        "in_app_notifications",
        "feedback_tickets",
        "email_campaigns",
        "app_error_logs",
        "announcements",
        "admin_audit_logs",
    ]:
        op.drop_table(table)
