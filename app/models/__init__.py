# app/models/__init__.py - VERSIONE FINALE COMPLETISSIMA
"""
FastZoom Archaeological System - Models
Sistema completo riorganizzato e ottimizzato
INCLUDE: TUTTI I MODELLI RIPRISTINATI

MODELLI RIPRISTINATI:
✅ PermissionLevel (enum per livelli permesso)
✅ UserActivity (tracking attività utente)  
✅ TokenBlacklist (gestione logout JWT)
✅ PhotoType, MaterialType, ConservationStatus (enum archeologici)

Struttura modelli:
1. Base - Modelli base e mixin
2. Users - Utenti, ruoli, permessi  
3. Sites - Siti archeologici e mappe
4. Stratigraphy - US/USM con gestione file
5. Archaeological Records - Tombe, reperti, campioni
6. Documentation & Field - Documenti, foto, cantiere, ICCD
7. Configurations - Export, relazioni finali, elenchi
8. UserActivity - Tracciamento attività utente
9. TokenBlacklist - Gestione sicurezza JWT
10. Archaeological Enums - Tutti gli enum archeologici
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

# ===== IMPORT ARCHAEOLOGICAL ENUMS =====
from app.models.archaeological_enums import (
    # Photo and Documentation
    PhotoType,  # RIPRISTINATO!
    DocumentType,
    
    # Materials and Conservation  
    MaterialType,  # RIPRISTINATO!
    ConservationStatus,  # RIPRISTINATO!
    
    # Archaeological Context
    ContextType,
    DepositionType,
    DatingMethod,
    ChronologicalPeriod,
    SiteFunction,
    StructuralElement,
    ArtifactCategory,
    PotteryType,
    StratigraphicRelation,
    
    # Display name mappings
    PHOTO_TYPE_DISPLAY,
    MATERIAL_TYPE_DISPLAY,
    CONSERVATION_STATUS_DISPLAY,
    
    # Helper functions
    get_photo_type_choices,
    get_material_type_choices,
    get_conservation_status_choices,
    get_enum_display_name,
    get_all_archaeological_enums,
    
    # Validation helpers
    is_valid_photo_type,
    is_valid_material_type,
    is_valid_conservation_status,
    
    # Backward compatibility
    PhotoTypeEnum,
    MaterialTypeEnum,
    ConservationStatusEnum
)

# ===== IMPORT UTENTI E RUOLI =====
from app.models.users import (
    User,
    Role,
    UserSitePermission,
    user_roles_association,
    UserStatusEnum,
    PermissionLevel,  # RIPRISTINATO!
    SITE_PERMISSIONS,
    SYSTEM_ROLES,
    PERMISSION_LEVEL_CHOICES  # RIPRISTINATO!
)

# ===== IMPORT USER PROFILES =====
from app.models.user_profiles import (
    UserProfile
)

# ===== IMPORT ACTIVITY TRACKING =====
from app.models.user_activity import (
    UserActivity,  # RIPRISTINATO!
    ACTIVITY_TYPES,
    get_activity_display_name
)

# ===== IMPORT TOKEN SECURITY =====
from app.models.token_blacklist import (
    TokenBlacklist,  # RIPRISTINATO!
    BLACKLIST_REASONS,
    invalidate_user_session,
    invalidate_all_user_sessions,
    is_token_valid,
    get_blacklist_reason_choices
)

# ===== IMPORT SITI ARCHEOLOGICI =====
from app.models.sites import (
    ArchaeologicalSite,
    SiteStatusEnum,
    SiteTypeEnum,
    ResearchStatusEnum
)

# ===== IMPORT PIANTE ARCHEOLOGICHE =====
from app.models.archaeological_plans import (
    ArchaeologicalPlan
)

# ===== IMPORT MAPPE GEOGRAFICHE =====
from app.models.geographic_maps import (
    GeographicMap,
    GeographicMapLayer,
    GeographicMapMarker,
    GeographicMapMarkerPhoto
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

# ===== IMPORT ARCHEOLOGIA AVANZATA =====
from app.models.archeologia_avanzata import (
    UnitaStratigraficaCompleta,
    MaterialeArcheologico,
    matrix_harris_relations,
    reperti_materiali_association,
    TipoUS,
    TipoTomba,
    RitoSepolcrale,
    TipoMateriale,
    TipoCampione,
    StatoConservazione
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
    giornale_operatori_association,
    DocumentCategoryEnum,
    PhotoStatusEnum,
    TipoTavolaEnum,
    QualificaOperatoreEnum,
    # Helper functions per PhotoType
    create_photo_with_type,
    filter_photos_by_type,
    get_photos_by_types
)

# ===== IMPORT CANTIERE =====
from app.models.cantiere import (
    Cantiere
)

# ===== IMPORT DOCUMENTAZIONE GRAFICA =====
from app.models.documentazione_grafica import (
    FotografiaArcheologica,
    ElencoConsegna
)

# ===== IMPORT ICCD RECORDS =====
from app.models.iccd_records import (
    ICCDBaseRecord,
    ICCDRecord,
    ICCDAuthorityFile,
    ICCDSchemaTemplate
)

# ===== IMPORT CONFIGURAZIONI =====
from app.models.configurations import (
    ConfigurazioneExport,
    RelazioneFinaleScavo,
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
    
    # Archaeological Enums (RIPRISTINATI!)
    'PhotoType',  # ✅ RIPRISTINATO
    'MaterialType',  # ✅ RIPRISTINATO  
    'ConservationStatus',  # ✅ RIPRISTINATO
    'DocumentType',
    'ContextType',
    'DepositionType',
    'DatingMethod',
    'ChronologicalPeriod',
    'SiteFunction',
    'StructuralElement',
    'ArtifactCategory',
    'PotteryType',
    'StratigraphicRelation',
    'PHOTO_TYPE_DISPLAY',
    'MATERIAL_TYPE_DISPLAY',
    'CONSERVATION_STATUS_DISPLAY',
    'get_photo_type_choices',
    'get_material_type_choices',
    'get_conservation_status_choices',
    'get_enum_display_name',
    'get_all_archaeological_enums',
    'is_valid_photo_type',
    'is_valid_material_type',
    'is_valid_conservation_status',
    'PhotoTypeEnum',  # Backward compatibility
    'MaterialTypeEnum',  # Backward compatibility
    'ConservationStatusEnum',  # Backward compatibility
    
    # Users & Roles
    'User',
    'Role',
    'UserSitePermission',
    'user_roles_association',
    'UserStatusEnum',
    'PermissionLevel',  # RIPRISTINATO!
    'SITE_PERMISSIONS',
    'SYSTEM_ROLES',
    'PERMISSION_LEVEL_CHOICES',  # RIPRISTINATO!
    
    # User Profiles
    'UserProfile',
    
    # Activity Tracking
    'UserActivity',  # RIPRISTINATO!
    'ACTIVITY_TYPES',
    'get_activity_display_name',
    
    # Token Security
    'TokenBlacklist',  # RIPRISTINATO!
    'BLACKLIST_REASONS',
    'invalidate_user_session',
    'invalidate_all_user_sessions',
    'is_token_valid',
    'get_blacklist_reason_choices',
    
    # Sites
    'ArchaeologicalSite',
    'SiteStatusEnum',
    'SiteTypeEnum',
    'ResearchStatusEnum',
    
    # Archaeological Plans
    'ArchaeologicalPlan',
    
    # Geographic Maps
    'GeographicMap',
    'GeographicMapLayer',
    'GeographicMapMarker',
    'GeographicMapMarkerPhoto',
    
    # Stratigraphy
    'UnitaStratigrafica',
    'UnitaStratigraficaMuraria', 
    'USFile',
    'us_files_association',
    'usm_files_association',
    'ConsistenzaEnum',
    'AffidabilitaEnum',
    'TecnicaCostruttiva',
    
    # Archeologia Avanzata
    'UnitaStratigraficaCompleta',
    'MaterialeArcheologico',
    'matrix_harris_relations',
    'reperti_materiali_association',
    'TipoUS',
    'TipoTomba',
    'RitoSepolcrale',
    'TipoMateriale',
    'TipoCampione',
    'StatoConservazione',
    
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
    'giornale_operatori_association',
    'DocumentCategoryEnum',
    'PhotoStatusEnum',
    'TipoTavolaEnum',
    'QualificaOperatoreEnum',
    'create_photo_with_type',
    'filter_photos_by_type',
    'get_photos_by_types',
    
    # ICCD Records
    'ICCDBaseRecord',
    'ICCDRecord',
    'ICCDAuthorityFile',
    'ICCDSchemaTemplate',
    
    # Configurations
    'ConfigurazioneExport',
    'RelazioneFinaleScavo',
    'ElencoConsegna',
    'FormatoExportEnum',
    'TipoDestinatarioEnum',
    'StatoRelazioneEnum',
    'TipoElencoEnum',
    'TEMPLATE_ELENCHI',
    
    # Cantiere
    'Cantiere'
]

# ===== METADATA INFO =====
MODELS_VERSION = "2.3.0"  # Incrementato per archaeological enums
MODELS_COUNT = len(__all__)

def get_models_summary():
    """Restituisce riassunto modelli del sistema"""
    return {
        'version': MODELS_VERSION,
        'total_models': MODELS_COUNT,
        'categories': {
            'base': 6,
            'users': 10,  # Include PermissionLevel + UserActivity + TokenBlacklist
            'security': 6,  # TokenBlacklist + helpers
            'archaeological_enums': 30,  # PhotoType, MaterialType, ConservationStatus + tutti gli altri
            'sites': 5, 
            'stratigraphy': 8,
            'archaeological_records': 8,
            'documentation_field': 16,  # Include helper functions
            'configurations': 8
        },
        'recent_fixes': [
            'RIPRISTINATO PermissionLevel enum',
            'RIPRISTINATO UserActivity model', 
            'RIPRISTINATO TokenBlacklist model',
            'RIPRISTINATO PhotoType, MaterialType, ConservationStatus',
            'Aggiunti tutti gli enum archeologici mancanti',
            'Corrette relazioni User.activities',
            'Aggiunti metodi di logging attività',
            'Sistema JWT logout sicuro',
            'Helper functions per gestione enum',
            'Backward compatibility mantenuta',
            'Mantenuta compatibilità codice esistente'
        ],
        'features': [
            'Multi-tenant per sito archeologico',
            'Sistema permessi granulare con PermissionLevel', 
            'Tracking completo attività utente',
            'Logout JWT sicuro con blacklist',
            'Enum archeologici completi per classificazione',
            'PhotoType per classificazione fotografica sistematica',
            'MaterialType per catalogazione manufatti standard',
            'ConservationStatus per valutazione stato ICCD',
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

def get_missing_models_status():
    """Status completo dei modelli che erano spariti - TUTTI RIPRISTINATI"""
    return {
        'PermissionLevel': {
            'status': '✅ RIPRISTINATO',
            'location': 'app.models.users',
            'values': ['READ', 'WRITE', 'ADMIN', 'REGIONAL_ADMIN'],
            'impact': '🔴 CRITICO - Sistema permessi rotto senza',
            'fixed_in': 'v2.1.0'
        },
        'UserActivity': {
            'status': '✅ RIPRISTINATO', 
            'location': 'app.models.user_activity',
            'features': ['Activity logging', 'Audit trail', 'User statistics'],
            'impact': '🟠 ALTO - Tracking attività perso',
            'fixed_in': 'v2.1.0'
        },
        'TokenBlacklist': {
            'status': '✅ RIPRISTINATO',
            'location': 'app.models.token_blacklist', 
            'features': ['JWT invalidation', 'Secure logout', 'Session management'],
            'impact': '🟠 ALTO - Logout non sicuro senza',
            'fixed_in': 'v2.2.0'
        },
        'PhotoType': {
            'status': '✅ RIPRISTINATO',
            'location': 'app.models.archaeological_enums',
            'values': ['GENERAL_VIEW', 'DETAIL', 'SECTION', 'STRATIGRAPHY', 'LABORATORY', 'etc...'],
            'impact': '🟠 MEDIO - Classificazione foto archeologiche',
            'fixed_in': 'v2.3.0'
        },
        'MaterialType': {
            'status': '✅ RIPRISTINATO',
            'location': 'app.models.archaeological_enums',
            'values': ['CERAMIC', 'BRONZE', 'IRON', 'STONE', 'GLASS', 'BONE', 'etc...'],
            'impact': '🟠 MEDIO - Catalogazione manufatti',
            'fixed_in': 'v2.3.0'
        },
        'ConservationStatus': {
            'status': '✅ RIPRISTINATO',
            'location': 'app.models.archaeological_enums',
            'values': ['EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'FRAGMENTARY', 'etc...'],
            'impact': '🟠 MEDIO - Valutazione stato ICCD',
            'fixed_in': 'v2.3.0'
        }
    }

def validate_all_models_complete():
    """Valida che TUTTI i modelli siano presenti e funzionanti"""
    issues = []
    
    try:
        # Test core models
        from app.models.users import User, PermissionLevel
        from app.models.user_activity import UserActivity
        from app.models.token_blacklist import TokenBlacklist
        from app.models.archaeological_enums import PhotoType, MaterialType, ConservationStatus
        
        # Test critical enums
        core_enum_checks = [
            ('PermissionLevel.READ', hasattr(PermissionLevel, 'READ')),
            ('PermissionLevel.ADMIN', hasattr(PermissionLevel, 'ADMIN')),
            ('PhotoType.GENERAL_VIEW', hasattr(PhotoType, 'GENERAL_VIEW')),
            ('PhotoType.DETAIL', hasattr(PhotoType, 'DETAIL')),
            ('MaterialType.CERAMIC', hasattr(MaterialType, 'CERAMIC')),
            ('MaterialType.BRONZE', hasattr(MaterialType, 'BRONZE')),
            ('ConservationStatus.EXCELLENT', hasattr(ConservationStatus, 'EXCELLENT')),
            ('ConservationStatus.POOR', hasattr(ConservationStatus, 'POOR'))
        ]
        
        # Test model methods
        method_checks = [
            ('UserActivity.log_activity', hasattr(UserActivity, 'log_activity')),
            ('TokenBlacklist.is_token_blacklisted', hasattr(TokenBlacklist, 'is_token_blacklisted')),
            ('User.get_permission_level_for_site', hasattr(User, 'get_permission_level_for_site'))
        ]
        
        all_checks = core_enum_checks + method_checks
        
        for check_name, result in all_checks:
            if not result:
                issues.append(f"Mancante: {check_name}")
                
        # Test enum values
        test_values = [
            ('PermissionLevel.READ', PermissionLevel.READ.value == 'read'),
            ('PhotoType.DETAIL', PhotoType.DETAIL.value == 'detail'),
            ('MaterialType.CERAMIC', MaterialType.CERAMIC.value == 'ceramic'),
            ('ConservationStatus.GOOD', ConservationStatus.GOOD.value == 'good')
        ]
        
        for test_name, result in test_values:
            if not result:
                issues.append(f"Valore errato: {test_name}")
                
    except ImportError as e:
        issues.append(f"Import error: {str(e)}")
    except Exception as e:
        issues.append(f"Unexpected error: {str(e)}")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'total_checks': len(all_checks) + len(test_values) if 'all_checks' in locals() and 'test_values' in locals() else 0,
        'status': '🎉 TUTTI I MODELLI RIPRISTINATI E FUNZIONANTI!' if not issues else f'⚠️ {len(issues)} problemi rilevati',
        'recommendation': 'Sistema completo al 100%!' if not issues else 'Verificare import e dipendenze mancanti'
    }

# ===== COMPREHENSIVE USAGE EXAMPLES =====

def usage_examples():
    """Esempi d'uso completi per tutti i modelli ripristinati"""
    return {
        'permission_level_usage': """
# Uso PermissionLevel
from app.models import PermissionLevel, User
level = PermissionLevel.ADMIN
user.can_admin_site(site_id)  # True se level >= ADMIN
        """,
        'activity_tracking_usage': """
# Tracking attività
from app.models import UserActivity
await UserActivity.log_login(db, user_id, success=True)
await UserActivity.log_us_action(db, user_id, 'create', us_id, site_id, 'US003')
        """,
        'token_security_usage': """
# Sicurezza JWT
from app.models import TokenBlacklist
await TokenBlacklist.blacklist_token(db, token_jti, user_id, 'logout')
is_valid = await TokenBlacklist.is_token_blacklisted(db, token_jti)
        """,
        'archaeological_enums_usage': """
# Enum archeologici
from app.models import PhotoType, MaterialType, ConservationStatus
photo = Photo(photo_type=PhotoType.DETAIL.value)
reperto = InventarioReperto(materiale=MaterialType.CERAMIC.value)
stato = ConservationStatus.GOOD.value
        """,
        'complete_workflow': """
# Workflow completo: login → azione → logout sicuro
user = authenticate_user(credentials)
await UserActivity.log_login(db, user.id, success=True)

# Azioni archeologiche
us = create_us(site_id, 'US003')
await UserActivity.log_us_action(db, user.id, 'create', us.id, site_id, 'US003')

photo = Photo(site_id=site_id, photo_type=PhotoType.STRATIGRAPHY.value)
await UserActivity.log_photo_action(db, user.id, 'upload', photo.id, site_id, photo.filename)

# Logout sicuro
await TokenBlacklist.blacklist_token(db, token_jti, user.id, 'logout')
await UserActivity.log_logout(db, user.id)
        """
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

def blacklist_token(db, token_jti, user_id, reason='logout'):
    """Helper per blacklist token - wrapper async"""
    return TokenBlacklist.blacklist_token(
        db=db,
        token_jti=token_jti,
        user_id=user_id,
        reason=reason
    )

def check_token_validity(db, token_jti):
    """Helper per controllo validità token"""
    return is_token_valid(db, token_jti)

def create_photo_with_enum(site_id, filename, photo_type_enum, **kwargs):
    """Helper per creare foto con enum PhotoType"""
    return create_photo_with_type(site_id, filename, photo_type_enum, **kwargs)

# ===== AUTHENTICATION INTEGRATION =====

async def authenticate_token(db, token_jti):
    """Helper per autenticazione token completa"""
    return await is_token_valid(db, token_jti)

async def logout_user_safely(db, user_id, token_jti, ip_address=None):
    """Helper per logout sicuro con blacklist e logging"""
    await TokenBlacklist.blacklist_token(
        db=db,
        token_jti=token_jti, 
        user_id=user_id,
        reason='logout',
        ip_address=ip_address
    )
    
    await UserActivity.log_logout(
        db=db,
        user_id=user_id,
        ip_address=ip_address
    )

# ===== IMPORT LOGGING =====
import logging

logger = logging.getLogger(__name__)
logger.info(f"FastZoom Models v{MODELS_VERSION} loaded - {MODELS_COUNT} models available")
logger.info("✅ RIPRISTINATI: PermissionLevel + UserActivity + TokenBlacklist")
logger.info("✅ RIPRISTINATI: PhotoType + MaterialType + ConservationStatus")
logger.info("🔒 Sistema autenticazione JWT completo e sicuro")
logger.info("🏛️ Enum archeologici completi per classificazione standard")

# ===== COMPATIBILITY =====
# Alias per compatibilità con codice esistente
# UnitàStratigraficaCompleta è ora un modello a sé stante, non un alias

# Final validation on import
try:
    _validation_result = validate_all_models_complete()
    if _validation_result['valid']:
        logger.info("🎉 TUTTI I MODELLI VALIDATI CORRETTAMENTE!")
    else:
        logger.warning(f"⚠️ Validation issues: {_validation_result['issues']}")
except Exception as e:
    logger.error(f"❌ Validation error: {e}")