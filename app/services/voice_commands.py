"""
Voice Command System for FastZoom

Context-aware voice navigation that understands the application structure:
- Dashboard (main) -> Site selection
- Site pages: /view/{site_id}/dashboard, photos, giornale, team, map
- Archeology: /archeologia/us/site/{site_id}, reperti, matrix-harris

Commands are processed server-side and return navigation instructions
that the frontend executes with the current site context.
"""

import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class ActionType(str, Enum):
    """Types of actions."""
    NAVIGATE = "navigate"
    GO_BACK = "go_back"
    CREATE = "create"
    SEARCH = "search"
    HELP = "help"
    NONE = "none"


@dataclass
class NavigationRoute:
    """Defines a navigation destination."""
    name: str                      # Display name in Italian
    keywords: List[str]            # Keywords to match
    path_template: str             # Path with {site_id} placeholder
    requires_site: bool = True     # Whether this route needs a site context
    section: str = "main"          # Navigation section


# Define all navigable routes
NAVIGATION_ROUTES = [
    # Main site pages
    NavigationRoute(
        name="Dashboard",
        keywords=["dashboard", "pannello", "home", "principale", "inizio"],
        path_template="/view/{site_id}/dashboard",
        requires_site=True,
        section="main"
    ),
    NavigationRoute(
        name="Foto",
        keywords=["foto", "fotografie", "immagini", "galleria", "photo"],
        path_template="/view/{site_id}/photos",
        requires_site=True,
        section="main"
    ),
    NavigationRoute(
        name="Giornale di Cantiere",
        keywords=["giornale", "cantieri", "cantiere", "giornali"],
        path_template="/view/{site_id}/giornale",
        requires_site=True,
        section="main"
    ),
    NavigationRoute(
        name="Team",
        keywords=["team", "squadra", "utenti", "membri", "collaboratori"],
        path_template="/view/{site_id}/team",
        requires_site=True,
        section="main"
    ),
    NavigationRoute(
        name="Mappa",
        keywords=["mappa", "mappa geografica", "geo", "posizione", "cartografia"],
        path_template="/view/{site_id}/map",
        requires_site=True,
        section="main"
    ),
    
    # Archeology pages
    NavigationRoute(
        name="Unità Stratigrafiche",
        keywords=["unità stratigrafiche", "us", "stratigrafia", "strati"],
        path_template="/archeologia/us/site/{site_id}",
        requires_site=True,
        section="archeologia"
    ),
    NavigationRoute(
        name="Reperti",
        keywords=["reperti", "manufatti", "oggetti", "ritrovamenti"],
        path_template="/archeologia/reperti/site/{site_id}",
        requires_site=True,
        section="archeologia"
    ),
    NavigationRoute(
        name="Matrix Harris",
        keywords=["harris", "matrix", "matrice", "stratigrafico"],
        path_template="/archeologia/matrix-harris/site/{site_id}",
        requires_site=True,
        section="archeologia"
    ),
    NavigationRoute(
        name="Tombe",
        keywords=["tombe", "sepolture", "necropoli"],
        path_template="/archeologia/tombe/site/{site_id}",
        requires_site=True,
        section="archeologia"
    ),
    NavigationRoute(
        name="Campioni",
        keywords=["campioni", "analisi", "laboratorio"],
        path_template="/archeologia/campioni/site/{site_id}",
        requires_site=True,
        section="archeologia"
    ),
    
    # Global pages (no site required)
    NavigationRoute(
        name="Dashboard Principale",
        keywords=["dashboard principale", "selezione sito", "tutti i siti", "lista siti"],
        path_template="/dashboard",
        requires_site=False,
        section="global"
    ),
    NavigationRoute(
        name="Amministrazione",
        keywords=["admin", "amministrazione", "gestione"],
        path_template="/admin",
        requires_site=False,
        section="global"
    ),
]


# Create actions
CREATE_ACTIONS = [
    {
        "keywords": ["nuovo giornale", "crea giornale", "aggiungi giornale", "nuovo cantiere", "crea cantiere"],
        "target": "giornale",
        "response": "Apro il modulo per un nuovo giornale di cantiere..."
    },
    {
        "keywords": ["carica foto", "nuova foto", "aggiungi foto", "upload foto"],
        "target": "photo",
        "response": "Apro il caricamento foto..."
    },
    {
        "keywords": ["nuova unità", "crea us", "aggiungi us", "nuova stratigrafia"],
        "target": "us",
        "response": "Apro il modulo per una nuova unità stratigrafica..."
    },
]


def parse_voice_command(text: str, current_site_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse a voice command and return structured action.
    
    Args:
        text: The transcribed voice command
        current_site_id: The current site ID from the URL (if any)
        
    Returns:
        Dict with action, target, path, and response
    """
    text_lower = text.lower().strip()
    logger.debug(f"Parsing voice command: '{text}' (site: {current_site_id})")
    
    # 1. Check for "go back" commands
    if any(kw in text_lower for kw in ["torna indietro", "indietro", "back", "precedente"]):
        return {
            "action": ActionType.GO_BACK.value,
            "path": None,
            "response": "Torno indietro...",
            "is_command": True
        }
    
    # 2. Check for navigation commands
    nav_patterns = [
        r"(?:vai|porta|apri|mostra|vedi)\s+(?:a(?:lla|l|lle)?|la|le|il|i|lo)?\s*(.+)",
        r"(?:voglio\s+vedere|fammi\s+vedere)\s+(.+)",
        r"(?:apri|mostra)\s+(.+)",
    ]
    
    for pattern in nav_patterns:
        match = re.search(pattern, text_lower)
        if match:
            target = match.group(1).strip()
            
            # Find matching route
            for route in NAVIGATION_ROUTES:
                for keyword in route.keywords:
                    if keyword in target or target in keyword:
                        # Build path
                        if route.requires_site:
                            if not current_site_id:
                                return {
                                    "action": ActionType.NONE.value,
                                    "path": None,
                                    "response": f"Per andare a {route.name}, devi prima selezionare un sito.",
                                    "is_command": True
                                }
                            path = route.path_template.replace("{site_id}", current_site_id)
                        else:
                            path = route.path_template
                        
                        return {
                            "action": ActionType.NAVIGATE.value,
                            "path": path,
                            "target_name": route.name,
                            "response": f"Vado a {route.name}...",
                            "is_command": True
                        }
    
    # 3. Check for create commands
    for create_action in CREATE_ACTIONS:
        if any(kw in text_lower for kw in create_action["keywords"]):
            return {
                "action": ActionType.CREATE.value,
                "target": create_action["target"],
                "response": create_action["response"],
                "is_command": True
            }
    
    # 4. Check for search commands
    search_match = re.search(r"(?:cerca|trova|ricerca)\s+(.+)", text_lower)
    if search_match:
        query = search_match.group(1).strip()
        return {
            "action": ActionType.SEARCH.value,
            "query": query,
            "response": f"Cerco: {query}...",
            "is_command": True
        }
    
    # 5. Check for help
    if any(kw in text_lower for kw in ["aiuto", "help", "cosa puoi fare", "comandi"]):
        help_text = """Ecco cosa posso fare:
• Navigare: "vai alle foto", "apri il giornale", "mostra la mappa"
• Creare: "nuovo giornale", "carica foto"
• Cercare: "cerca [qualcosa]"
• Tornare indietro: "torna indietro"

Pagine disponibili: dashboard, foto, giornale, team, mappa, unità stratigrafiche, reperti, matrix harris."""
        
        return {
            "action": ActionType.HELP.value,
            "response": help_text,
            "is_command": True
        }
    
    # 6. No command matched - let LLM handle it
    return {
        "action": ActionType.NONE.value,
        "response": "",
        "is_command": False
    }


def get_available_pages(current_site_id: Optional[str] = None) -> List[Dict[str, str]]:
    """Get list of available pages for the current context."""
    pages = []
    for route in NAVIGATION_ROUTES:
        if route.requires_site and not current_site_id:
            continue
        pages.append({
            "name": route.name,
            "section": route.section
        })
    return pages
