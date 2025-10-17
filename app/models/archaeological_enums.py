# app/models/archaeological_enums.py
"""
Archaeological Enums for FastZoom System
RIPRISTINATI: PhotoType, MaterialType, ConservationStatus + altri enum mancanti
Include tutti gli enum archeologici standardizzati per classificazione
"""

from enum import Enum as PyEnum


# ===== PHOTO AND DOCUMENTATION ENUMS =====

class PhotoType(str, PyEnum):
    """
    Tipologie di fotografie archeologiche
    RIPRISTINATO - era sparito nella riorganizzazione!
    """
    GENERAL_VIEW = "general_view"              # Vista generale
    DETAIL = "detail"                          # Dettaglio
    SECTION = "section"                        # Sezione
    DRAWING_OVERLAY = "drawing_overlay"        # Disegno sovrapposto
    BEFORE_RESTORATION = "before_restoration"  # Pre-restauro
    AFTER_RESTORATION = "after_restoration"   # Post-restauro
    EXCAVATION_PROGRESS = "excavation_progress"  # Avanzamento scavo
    STRATIGRAPHY = "stratigraphy"             # Stratigrafia
    FIND_CONTEXT = "find_context"             # Contesto rinvenimento
    LABORATORY = "laboratory"                 # Laboratorio
    ARCHIVE = "archive"                       # Archivio
    WORKING = "working"                       # Di lavoro
    PUBLICATION = "publication"               # Pubblicazione


class DocumentType(str, PyEnum):
    """Tipologie documenti archeologici"""
    RELAZIONE = "relazione"
    PLANIMETRIA = "planimetria" 
    SEZIONE = "sezione"
    PROSPETTO = "prospetto"
    DISEGNO = "disegno"
    FOTOGRAFIA = "fotografia"
    AUTORIZZAZIONE = "autorizzazione"
    BIBLIOGRAFIA = "bibliografia"
    RAPPORTO = "rapporto"
    CATALOGO = "catalogo"
    INVENTARIO = "inventario"
    ALTRO = "altro"


# ===== MATERIAL AND CONSERVATION ENUMS =====

class MaterialType(str, PyEnum):
    """
    Tipologie di materiali archeologici
    RIPRISTINATO - era sparito nella riorganizzazione!
    Standard per catalogazione manufatti
    """
    CERAMIC = "ceramic"                # Ceramica
    BRONZE = "bronze"                 # Bronzo  
    IRON = "iron"                     # Ferro
    STONE = "stone"                   # Pietra
    MARBLE = "marble"                 # Marmo
    GLASS = "glass"                   # Vetro
    BONE = "bone"                     # Osso
    WOOD = "wood"                     # Legno
    GOLD = "gold"                     # Oro
    SILVER = "silver"                 # Argento
    LEAD = "lead"                     # Piombo
    COPPER = "copper"                 # Rame
    TERRACOTTA = "terracotta"         # Terracotta
    STUCCO = "stucco"                 # Stucco
    MOSAIC = "mosaic"                 # Mosaico
    FABRIC = "fabric"                 # Tessuto
    LEATHER = "leather"               # Cuoio
    AMBER = "amber"                   # Ambra
    IVORY = "ivory"                   # Avorio
    CORAL = "coral"                   # Corallo
    PLASTER = "plaster"               # Intonaco
    MORTAR = "mortar"                 # Malta
    CONCRETE = "concrete"             # Calcestruzzo
    TILE = "tile"                     # Tegola/mattone
    METAL_COMPOSITE = "metal_composite"  # Lega metallica
    COMPOSITE = "composite"           # Materiale composito
    ORGANIC = "organic"               # Organico generico
    OTHER = "other"                   # Altro


class ConservationStatus(str, PyEnum):
    """
    Stati di conservazione archeologici
    RIPRISTINATO - era sparito nella riorganizzazione!
    Standard ICCD per valutazione stato manufatti
    """
    EXCELLENT = "excellent"           # Eccellente
    GOOD = "good"                     # Buono
    FAIR = "fair"                     # Discreto  
    POOR = "poor"                     # Cattivo
    VERY_POOR = "very_poor"           # Pessimo
    FRAGMENTARY = "fragmentary"       # Frammentario
    RESTORED = "restored"             # Restaurato
    RECONSTRUCTED = "reconstructed"   # Ricostruito
    LOST = "lost"                     # Perduto
    MISSING = "missing"               # Mancante
    DAMAGED = "damaged"               # Danneggiato
    INCOMPLETE = "incomplete"         # Incompleto


# ===== ARCHAEOLOGICAL CONTEXT ENUMS =====

class ContextType(str, PyEnum):
    """Tipologie contesto archeologico"""
    PRIMARY = "primary"               # Primario
    SECONDARY = "secondary"           # Secondario  
    DISTURBED = "disturbed"           # Sconvolto
    MIXED = "mixed"                   # Misto
    REDEPOSITED = "redeposited"       # Ridepositato
    UNKNOWN = "unknown"               # Sconosciuto


class DepositionType(str, PyEnum):
    """Modalità di deposizione"""
    INTENTIONAL = "intentional"       # Intenzionale
    ACCIDENTAL = "accidental"         # Accidentale
    NATURAL = "natural"               # Naturale
    RITUAL = "ritual"                 # Rituale
    FUNERARY = "funerary"             # Funerario
    VOTIVE = "votive"                 # Votivo
    UNKNOWN = "unknown"               # Sconosciuto


# ===== DATING AND CHRONOLOGY ENUMS =====

class DatingMethod(str, PyEnum):
    """Metodi di datazione"""
    STRATIGRAPHIC = "stratigraphic"   # Stratigrafico
    TYPOLOGICAL = "typological"       # Tipologico
    STYLISTIC = "stylistic"           # Stilistico
    C14 = "c14"                      # Radiocarbonio
    THERMOLUMINESCENCE = "tl"         # Termoluminescenza
    DENDROCHRONOLOGY = "dendro"       # Dendrocronologia
    ARCHAEOMAGNETIC = "archaeomag"    # Archeomagnetico
    HISTORICAL = "historical"         # Storico
    EPIGRAPHIC = "epigraphic"         # Epigrafico
    NUMISMATIC = "numismatic"         # Numismatico


class ChronologicalPeriod(str, PyEnum):
    """Periodi cronologici standard"""
    PREHISTORIC = "prehistoric"
    PALEOLITHIC = "paleolithic"
    MESOLITHIC = "mesolithic" 
    NEOLITHIC = "neolithic"
    BRONZE_AGE = "bronze_age"
    IRON_AGE = "iron_age"
    ARCHAIC = "archaic"
    CLASSICAL = "classical"
    HELLENISTIC = "hellenistic"
    ROMAN_REPUBLICAN = "roman_republican"
    ROMAN_IMPERIAL = "roman_imperial"
    LATE_ANTIQUE = "late_antique"
    EARLY_MEDIEVAL = "early_medieval"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    POST_MEDIEVAL = "post_medieval"
    MODERN = "modern"
    CONTEMPORARY = "contemporary"
    UNKNOWN = "unknown"


# ===== SITE AND STRUCTURE ENUMS =====

class SiteFunction(str, PyEnum):
    """Funzioni siti archeologici"""
    SETTLEMENT = "settlement"         # Insediamento
    NECROPOLIS = "necropolis"        # Necropoli
    SANCTUARY = "sanctuary"           # Santuario
    TEMPLE = "temple"                # Tempio
    VILLA = "villa"                  # Villa
    FORTRESS = "fortress"            # Fortezza
    WORKSHOP = "workshop"            # Officina
    QUARRY = "quarry"               # Cava
    HARBOR = "harbor"               # Porto
    ROAD = "road"                   # Strada
    AQUEDUCT = "aqueduct"           # Acquedotto
    BRIDGE = "bridge"               # Ponte
    THEATER = "theater"             # Teatro
    AMPHITHEATER = "amphitheater"   # Anfiteatro
    CIRCUS = "circus"               # Circo
    BATHS = "baths"                 # Terme
    MARKET = "market"               # Mercato
    INDUSTRIAL = "industrial"        # Industriale
    AGRICULTURAL = "agricultural"    # Agricolo
    OTHER = "other"                 # Altro


class StructuralElement(str, PyEnum):
    """Elementi strutturali"""
    WALL = "wall"                   # Muro
    FOUNDATION = "foundation"       # Fondazione
    FLOOR = "floor"                 # Pavimento
    ROOF = "roof"                   # Tetto
    COLUMN = "column"               # Colonna
    PILLAR = "pillar"               # Pilastro
    ARCH = "arch"                   # Arco
    VAULT = "vault"                 # Volta
    DOOR = "door"                   # Porta
    WINDOW = "window"               # Finestra
    STAIRCASE = "staircase"         # Scala
    DRAIN = "drain"                 # Scarico
    CANAL = "canal"                 # Canale
    CISTERN = "cistern"             # Cisterna
    HEARTH = "hearth"               # Focolare
    OVEN = "oven"                   # Forno
    OTHER = "other"                 # Altro


# ===== ARTIFACT CLASSIFICATION ENUMS =====

class ArtifactCategory(str, PyEnum):
    """Categorie manufatti"""
    POTTERY = "pottery"             # Ceramica
    TOOLS = "tools"                 # Utensili
    WEAPONS = "weapons"             # Armi
    ORNAMENTS = "ornaments"         # Ornamenti
    COINS = "coins"                 # Monete
    SCULPTURES = "sculptures"       # Sculture
    INSCRIPTIONS = "inscriptions"   # Iscrizioni
    MOSAICS = "mosaics"            # Mosaici
    PAINTINGS = "paintings"         # Pitture
    ARCHITECTURAL = "architectural" # Architettonici
    RELIGIOUS = "religious"         # Religiosi
    FUNERARY = "funerary"          # Funerari
    DOMESTIC = "domestic"          # Domestici
    INDUSTRIAL = "industrial"       # Industriali
    OTHER = "other"                # Altri


class PotteryType(str, PyEnum):
    """Tipologie ceramiche specifiche"""
    FINE_WARE = "fine_ware"        # Ceramica fine
    COARSE_WARE = "coarse_ware"    # Ceramica grossolana
    COOKING_POT = "cooking_pot"     # Pentola
    STORAGE_JAR = "storage_jar"     # Giara
    AMPHORA = "amphora"            # Anfora
    CUP = "cup"                    # Coppa
    BOWL = "bowl"                  # Ciotola
    DISH = "dish"                  # Piatto
    JUG = "jug"                    # Brocca
    LAMP = "lamp"                  # Lucerna
    FIGURINE = "figurine"          # Figurina
    TILE = "tile"                  # Tegola
    BRICK = "brick"                # Mattone
    PIPE = "pipe"                  # Tubo
    OTHER = "other"                # Altro


# ===== STRATIGRAPHIC ENUMS =====

class StratigraphicRelation(str, PyEnum):
    """Relazioni stratigrafiche Matrix Harris"""
    COVERS = "covers"               # copre
    COVERED_BY = "covered_by"       # coperto da
    CUTS = "cuts"                   # taglia
    CUT_BY = "cut_by"              # tagliato da
    FILLS = "fills"                # riempie
    FILLED_BY = "filled_by"        # riempito da
    EQUALS = "equals"              # uguale a
    BONDS_WITH = "bonds_with"      # si lega a
    LEANS_AGAINST = "leans_against" # si appoggia a
    SUPPORTS = "supports"          # supporta


# ===== DISPLAY NAME MAPPINGS =====

# PhotoType display names
PHOTO_TYPE_DISPLAY = {
    PhotoType.GENERAL_VIEW: 'Vista generale',
    PhotoType.DETAIL: 'Dettaglio',
    PhotoType.SECTION: 'Sezione',
    PhotoType.DRAWING_OVERLAY: 'Disegno sovrapposto',
    PhotoType.BEFORE_RESTORATION: 'Pre-restauro',
    PhotoType.AFTER_RESTORATION: 'Post-restauro',
    PhotoType.EXCAVATION_PROGRESS: 'Avanzamento scavo',
    PhotoType.STRATIGRAPHY: 'Stratigrafia',
    PhotoType.FIND_CONTEXT: 'Contesto rinvenimento',
    PhotoType.LABORATORY: 'Laboratorio',
    PhotoType.ARCHIVE: 'Archivio',
    PhotoType.WORKING: 'Di lavoro',
    PhotoType.PUBLICATION: 'Pubblicazione'
}

# MaterialType display names
MATERIAL_TYPE_DISPLAY = {
    MaterialType.CERAMIC: 'Ceramica',
    MaterialType.BRONZE: 'Bronzo',
    MaterialType.IRON: 'Ferro',
    MaterialType.STONE: 'Pietra',
    MaterialType.MARBLE: 'Marmo',
    MaterialType.GLASS: 'Vetro',
    MaterialType.BONE: 'Osso',
    MaterialType.WOOD: 'Legno',
    MaterialType.GOLD: 'Oro',
    MaterialType.SILVER: 'Argento',
    MaterialType.LEAD: 'Piombo',
    MaterialType.COPPER: 'Rame',
    MaterialType.TERRACOTTA: 'Terracotta',
    MaterialType.STUCCO: 'Stucco',
    MaterialType.MOSAIC: 'Mosaico',
    MaterialType.FABRIC: 'Tessuto',
    MaterialType.LEATHER: 'Cuoio',
    MaterialType.AMBER: 'Ambra',
    MaterialType.IVORY: 'Avorio',
    MaterialType.CORAL: 'Corallo',
    MaterialType.PLASTER: 'Intonaco',
    MaterialType.MORTAR: 'Malta',
    MaterialType.CONCRETE: 'Calcestruzzo',
    MaterialType.TILE: 'Tegola/mattone',
    MaterialType.METAL_COMPOSITE: 'Lega metallica',
    MaterialType.COMPOSITE: 'Materiale composito',
    MaterialType.ORGANIC: 'Organico',
    MaterialType.OTHER: 'Altro'
}

# ConservationStatus display names  
CONSERVATION_STATUS_DISPLAY = {
    ConservationStatus.EXCELLENT: 'Eccellente',
    ConservationStatus.GOOD: 'Buono',
    ConservationStatus.FAIR: 'Discreto',
    ConservationStatus.POOR: 'Cattivo',
    ConservationStatus.VERY_POOR: 'Pessimo',
    ConservationStatus.FRAGMENTARY: 'Frammentario',
    ConservationStatus.RESTORED: 'Restaurato',
    ConservationStatus.RECONSTRUCTED: 'Ricostruito',
    ConservationStatus.LOST: 'Perduto',
    ConservationStatus.MISSING: 'Mancante',
    ConservationStatus.DAMAGED: 'Danneggiato',
    ConservationStatus.INCOMPLETE: 'Incompleto'
}


# ===== HELPER FUNCTIONS =====

def get_photo_type_choices():
    """Choices per PhotoType in forms"""
    return [(pt.value, PHOTO_TYPE_DISPLAY.get(pt, pt.value.replace('_', ' ').title())) 
            for pt in PhotoType]

def get_material_type_choices():
    """Choices per MaterialType in forms"""
    return [(mt.value, MATERIAL_TYPE_DISPLAY.get(mt, mt.value.replace('_', ' ').title())) 
            for mt in MaterialType]

def get_conservation_status_choices():
    """Choices per ConservationStatus in forms"""
    return [(cs.value, CONSERVATION_STATUS_DISPLAY.get(cs, cs.value.replace('_', ' ').title())) 
            for cs in ConservationStatus]

def get_enum_display_name(enum_value, enum_type):
    """Helper generico per ottenere nome display di enum"""
    display_maps = {
        'PhotoType': PHOTO_TYPE_DISPLAY,
        'MaterialType': MATERIAL_TYPE_DISPLAY, 
        'ConservationStatus': CONSERVATION_STATUS_DISPLAY
    }
    
    display_map = display_maps.get(enum_type.__name__)
    if display_map and enum_value in display_map:
        return display_map[enum_value]
    
    return enum_value.value.replace('_', ' ').title() if hasattr(enum_value, 'value') else str(enum_value)

def get_all_archaeological_enums():
    """Restituisce dizionario di tutti gli enum archeologici"""
    return {
        'PhotoType': PhotoType,
        'MaterialType': MaterialType,
        'ConservationStatus': ConservationStatus,
        'DocumentType': DocumentType,
        'ContextType': ContextType,
        'DepositionType': DepositionType,
        'DatingMethod': DatingMethod,
        'ChronologicalPeriod': ChronologicalPeriod,
        'SiteFunction': SiteFunction,
        'StructuralElement': StructuralElement,
        'ArtifactCategory': ArtifactCategory,
        'PotteryType': PotteryType,
        'StratigraphicRelation': StratigraphicRelation
    }


# ===== VALIDATION HELPERS =====

def is_valid_photo_type(value: str) -> bool:
    """Valida se valore è PhotoType valido"""
    try:
        PhotoType(value)
        return True
    except ValueError:
        return False

def is_valid_material_type(value: str) -> bool:
    """Valida se valore è MaterialType valido"""
    try:
        MaterialType(value)
        return True
    except ValueError:
        return False

def is_valid_conservation_status(value: str) -> bool:
    """Valida se valore è ConservationStatus valido"""
    try:
        ConservationStatus(value)
        return True
    except ValueError:
        return False


# ===== BACKWARD COMPATIBILITY =====
# Alias per compatibilità con codice esistente che potrebbe usare nomi diversi
PhotoTypeEnum = PhotoType
MaterialTypeEnum = MaterialType  
ConservationStatusEnum = ConservationStatus