"""Remove PhotoModification table - use UserActivity instead

Revision ID: remove_photo_modifications
Revises: optimize_database_001
Create Date: 2025-01-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'remove_photo_modifications'
down_revision = 'optimize_database_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Rimuove la tabella photo_modifications.
    
    RATIONALE:
    - La tabella PhotoModification è ridondante
    - Il sistema UserActivity già traccia tutte le modifiche (photo_id field)
    - UserActivity è più completo (IP, user_agent, extra_data JSON)
    - Riduce complessità del database
    - Risparmia spazio disco
    
    MIGRAZIONE DATI:
    Se esistono dati in photo_modifications, vengono migrati in user_activities
    prima della rimozione della tabella.
    """
    
    # Verifica se la tabella esiste
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'photo_modifications' in existing_tables:
        print("📊 Migrando dati da photo_modifications a user_activities...")
        
        # Migra i dati esistenti a user_activities
        op.execute("""
            INSERT INTO user_activities (
                id,
                user_id,
                activity_date,
                activity_type,
                activity_desc,
                photo_id,
                extra_data,
                created,
                updated
            )
            SELECT 
                gen_random_uuid(),
                pm.modified_by,
                pm.created,
                'photo_' || LOWER(pm.modification_type),
                COALESCE(pm.notes, 'Campo modificato: ' || COALESCE(pm.field_changed, 'sconosciuto')),
                pm.photo_id,
                json_build_object(
                    'field_changed', pm.field_changed,
                    'old_value', pm.old_value,
                    'new_value', pm.new_value,
                    'modification_type', pm.modification_type,
                    'migrated_from', 'photo_modifications'
                )::text,
                pm.created,
                pm.updated
            FROM photo_modifications pm
            WHERE NOT EXISTS (
                SELECT 1 FROM user_activities ua 
                WHERE ua.photo_id = pm.photo_id 
                AND ua.user_id = pm.modified_by
                AND ua.created = pm.created
            )
        """)
        
        records_migrated = bind.execute(sa.text("SELECT COUNT(*) FROM photo_modifications")).scalar()
        print(f"✅ Migrati {records_migrated} record da photo_modifications a user_activities")
        
        # Rimuovi indici
        print("🗑️ Rimuovendo indici photo_modifications...")
        try:
            op.drop_index('idx_modification_photo', table_name='photo_modifications')
        except Exception:
            pass
        
        try:
            op.drop_index('idx_modification_user', table_name='photo_modifications')
        except Exception:
            pass
        
        try:
            op.drop_index('idx_modification_date', table_name='photo_modifications')
        except Exception:
            pass
        
        try:
            op.drop_index('idx_modification_type', table_name='photo_modifications')
        except Exception:
            pass
        
        try:
            op.drop_index('ix_photo_modifications_photo_id', table_name='photo_modifications')
        except Exception:
            pass
        
        # Rimuovi la tabella
        print("🗑️ Rimuovendo tabella photo_modifications...")
        op.drop_table('photo_modifications')
        
        print("✅ Tabella photo_modifications rimossa con successo!")
        print("📋 Tutti i dati storici sono stati preservati in user_activities")
        print("💡 Usa user_activities con photo_id per tracciare modifiche foto")
    else:
        print("ℹ️ Tabella photo_modifications non esiste, nessuna azione necessaria")


def downgrade() -> None:
    """Ricrea la tabella photo_modifications se necessario"""
    
    # Ricrea tabella
    op.create_table(
        'photo_modifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('photo_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('modified_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('modification_type', sa.String(100), nullable=False),
        sa.Column('field_changed', sa.String(100), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id']),
        sa.ForeignKeyConstraint(['modified_by'], ['users.id'])
    )
    
    # Ricrea indici
    op.create_index('idx_modification_photo', 'photo_modifications', ['photo_id'])
    op.create_index('idx_modification_user', 'photo_modifications', ['modified_by'])
    op.create_index('idx_modification_date', 'photo_modifications', ['created'])
    op.create_index('idx_modification_type', 'photo_modifications', ['modification_type'])
    op.create_index('ix_photo_modifications_photo_id', 'photo_modifications', ['photo_id'])
    
    # Ripristina dati da user_activities
    op.execute("""
        INSERT INTO photo_modifications (
            id,
            photo_id,
            modified_by,
            modification_type,
            field_changed,
            old_value,
            new_value,
            notes,
            created,
            updated
        )
        SELECT 
            gen_random_uuid(),
            ua.photo_id,
            ua.user_id,
            UPPER(REPLACE(ua.activity_type, 'photo_', '')),
            (ua.extra_data::json->>'field_changed'),
            (ua.extra_data::json->>'old_value'),
            (ua.extra_data::json->>'new_value'),
            ua.activity_desc,
            ua.created,
            ua.updated
        FROM user_activities ua
        WHERE ua.photo_id IS NOT NULL
        AND ua.extra_data::json->>'migrated_from' = 'photo_modifications'
    """)