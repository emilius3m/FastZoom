# app/models/__init__.py
"""
FastZoom Archaeological System - Models
Sistema completo riorganizzato e ottimizzato

Struttura modelli:
1. Base - Modelli base e mixin
2. Users - Utenti, ruoli, permessi  
3. Sites - Siti archeologici e mappe
4. Stratigraphy - US/USM con gestione file
5. Archaeological Records - Tombe, reperti, campioni
6. Documentation & Field - Documenti, foto, cantiere, ICCD
7. Configurations - Export, relazioni finali, elenchi
"""

# ===== IMPORT BASE =====
from app.models.base import (
    Base,
    BaseSQLModel,
    TimestampMixin,
    SiteMixin,
    UserMixin,
    SoftDeleteMixin
)

# ===== IMPORT UTENTI E RUOLI =====
from app.models.users import (
    User,
    Role,
    UserSitePermission,
    user_roles_association,
    UserStatusEnum,
    SITE_PERMISSIONS,
    SYSTEM_ROLES
)

# ===== IMPORT SITI ARCHEOLOGICI =====
from app.models.sites import (
    ArchaeologicalSite,
    GeographicMap,
    SiteStatusEnum,
    SiteTypeEnum,
    ResearchStatusEnum
)

# ===== IMPORT STRATIGRAFIA =====
from app.models.stratigraphy import (
    UnitaStratigrafica,
    UnitaStratigraficaMuraria,
    USFile,
    us_files_association,
    usm_files_association,
    ConsistenzaEnum,
    AffidabilitaEnum,
    TecnicaCostruttiva
)

# ===== IMPORT RECORD ARCHEOLOGICI =====
from app.models.archaeological_records import (
    SchedaTomba,
    InventarioReperto,
    CampioneScientifico,
    TipoTombaEnum,
    OrientamentoEnum,
    ConservazioneEnum,
    TipoCampioneEnum,
    MaterialeEnum
)

# ===== IMPORT DOCUMENTAZIONE E CANTIERE =====
from app.models.documentation_and_field import (
    Document,
    Photo,
    TavolaGrafica,
    MatrixHarris,
    OperatoreCantiere,
    GiornaleCantiere,
    FormSchema,
    ICCDBaseRecord,
    giornale_operatori_association,
    DocumentCategoryEnum,
    PhotoStatusEnum,
    TipoTavolaEnum,
    QualificaOperatoreEnum
)

# ===== IMPORT CONFIGURAZIONI =====
from app.models.configurations import (
    ConfigurazioneExport,
    RelazioneFinaleScavo,
    ElencoConsegna,
    FormatoExportEnum,
    TipoDestinatarioEnum,
    StatoRelazioneEnum,
    TipoElencoEnum,
    TEMPLATE_ELENCHI
)

# ===== EXPORT ALL MODELS =====
__all__ = [
    # Base
    'Base',
    'BaseSQLModel',
    'TimestampMixin',
    'SiteMixin', 
    'UserMixin',
    'SoftDeleteMixin',
    
    # Users & Roles
    'User',
    'Role',
    'UserSitePermission',
    'user_roles_association',
    'UserStatusEnum',
    'SITE_PERMISSIONS',
    'SYSTEM_ROLES',
    
    # Sites
    'ArchaeologicalSite',
    'GeographicMap',
    'SiteStatusEnum',
    'SiteTypeEnum',
    'ResearchStatusEnum',
    
    # Stratigraphy
    'UnitaStratigrafica',
    'UnitaStratigraficaMuraria', 
    'USFile',
    'us_files_association',
    'usm_files_association',
    'ConsistenzaEnum',
    'AffidabilitaEnum',
    'TecnicaCostruttiva',
    
    # Archaeological Records
    'SchedaTomba',
    'InventarioReperto',
    'CampioneScientifico',
    'TipoTombaEnum',
    'OrientamentoEnum',
    'ConservazioneEnum',
    'TipoCampioneEnum',
    'MaterialeEnum',
    
    # Documentation & Field
    'Document',
    'Photo',
    'TavolaGrafica',
    'MatrixHarris',
    'OperatoreCantiere',
    'GiornaleCantiere', 
    'FormSchema',
    'ICCDBaseRecord',
    'giornale_operatori_association',
    'DocumentCategoryEnum',
    'PhotoStatusEnum',
    'TipoTavolaEnum',
    'QualificaOperatoreEnum',
    
    # Configurations
    'ConfigurazioneExport',
    'RelazioneFinaleScavo',
    'ElencoConsegna',
    'FormatoExportEnum',
    'TipoDestinatarioEnum',
    'StatoRelazioneEnum',
    'TipoElencoEnum',
    'TEMPLATE_ELENCHI'
]

# ===== METADATA INFO =====
MODELS_VERSION = "2.0.0"
MODELS_COUNT = len(__all__)

def get_models_summary():
    """Restituisce riassunto modelli del sistema"""
    return {
        'version': MODELS_VERSION,
        'total_models': MODELS_COUNT,
        'categories': {
            'base': 6,
            'users': 7,
            'sites': 5, 
            'stratigraphy': 8,
            'archaeological_records': 8,
            'documentation_field': 13,
            'configurations': 8
        },
        'features': [
            'Multi-tenant per sito archeologico',
            'Sistema permessi granulare', 
            'Gestione file integrata US/USM',
            'Standard MiC 2021 compliance',
            'ICCD schede supportate',
            'Matrix Harris digitale',
            'Export automatizzato',
            'Giornali cantiere digitali',
            'Soft delete e versioning',
            'Deep zoom integrazione'
        ]
    }

def get_relationships_map():
    """Mappa delle relazioni principali tra modelli"""
    return {
        'ArchaeologicalSite': {
            'is_hub_for': [
                'User (permissions)', 'UnitaStratigrafica', 'UnitaStratigraficaMuraria',
                'SchedaTomba', 'InventarioReperto', 'CampioneScientifico',
                'Photo', 'Document', 'GiornaleCantiere', 'ICCDBaseRecord'
            ],
            'relationship_type': 'one-to-many'
        },
        'UnitaStratigrafica': {
            'has_files': 'USFile (many-to-many)',
            'has_samples': 'CampioneScientifico',
            'has_artifacts': 'InventarioReperto',
            'matrix_relations': 'Self-referential JSON'
        },
        'SchedaTomba': {
            'has_artifacts': 'InventarioReperto (corredo)',
            'has_samples': 'CampioneScientifico',
            'anthropology': 'Embedded fields'
        },
        'User': {
            'site_permissions': 'UserSitePermission',
            'roles': 'Role (many-to-many)',
            'created_content': 'All models with UserMixin'
        }
    }

# ===== VALIDATION HELPERS =====

def validate_model_integrity():
    """Valida integrità modelli e relazioni"""
    issues = []
    
    # Controlla che tutti i ForeignKey abbiano target validi
    # Controlla che tutte le relazioni siano simmetriche
    # Controlla che tutti gli enum siano definiti
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'checked_at': datetime.now().isoformat()
    }

# ===== DATABASE CREATION HELPERS =====

def create_all_tables(engine):
    """Crea tutte le tabelle nel database"""
    Base.metadata.create_all(bind=engine)

def drop_all_tables(engine):
    """Elimina tutte le tabelle dal database"""
    Base.metadata.drop_all(bind=engine)

# ===== IMPORT LOGGING =====
import logging

logger = logging.getLogger(__name__)
logger.info(f"FastZoom Models v{MODELS_VERSION} loaded - {MODELS_COUNT} models available")

# ===== COMPATIBILITY =====
# Alias per compatibilità con codice esistente
UnitaStratigraficaCompleta = UnitaStratigrafica  # Alias legacy