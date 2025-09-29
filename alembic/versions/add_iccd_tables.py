"""add_iccd_tables

Revision ID: add_iccd_tables
Revises: 
Create Date: 2025-09-29 10:12:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_iccd_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crea tabella iccd_records
    op.create_table('iccd_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nct_region', sa.String(length=2), nullable=False),
        sa.Column('nct_number', sa.String(length=8), nullable=False),
        sa.Column('nct_suffix', sa.String(length=2), nullable=True),
        sa.Column('schema_type', sa.String(length=5), nullable=False),
        sa.Column('level', sa.String(length=1), nullable=False),
        sa.Column('iccd_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('cataloging_institution', sa.String(length=100), nullable=False),
        sa.Column('cataloger_name', sa.String(length=255), nullable=True),
        sa.Column('is_validated', sa.Boolean(), nullable=False),
        sa.Column('validation_date', sa.DateTime(), nullable=True),
        sa.Column('validation_notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('survey_date', sa.DateTime(), nullable=True),
        sa.Column('creation_date', sa.DateTime(), nullable=False),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('validated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id'], ),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nct_region', 'nct_number', 'nct_suffix', name='uq_nct_complete')
    )
    
    # Indici per performance
    op.create_index('idx_nct_complete', 'iccd_records', ['nct_region', 'nct_number', 'nct_suffix'])
    op.create_index('idx_schema_site', 'iccd_records', ['schema_type', 'site_id'])
    op.create_index('idx_status_level', 'iccd_records', ['status', 'level'])
    op.create_index(op.f('ix_iccd_records_id'), 'iccd_records', ['id'])
    op.create_index(op.f('ix_iccd_records_is_validated'), 'iccd_records', ['is_validated'])
    op.create_index(op.f('ix_iccd_records_level'), 'iccd_records', ['level'])
    op.create_index(op.f('ix_iccd_records_nct_number'), 'iccd_records', ['nct_number'])
    op.create_index(op.f('ix_iccd_records_nct_region'), 'iccd_records', ['nct_region'])
    op.create_index(op.f('ix_iccd_records_schema_type'), 'iccd_records', ['schema_type'])
    op.create_index(op.f('ix_iccd_records_status'), 'iccd_records', ['status'])

    # Crea tabella iccd_schema_templates
    op.create_table('iccd_schema_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('schema_type', sa.String(length=5), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(length=10), nullable=False),
        sa.Column('json_schema', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('ui_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('icon', sa.String(length=10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('standard_compliant', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('schema_type')
    )
    
    op.create_index(op.f('ix_iccd_schema_templates_schema_type'), 'iccd_schema_templates', ['schema_type'])

    # Crea tabella iccd_validation_rules
    op.create_table('iccd_validation_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('schema_type', sa.String(length=5), nullable=False),
        sa.Column('level', sa.String(length=1), nullable=False),
        sa.Column('field_path', sa.String(length=255), nullable=False),
        sa.Column('rule_type', sa.String(length=50), nullable=False),
        sa.Column('rule_config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indici per validation rules
    op.create_index('idx_validation_active', 'iccd_validation_rules', ['is_active', 'priority'])
    op.create_index('idx_validation_schema_level', 'iccd_validation_rules', ['schema_type', 'level'])
    op.create_index(op.f('ix_iccd_validation_rules_level'), 'iccd_validation_rules', ['level'])
    op.create_index(op.f('ix_iccd_validation_rules_schema_type'), 'iccd_validation_rules', ['schema_type'])


def downgrade() -> None:
    # Drop indici
    op.drop_index(op.f('ix_iccd_validation_rules_schema_type'), table_name='iccd_validation_rules')
    op.drop_index(op.f('ix_iccd_validation_rules_level'), table_name='iccd_validation_rules')
    op.drop_index('idx_validation_schema_level', table_name='iccd_validation_rules')
    op.drop_index('idx_validation_active', table_name='iccd_validation_rules')
    
    op.drop_index(op.f('ix_iccd_schema_templates_schema_type'), table_name='iccd_schema_templates')
    
    op.drop_index(op.f('ix_iccd_records_status'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_schema_type'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_nct_region'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_nct_number'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_level'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_is_validated'), table_name='iccd_records')
    op.drop_index(op.f('ix_iccd_records_id'), table_name='iccd_records')
    op.drop_index('idx_status_level', table_name='iccd_records')
    op.drop_index('idx_schema_site', table_name='iccd_records')
    op.drop_index('idx_nct_complete', table_name='iccd_records')
    
    # Drop tabelle
    op.drop_table('iccd_validation_rules')
    op.drop_table('iccd_schema_templates')
    op.drop_table('iccd_records')