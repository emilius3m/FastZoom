# In alembic/versions/xxx_add_sites_data.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column
from sqlalchemy.sql import func
from uuid import uuid4

# Crea una rappresentazione della tabella per il bulk insert
sites_table = table('archaeological_site',
    column('id', sa.UUID),
    column('site_name', sa.String),
    column('site_code', sa.String), 
    column('region', sa.String),
    column('created', sa.DateTime),
    column('updated', sa.DateTime)
)

def upgrade():
    # Prima crea la tabella (se necessario)
    # op.create_table(...)
    
    # Poi inserisci i dati di seed
    op.bulk_insert(sites_table, [
        {
            'id': str(uuid4()),
            'site_name': 'Pompei',
            'site_code': 'POMPEI_001', 
            'region': 'Campania',
            'created': func.now(),
            'updated': func.now()
        },
        {
            'id': str(uuid4()),
            'site_name': 'Colosseo',
            'site_code': 'ROMA_COL',
            'region': 'Lazio', 
            'created': func.now(),
            'updated': func.now()
        },
        {
            'id': str(uuid4()),
            'site_name': 'Valle dei Templi',
            'site_code': 'AGRIGENTO_001',
            'region': 'Sicilia',
            'created': func.now(),
            'updated': func.now()
        }
    ])

def downgrade():
    # Rimuovi i dati se necessario
    op.execute("DELETE FROM archaeological_site WHERE site_code IN ('POMPEI_001', 'ROMA_COL', 'AGRIGENTO_001')")
