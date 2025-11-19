# app/utils/enum_mappings.py
"""
Centralized mapping system for Italian to English enum conversions
Provides comprehensive mappings for all archaeological enums used in FastZoom
"""

from typing import Dict, Optional, Any, Type
from loguru import logger

# Import all enum types that need conversion
from app.models import (
    PhotoType, MaterialType, ConservationStatus,
    DocumentType, ContextType, DepositionType,
    DatingMethod, ChronologicalPeriod, SiteFunction,
    StructuralElement, ArtifactCategory, PotteryType,
    StratigraphicRelation
)


class EnumMappingError(Exception):
    """Exception raised when enum mapping fails"""
    pass


class EnumConverter:
    """
    Centralized enum converter with Italian to English mappings
    Supports all archaeological enums used in the FastZoom system
    """
    
    # ===== PHOTO TYPE MAPPINGS =====
    PHOTO_TYPE_MAPPINGS: Dict[str, str] = {
        # Italian to English mappings for PhotoType
        'vista generale': 'general_view',
        'vista generale del sito': 'general_view',
        'vista complessiva': 'general_view',
        'panoramica': 'general_view',
        'panoramico': 'general_view',
        
        'dettaglio': 'detail',
        'dettagliata': 'detail',
        'particolare': 'detail',
        'particolare tecnico': 'detail',
        'macro': 'detail',
        'macrofotografia': 'detail',
        
        'sezione': 'section',
        'sezione stratigrafica': 'section',
        'profilo': 'section',
        'profilo stratigrafico': 'section',
        
        'disegno sovrapposto': 'drawing_overlay',
        'disegno sovrapposto fotografico': 'drawing_overlay',
        'fotografia con disegno': 'drawing_overlay',
        'rilievo sovrapposto': 'drawing_overlay',
        
        'pre-restauro': 'before_restoration',
        'prima del restauro': 'before_restoration',
        'pre restauro': 'before_restoration',
        'stato pre-restauro': 'before_restoration',
        
        'post-restauro': 'after_restoration',
        'dopo il restauro': 'after_restoration',
        'post restauro': 'after_restoration',
        'stato post-restauro': 'after_restoration',
        
        'avanzamento scavo': 'excavation_progress',
        'progress scavo': 'excavation_progress',
        'lavori in corso': 'excavation_progress',
        'scavo in corso': 'excavation_progress',
        
        'stratigrafia': 'stratigraphy',
        'documentazione stratigrafica': 'stratigraphy',
        'analisi stratigrafica': 'stratigraphy',
        'matrix harris': 'stratigraphy',
        
        'contesto rinvenimento': 'find_context',
        'contesto di rinvenimento': 'find_context',
        'contesto archeologico': 'find_context',
        'in situ': 'find_context',
        
        'laboratorio': 'laboratory',
        'analisi di laboratorio': 'laboratory',
        'studio laboratorio': 'laboratory',
        'ricerca laboratorio': 'laboratory',
        
        'archivio': 'archive',
        'documentazione archivio': 'archive',
        'foto archivio': 'archive',
        'archivistica': 'archive',
        
        'di lavoro': 'working',
        'lavorazione': 'working',
        'documentazione lavoro': 'working',
        'tecnica': 'working',
        
        'pubblicazione': 'publication',
        'per pubblicazione': 'publication',
        'editoriale': 'publication',
        'divulgazione': 'publication',
        
        # 🔧 FIX: Add English fallback mappings for common shorthand values
        'general': 'general_view',           # Common shorthand for general_view
        'generale': 'general_view',          # Italian fallback
        'vista': 'general_view',             # Single word fallback
        'panoramic': 'general_view',         # English typo fallback
        
        'detail shot': 'detail',             # English fallback
        'close-up': 'detail',                # English fallback
        'macro shot': 'detail',              # English fallback
        
        'stratigraphic': 'stratigraphy',     # English fallback
        'strat': 'stratigraphy',             # Abbreviation fallback
        
        'excavation': 'excavation_progress', # English fallback
        'progress': 'excavation_progress',   # English fallback
        
        'context': 'find_context',           # English fallback
        'find': 'find_context',              # English fallback
        
        'lab': 'laboratory',                 # Abbreviation fallback
        'analysis': 'laboratory',            # English fallback
    }
    
    # ===== MATERIAL TYPE MAPPINGS =====
    MATERIAL_TYPE_MAPPINGS: Dict[str, str] = {
        # Italian to English mappings for MaterialType
        'ceramica': 'ceramic',
        'ceramico': 'ceramic',
        'terracotta': 'terracotta',
        'cotto': 'terracotta',
        'vasellame': 'ceramic',
        
        'bronzo': 'bronze',
        'bronzo antico': 'bronze',
        'lega bronzo': 'bronze',
        'bronzeo': 'bronze',
        
        'ferro': 'iron',
        'ferro battuto': 'iron',
        'ferro forgiato': 'iron',
        'ferroso': 'iron',
        
        'pietra': 'stone',
        'litico': 'stone',
        'pietra naturale': 'stone',
        'materiale lapideo': 'stone',
        
        'marmo': 'marble',
        'marmoreo': 'marble',
        'marmo bianco': 'marble',
        'marmo colorato': 'marble',
        
        'vetro': 'glass',
        'vetroso': 'glass',
        'vetro cotto': 'glass',
        'fragmente di vetro': 'glass',
        
        'osso': 'bone',
        'ossa': 'bone',
        'materiale osseo': 'bone',
        'osteologico': 'bone',
        
        'legno': 'wood',
        'ligneo': 'wood',
        'materiale legnoso': 'wood',
        'travi di legno': 'wood',
        
        'oro': 'gold',
        'aureo': 'gold',
        'materiale aureo': 'gold',
        'laminato oro': 'gold',
        
        'argento': 'silver',
        'argentato': 'silver',
        'materiale argenteo': 'silver',
        'laminato argento': 'silver',
        
        'piombo': 'lead',
        'piombato': 'lead',
        'materiale plumbeo': 'lead',
        
        'rame': 'copper',
        'ramato': 'copper',
        'materiale rameo': 'copper',
        'lega di rame': 'copper',
        
        'stucco': 'stucco',
        'intonaco': 'plaster',
        'intonaco decorativo': 'plaster',
        'rivestimento': 'plaster',
        
        'malta': 'mortar',
        'calcestruzzo': 'concrete',
        'cemento': 'concrete',
        
        'tegola': 'tile',
        'mattone': 'tile',
        'laterizio': 'tile',
        'materiale laterizio': 'tile',
        
        'mosaico': 'mosaic',
        'tessera musiva': 'mosaic',
        'pavimento musivo': 'mosaic',
        
        'tessuto': 'fabric',
        'tessile': 'fabric',
        'materiale tessile': 'fabric',
        'fibra tessile': 'fabric',
        
        'cuoio': 'leather',
        'pelle': 'leather',
        'materiale cuoio': 'leather',
        
        'ambra': 'amber',
        'resina fossile': 'amber',
        
        'avorio': 'ivory',
        'materiale avorio': 'ivory',
        
        'corallo': 'coral',
        'materiale corallo': 'coral',
        
        'lega metallica': 'metal_composite',
        'lega': 'metal_composite',
        'composito': 'composite',
        'materiale composito': 'composite',
        
        'organico': 'organic',
        'materiale organico': 'organic',
        'resti organici': 'organic',
        
        'altro': 'other',
        'materiale non identificato': 'other',
        'sconosciuto': 'other',
        
        # 🔧 FIX: Add English fallback mappings for common shorthand values
        'pottery': 'ceramic',              # English fallback
        'ceramic': 'ceramic',              # Direct English match
        'pot': 'ceramic',                  # English fallback
        
        'metal': 'metal_composite',        # English fallback
        'bronze': 'bronze',                # Direct English match
        'iron': 'iron',                    # Direct English match
        'steel': 'iron',                   # English fallback
        
        'stone': 'stone',                  # Direct English match
        'rock': 'stone',                   # English fallback
        'marble': 'marble',                # Direct English match
        
        'glass': 'glass',                  # Direct English match
        'wood': 'wood',                    # Direct English match
        'bone': 'bone',                    # Direct English match
        
        'gold': 'gold',                    # Direct English match
        'silver': 'silver',                # Direct English match
        'lead': 'lead',                    # Direct English match
        'copper': 'copper',                # Direct English match
        
        'unknown': 'other',                # English fallback
        'misc': 'other',                   # English fallback
        'various': 'other',                # English fallback
    }
    
    # ===== CONSERVATION STATUS MAPPINGS =====
    CONSERVATION_STATUS_MAPPINGS: Dict[str, str] = {
        # Italian to English mappings for ConservationStatus
        'eccellente': 'excellent',
        'ottimo': 'excellent',
        'perfetto': 'excellent',
        'integro': 'excellent',
        
        'buono': 'good',
        'discreto': 'fair',
        'soddisfacente': 'fair',
        'accettabile': 'fair',
        
        'cattivo': 'poor',
        'scadente': 'poor',
        'deteriorato': 'poor',
        
        'pessimo': 'very_poor',
        'molto cattivo': 'very_poor',
        'gravemente danneggiato': 'very_poor',
        
        'frammentario': 'fragmentary',
        'frammentato': 'fragmentary',
        'incompleto': 'incomplete',
        'parziale': 'incomplete',
        
        'restaurato': 'restored',
        'con restauro': 'restored',
        'restaurato recentemente': 'restored',
        
        'ricostruito': 'reconstructed',
        'ricostruzione': 'reconstructed',
        'integrato': 'reconstructed',
        
        'perduto': 'lost',
        'scomparso': 'lost',
        'mancante': 'missing',
        'assente': 'missing',
        
        'danneggiato': 'damaged',
        'lesionato': 'damaged',
        'deteriorato': 'damaged',
        
        'incompleto': 'incomplete',
        'parziale': 'incomplete',
        'frammentario': 'fragmentary',
        
        # 🔧 FIX: Add English fallback mappings for common shorthand values
        'excellent': 'excellent',           # Direct English match
        'perfect': 'excellent',            # English fallback
        'mint': 'excellent',               # English fallback
        'pristine': 'excellent',           # English fallback
        
        'good': 'good',                    # Direct English match
        'fine': 'good',                    # English fallback
        'well preserved': 'good',          # English fallback
        
        'fair': 'fair',                    # Direct English match
        'average': 'fair',                 # English fallback
        'moderate': 'fair',                # English fallback
        'ok': 'fair',                      # English fallback
        
        'poor': 'poor',                    # Direct English match
        'bad': 'poor',                     # English fallback
        'damaged': 'poor',                 # English fallback
        'worn': 'poor',                    # English fallback
        
        'very poor': 'very_poor',          # English fallback
        'terrible': 'very_poor',           # English fallback
        'critical': 'very_poor',           # English fallback
        
        'fragmentary': 'fragmentary',      # Direct English match
        'fragmented': 'fragmentary',       # English fallback
        'incomplete': 'incomplete',        # Direct English match
        'partial': 'incomplete',           # English fallback
        
        'restored': 'restored',            # Direct English match
        'repaired': 'restored',            # English fallback
        'conserved': 'restored',           # English fallback
        
        'reconstructed': 'reconstructed',  # Direct English match
        'rebuilt': 'reconstructed',        # English fallback
        'reconstructed': 'reconstructed',  # Direct English match
        
        'lost': 'lost',                    # Direct English match
        'missing': 'missing',              # Direct English match
        'absent': 'missing',               # English fallback
        
        'damaged': 'damaged',              # Direct English match
        'broken': 'damaged',               # English fallback
        'injured': 'damaged',              # English fallback
    }
    
    # ===== DOCUMENT TYPE MAPPINGS =====
    DOCUMENT_TYPE_MAPPINGS: Dict[str, str] = {
        'relazione': 'relazione',
        'rapporto': 'rapporto',
        'relazione di scavo': 'relazione',
        
        'planimetria': 'planimetria',
        'pianta': 'planimetria',
        'planimetria topografica': 'planimetria',
        
        'sezione': 'sezione',
        'profilo': 'sezione',
        'sezione stratigrafica': 'sezione',
        
        'prospetto': 'prospetto',
        'elevazione': 'prospetto',
        'vista laterale': 'prospetto',
        
        'disegno': 'disegno',
        'rilievo': 'disegno',
        'disegno tecnico': 'disegno',
        
        'fotografia': 'fotografia',
        'foto': 'fotografia',
        'immagine': 'fotografia',
        
        'autorizzazione': 'autorizzazione',
        'permesso': 'autorizzazione',
        'concessione': 'autorizzazione',
        
        'bibliografia': 'bibliografia',
        'riferimento bibliografico': 'bibliografia',
        'fonte bibliografica': 'bibliografia',
        
        'catalogo': 'catalogo',
        'inventario': 'inventario',
        'elenco': 'catalogo',
        
        'altro': 'altro',
        'vario': 'altro',
        'diverso': 'altro'
    }
    
    # ===== OTHER ENUM MAPPINGS =====
    # Add mappings for other enums as needed
    CONTEXT_TYPE_MAPPINGS: Dict[str, str] = {
        'primario': 'primary',
        'secondario': 'secondary',
        'sconvolto': 'disturbed',
        'misto': 'mixed',
        'ridepositato': 'redeposited',
        'sconosciuto': 'unknown'
    }
    
    DEPOSITION_TYPE_MAPPINGS: Dict[str, str] = {
        'intenzionale': 'intentional',
        'accidentale': 'accidental',
        'naturale': 'natural',
        'rituale': 'ritual',
        'funerario': 'funerary',
        'votivo': 'votive',
        'sconosciuto': 'unknown'
    }
    
    # ===== ENUM CLASS MAPPINGS =====
    ENUM_CLASS_MAPPINGS: Dict[Type, Dict[str, str]] = {
        PhotoType: PHOTO_TYPE_MAPPINGS,
        MaterialType: MATERIAL_TYPE_MAPPINGS,
        ConservationStatus: CONSERVATION_STATUS_MAPPINGS,
        DocumentType: DOCUMENT_TYPE_MAPPINGS,
        ContextType: CONTEXT_TYPE_MAPPINGS,
        DepositionType: DEPOSITION_TYPE_MAPPINGS,
        # Add other enum mappings as needed
    }
    
    @classmethod
    def convert_to_enum(cls, enum_class: Type, value: Any) -> Optional[Any]:
        """
        Convert Italian value to enum instance
        
        Args:
            enum_class: The enum class to convert to
            value: The Italian value to convert
            
        Returns:
            Enum instance or None if conversion fails
        """
        if value is None:
            return None
            
        if isinstance(value, enum_class):
            return value
            
        if not isinstance(value, str):
            logger.warning(f"Cannot convert non-string value {value} to {enum_class.__name__}")
            return None
            
        # Normalize the input value
        normalized_value = value.lower().strip()
        
        # Try direct conversion first
        try:
            return enum_class(normalized_value)
        except ValueError:
            pass
            
        # Try mapping conversion
        mappings = cls.ENUM_CLASS_MAPPINGS.get(enum_class, {})
        if normalized_value in mappings:
            english_value = mappings[normalized_value]
            try:
                enum_instance = enum_class(english_value)
                logger.info(f"Converted Italian '{value}' to {enum_class.__name__}.{enum_instance.name}")
                return enum_instance
            except ValueError as e:
                logger.error(f"Failed to create {enum_class.__name__} from mapped value '{english_value}': {e}")
        
        # Try partial matching for PhotoType
        if enum_class == PhotoType:
            return cls._partial_match_photo_type(normalized_value)
            
        # Try partial matching for MaterialType
        if enum_class == MaterialType:
            return cls._partial_match_material_type(normalized_value)
            
        # Try partial matching for ConservationStatus
        if enum_class == ConservationStatus:
            return cls._partial_match_conservation_status(normalized_value)
        
        logger.warning(f"Unable to convert '{value}' to {enum_class.__name__}")
        return None
    
    @classmethod
    def _partial_match_photo_type(cls, value: str) -> Optional[PhotoType]:
        """Try partial matching for PhotoType"""
        # Check for keywords in the value
        if any(keyword in value for keyword in ['vista', 'generale', 'panoramica']):
            return PhotoType.GENERAL_VIEW
        elif any(keyword in value for keyword in ['dettaglio', 'particolare', 'macro']):
            return PhotoType.DETAIL
        elif any(keyword in value for keyword in ['sezione', 'profilo']):
            return PhotoType.SECTION
        elif any(keyword in value for keyword in ['disegno', 'rilievo']):
            return PhotoType.DRAWING_OVERLAY
        elif any(keyword in value for keyword in ['restauro', 'restaurato']):
            return PhotoType.BEFORE_RESTORATION  # Default to before_restoration
        elif any(keyword in value for keyword in ['scavo', 'lavoro']):
            return PhotoType.EXCAVATION_PROGRESS
        elif any(keyword in value for keyword in ['stratigraf', 'matrix']):
            return PhotoType.STRATIGRAPHY
        elif any(keyword in value for keyword in ['contesto', 'rinvenimento']):
            return PhotoType.FIND_CONTEXT
        elif any(keyword in value for keyword in ['laboratorio', 'analisi']):
            return PhotoType.LABORATORY
        elif any(keyword in value for keyword in ['archivio', 'documentazione']):
            return PhotoType.ARCHIVE
        elif any(keyword in value for keyword in ['lavorazione', 'tecnica']):
            return PhotoType.WORKING
        elif any(keyword in value for keyword in ['pubblicazione', 'divulgazione']):
            return PhotoType.PUBLICATION
        return None
    
    @classmethod
    def _partial_match_material_type(cls, value: str) -> Optional[MaterialType]:
        """Try partial matching for MaterialType"""
        if any(keyword in value for keyword in ['ceramica', 'ceramico', 'cotto']):
            return MaterialType.CERAMIC
        elif any(keyword in value for keyword in ['bronzo', 'bronzeo']):
            return MaterialType.BRONZE
        elif any(keyword in value for keyword in ['ferro', 'ferroso']):
            return MaterialType.IRON
        elif any(keyword in value for keyword in ['pietra', 'litico', 'lapideo']):
            return MaterialType.STONE
        elif any(keyword in value for keyword in ['marmo', 'marmoreo']):
            return MaterialType.MARBLE
        elif any(keyword in value for keyword in ['vetro', 'vetroso']):
            return MaterialType.GLASS
        elif any(keyword in value for keyword in ['osso', 'ossa', 'osteologico']):
            return MaterialType.BONE
        elif any(keyword in value for keyword in ['legno', 'ligneo']):
            return MaterialType.WOOD
        elif any(keyword in value for keyword in ['oro', 'aureo']):
            return MaterialType.GOLD
        elif any(keyword in value for keyword in ['argento', 'argentato']):
            return MaterialType.SILVER
        elif any(keyword in value for keyword in ['piombo', 'plumbeo']):
            return MaterialType.LEAD
        elif any(keyword in value for keyword in ['rame', 'rameo']):
            return MaterialType.COPPER
        elif any(keyword in value for keyword in ['terracotta', 'laterizio']):
            return MaterialType.TERRACOTTA
        elif any(keyword in value for keyword in ['stucco']):
            return MaterialType.STUCCO
        elif any(keyword in value for keyword in ['mosaico', 'musivo']):
            return MaterialType.MOSAIC
        elif any(keyword in value for keyword in ['tessuto', 'tessile']):
            return MaterialType.FABRIC
        elif any(keyword in value for keyword in ['cuoio', 'pelle']):
            return MaterialType.LEATHER
        elif any(keyword in value for keyword in ['ambra']):
            return MaterialType.AMBER
        elif any(keyword in value for keyword in ['avorio']):
            return MaterialType.IVORY
        elif any(keyword in value for keyword in ['corallo']):
            return MaterialType.CORAL
        elif any(keyword in value for keyword in ['intonaco']):
            return MaterialType.PLASTER
        elif any(keyword in value for keyword in ['malta']):
            return MaterialType.MORTAR
        elif any(keyword in value for keyword in ['calcestruzzo', 'cemento']):
            return MaterialType.CONCRETE
        elif any(keyword in value for keyword in ['tegola', 'mattone']):
            return MaterialType.TILE
        elif any(keyword in value for keyword in ['lega', 'metallico']):
            return MaterialType.METAL_COMPOSITE
        elif any(keyword in value for keyword in ['composito']):
            return MaterialType.COMPOSITE
        elif any(keyword in value for keyword in ['organico']):
            return MaterialType.ORGANIC
        elif any(keyword in value for keyword in ['altro', 'sconosciuto']):
            return MaterialType.OTHER
        return None
    
    @classmethod
    def _partial_match_conservation_status(cls, value: str) -> Optional[ConservationStatus]:
        """Try partial matching for ConservationStatus"""
        if any(keyword in value for keyword in ['eccellente', 'ottimo', 'perfetto', 'integro']):
            return ConservationStatus.EXCELLENT
        elif any(keyword in value for keyword in ['buono']):
            return ConservationStatus.GOOD
        elif any(keyword in value for keyword in ['discreto', 'soddisfacente', 'accettabile']):
            return ConservationStatus.FAIR
        elif any(keyword in value for keyword in ['cattivo', 'scadente', 'deteriorato']):
            return ConservationStatus.POOR
        elif any(keyword in value for keyword in ['pessimo', 'gravemente']):
            return ConservationStatus.VERY_POOR
        elif any(keyword in value for keyword in ['frammentario', 'frammentato']):
            return ConservationStatus.FRAGMENTARY
        elif any(keyword in value for keyword in ['restaurato', 'restauro']):
            return ConservationStatus.RESTORED
        elif any(keyword in value for keyword in ['ricostruito', 'ricostruzione']):
            return ConservationStatus.RECONSTRUCTED
        elif any(keyword in value for keyword in ['perduto', 'scomparso']):
            return ConservationStatus.LOST
        elif any(keyword in value for keyword in ['mancante', 'assente']):
            return ConservationStatus.MISSING
        elif any(keyword in value for keyword in ['danneggiato', 'lesionato']):
            return ConservationStatus.DAMAGED
        elif any(keyword in value for keyword in ['incompleto', 'parziale']):
            return ConservationStatus.INCOMPLETE
        return None
    
    @classmethod
    def get_all_mappings(cls) -> Dict[str, Dict[str, str]]:
        """Get all available mappings for debugging"""
        return {
            'PhotoType': cls.PHOTO_TYPE_MAPPINGS,
            'MaterialType': cls.MATERIAL_TYPE_MAPPINGS,
            'ConservationStatus': cls.CONSERVATION_STATUS_MAPPINGS,
            'DocumentType': cls.DOCUMENT_TYPE_MAPPINGS,
            'ContextType': cls.CONTEXT_TYPE_MAPPINGS,
            'DepositionType': cls.DEPOSITION_TYPE_MAPPINGS
        }
    
    @classmethod
    def validate_enum_value(cls, enum_class: Type, value: str) -> bool:
        """
        Validate if a value is a valid enum or can be converted
        
        Args:
            enum_class: The enum class to validate against
            value: The value to validate
            
        Returns:
            True if valid or convertible, False otherwise
        """
        if value is None:
            return False
            
        # Try direct validation
        try:
            enum_class(value)
            return True
        except ValueError:
            pass
            
        # Try conversion
        converted = cls.convert_to_enum(enum_class, value)
        return converted is not None


# Global instance for easy access
enum_converter = EnumConverter()


# ===== CONVENIENCE FUNCTIONS =====

def convert_photo_type(value: Any) -> Optional[PhotoType]:
    """Convert Italian value to PhotoType enum"""
    return enum_converter.convert_to_enum(PhotoType, value)


def convert_material_type(value: Any) -> Optional[MaterialType]:
    """Convert Italian value to MaterialType enum"""
    return enum_converter.convert_to_enum(MaterialType, value)


def convert_conservation_status(value: Any) -> Optional[ConservationStatus]:
    """Convert Italian value to ConservationStatus enum"""
    return enum_converter.convert_to_enum(ConservationStatus, value)


def convert_document_type(value: Any) -> Optional[DocumentType]:
    """Convert Italian value to DocumentType enum"""
    return enum_converter.convert_to_enum(DocumentType, value)


def convert_context_type(value: Any) -> Optional[ContextType]:
    """Convert Italian value to ContextType enum"""
    return enum_converter.convert_to_enum(ContextType, value)


def convert_deposition_type(value: Any) -> Optional[DepositionType]:
    """Convert Italian value to DepositionType enum"""
    return enum_converter.convert_to_enum(DepositionType, value)


# ===== LOGGING FUNCTIONS =====

def log_conversion_attempt(enum_class: Type, original_value: str, converted_value: Any, success: bool):
    """Log conversion attempts for debugging"""
    if success:
        logger.info(f"✅ Successfully converted '{original_value}' to {enum_class.__name__}.{converted_value.name}")
    else:
        logger.warning(f"❌ Failed to convert '{original_value}' to {enum_class.__name__}")