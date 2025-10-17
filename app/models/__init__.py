# app/models/__init__.py - VERSIONE CORRETTA CON UserActivity
"""
FastZoom Archaeological System - Models
Sistema completo riorganizzato e ottimizzato
INCLUDE: PermissionLevel + UserActivity RIPRISTINATI

Struttura modelli:
1. Base - Modelli base e mixin
2. Users - Utenti, ruoli, permessi
3. Sites - Siti archeologici e mappe
4. Stratigraphy - US/USM con gestione file
5. Archaeological Records - Tombe, reperti, campioni
6. Documentation & Field - Documenti, foto, cantiere, ICCD
7. Configurations - Export, relazioni finali, elenchi
8. UserActivity - Tracciamento attività utente RIPRISTINATO
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
from app.models import (
    User,
    Role,
    UserSitePermission,
    user_roles_association,
    UserStatusEnum,
    PermissionLevel,  # RIPRISTINATO!
    TokenBlacklist,
    SITE_PERMISSIONS,
    SYSTEM_ROLES,
    PERMISSION_LEVEL_CHOICES  # RIPRISTINATO!
)

# ===== IMPORT ACTIVITY TRACKING =====
from app.models.user_activity import (
    UserActivity,  # RIPRISTINATO!
    ACTIVITY_TYPES,
    get_activity_display_name
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
    'PermissionLevel',  # RIPRISTINATO!
'TokenBlacklist',
    'SITE_PERMISSIONS',
    'SYSTEM_ROLES',
    'PERMISSION_LEVEL_CHOICES',  # RIPRISTINATO!

    # Activity Tracking
    'UserActivity',  # RIPRISTINATO!
    'ACTIVITY_TYPES',
    'get_activity_display_name',

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
MODELS_VERSION = "2.1.0"  # Incrementato per correzioni
MODELS_COUNT = len(__all__)


def get_models_summary():
    """Restituisce riassunto modelli del sistema"""
    return {
        'version': MODELS_VERSION,
        'total_models': MODELS_COUNT,
        'categories': {
            'base': 6,
            'users': 10,  # Include PermissionLevel + UserActivity
            'sites': 5,
            'stratigraphy': 8,
            'archaeological_records': 8,
            'documentation_field': 13,
            'configurations': 8
        },
        'recent_fixes': [
            'RIPRISTINATO PermissionLevel enum',
            'RIPRISTINATO UserActivity model',
            'Corrette relazioni User.activities',
            'Aggiunti metodi di logging attività',
            'Mantenuta compatibilità codice esistente'
        ],
        'features': [
            'Multi-tenant per sito archeologico',
            'Sistema permessi granulare con PermissionLevel',
            'Tracking completo attività utente',
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


def get_missing_models_recovered():
    """Lista modelli recuperati che erano spariti"""
    return {
        'PermissionLevel': {
            'status': 'RIPRISTINATO',
            'location': 'app.models.users',
            'values': ['READ', 'WRITE', 'ADMIN', 'REGIONAL_ADMIN'],
            'impact': 'CRITICO - Sistema permessi rotto senza'
        },
        'UserActivity': {
            'status': 'RIPRISTINATO',
            'location': 'app.models.user_activity',
            'features': ['Activity logging', 'Audit trail', 'User statistics'],
            'impact': 'ALTO - Tracking attività perso'
        }
    }


def validate_model_relationships():
    """Valida che tutte le relazioni siano corrette dopo ripristino"""
    issues = []

    # Verifica User.activities relationship
    from app.models import User
    from app.models.user_activity import UserActivity

    try:
        # Controlla che User abbia la relazione activities
        if not hasattr(User, 'activities'):
            issues.append("User.activities relationship mancante")

        # Controlla che UserActivity abbia relazione user
        if not hasattr(UserActivity, 'user'):
            issues.append("UserActivity.user relationship mancante")

    except ImportError as e:
        issues.append(f"Import error: {str(e)}")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'recommendation': 'Aggiorna User model per includere activities relationship' if issues else 'OK'
    }


# ===== COMPATIBILITY HELPERS =====

def get_permission_level_choices():
    """Helper per form choices compatibile con Django/FastAPI"""
    return PERMISSION_LEVEL_CHOICES


def log_user_activity(db, user_id, activity_type, description=None, **kwargs):
    """Helper per logging attività - wrapper async"""
    return UserActivity.log_activity(
        db=db,
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        **kwargs
    )


# ===== IMPORT LOGGING =====
import logging

logger = logging.getLogger(__name__)
logger.info(f"FastZoom Models v{MODELS_VERSION} loaded - {MODELS_COUNT} models available")
logger.info("✅ RIPRISTINATI: PermissionLevel + UserActivity")

# ===== COMPATIBILITY =====
# Alias per compatibilità con codice esistente
UnitaStratigraficaCompleta = UnitaStratigrafica  # Alias legacy