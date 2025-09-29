"""Create hierarchical ICCD system

Revision ID: hierarchical_iccd_001
Revises: add_iccd_tables
Create Date: 2025-01-29 15:54:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'hierarchical_iccd_001'
down_revision = 'add_iccd_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create hierarchical ICCD system tables."""
    
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Create iccd_base_records table only if it doesn't exist
    if 'iccd_base_records' not in existing_tables:
        op.create_table('iccd_base_records',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            
            # Codice Univoco Nazionale (NCT)
            sa.Column('nct_region', sa.String(2), nullable=False, default='12'),  # NCTR - Lazio
            sa.Column('nct_number', sa.String(8), nullable=False),               # NCTN
            sa.Column('nct_suffix', sa.String(2), nullable=True),                # NCTS
            
            # Metadati scheda
            sa.Column('schema_type', sa.String(5), nullable=False),  # SI, CA, MA, SAS, RA, NU, TMA, AT
            sa.Column('schema_version', sa.String(10), default='3.00'),
            sa.Column('level', sa.String(1), nullable=False, default='C'),  # P, C, A
            
            # Dati JSON della scheda
            sa.Column('iccd_data', postgresql.JSON, nullable=False),
            
            # Relazioni gerarchiche
            sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('site_id', postgresql.UUID(as_uuid=True), nullable=False),
            
            # Metadati gestione
            sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('created_at', sa.DateTime, default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, onupdate=sa.func.now()),
            sa.Column('status', sa.String(20), default='draft'),  # draft, validated, published
            
            # Foreign keys
            sa.ForeignKeyConstraint(['parent_id'], ['iccd_base_records.id']),
            sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        )
        
        # Create indexes for performance (only if table was created)
        try:
            op.create_index('idx_nct_complete', 'iccd_base_records', ['nct_region', 'nct_number', 'nct_suffix'])
        except Exception:
            pass  # Index might already exist
            
        try:
            op.create_index('idx_schema_site', 'iccd_base_records', ['schema_type', 'site_id'])
        except Exception:
            pass  # Index might already exist
            
        try:
            op.create_index('idx_hierarchy', 'iccd_base_records', ['parent_id', 'schema_type'])
        except Exception:
            pass  # Index might already exist
            
        try:
            op.create_index('idx_site_status', 'iccd_base_records', ['site_id', 'status'])
        except Exception:
            pass  # Index might already exist
            
        try:
            op.create_index('idx_created_at', 'iccd_base_records', ['created_at'])
        except Exception:
            pass  # Index might already exist
        
        # Create unique constraint for complete NCT
        try:
            op.create_unique_constraint('uq_nct_complete', 'iccd_base_records',
                                       ['nct_region', 'nct_number', 'nct_suffix'])
        except Exception:
            pass  # Constraint might already exist
    
    # Create iccd_relations table only if it doesn't exist
    if 'iccd_relations' not in existing_tables:
        op.create_table('iccd_relations',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            
            sa.Column('source_record_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('target_record_id', postgresql.UUID(as_uuid=True), nullable=False),
            
            sa.Column('relation_type', sa.String(50), nullable=False),
            # Tipi: "contenuto_in", "composto_da", "relazionato_a", "derivato_da",
            #       "stesso_contesto", "stesso_corredo", "stessa_campagna"
            
            sa.Column('relation_level', sa.String(1), default='1'),  # 1=principale, 2=secondaria, 3=terziaria
            sa.Column('notes', sa.Text),
            
            sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('created_at', sa.DateTime, default=sa.func.now()),
            
            # Foreign keys
            sa.ForeignKeyConstraint(['source_record_id'], ['iccd_base_records.id']),
            sa.ForeignKeyConstraint(['target_record_id'], ['iccd_base_records.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        )
        
        # Create indexes for relations
        try:
            op.create_index('idx_source_relation', 'iccd_relations', ['source_record_id', 'relation_type'])
        except Exception:
            pass
            
        try:
            op.create_index('idx_target_relation', 'iccd_relations', ['target_record_id', 'relation_type'])
        except Exception:
            pass
    
    # Create iccd_authority_files table only if it doesn't exist
    if 'iccd_authority_files' not in existing_tables:
        op.create_table('iccd_authority_files',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            
            sa.Column('authority_type', sa.String(10), nullable=False),  # DSC, RCG, BIB, AUT
            sa.Column('authority_code', sa.String(20), unique=True, nullable=False),
            
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text),
            
            # Dati specifici authority
            sa.Column('authority_data', postgresql.JSON),
            
            sa.Column('site_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('created_at', sa.DateTime, default=sa.func.now()),
            
            # Foreign keys
            sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        )
        
        # Create indexes for authority files
        try:
            op.create_index('idx_authority_type_site', 'iccd_authority_files', ['authority_type', 'site_id'])
        except Exception:
            pass
            
        try:
            op.create_index('idx_authority_code', 'iccd_authority_files', ['authority_code'])
        except Exception:
            pass
    
    # Add relationship column to archaeological_sites for backward compatibility
    try:
        op.add_column('archaeological_sites',
                      sa.Column('iccd_hierarchy_enabled', sa.Boolean, default=True))
    except Exception:
        pass  # Column might already exist


def downgrade() -> None:
    """Drop hierarchical ICCD system tables."""
    
    # Drop tables in reverse order
    op.drop_table('iccd_authority_files')
    op.drop_table('iccd_relations')
    op.drop_table('iccd_base_records')
    
    # Remove added column
    op.drop_column('archaeological_sites', 'iccd_hierarchy_enabled')