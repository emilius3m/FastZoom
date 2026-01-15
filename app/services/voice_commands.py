"""
Voice Command Parser for FastZoom

Parses Italian voice commands and returns structured actions
that the frontend can execute.
"""

import re
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from loguru import logger


class ActionType(str, Enum):
    """Types of actions the frontend can execute."""
    NAVIGATE = "navigate"
    OPEN_MODAL = "open_modal"
    SEARCH = "search"
    CREATE = "create"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    HELP = "help"
    NONE = "none"


@dataclass
class VoiceCommand:
    """Parsed voice command result."""
    action: ActionType
    target: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    response_text: str = ""


class VoiceCommandParser:
    """Parse Italian voice commands into structured actions."""
    
    PATTERNS = [
        # Navigation
        (r"(?:vai|porta|apri|mostra).*dashboard", ActionType.NAVIGATE, "dashboard", "Apro la dashboard..."),
        (r"(?:vai|porta|apri|mostra).*(?:siti|cantieri)", ActionType.NAVIGATE, "sites", "Apro i siti..."),
        (r"(?:vai|porta|apri|mostra).*(?:foto|galleria)", ActionType.NAVIGATE, "photos", "Apro le foto..."),
        (r"(?:vai|porta|apri|mostra).*giornali", ActionType.NAVIGATE, "giornale", "Apro i giornali..."),
        (r"(?:torna|vai).*indietro", ActionType.NAVIGATE, "back", "Torno indietro..."),
        (r"(?:vai|torna).*home", ActionType.NAVIGATE, "home", "Torno alla home..."),
        
        # Create commands
        (r"(?:crea|nuovo|aggiungi|inserisci).*giornale", ActionType.CREATE, "giornale", "Apro il modulo per un nuovo giornale..."),
        (r"(?:crea|nuovo|aggiungi).*(?:sito|cantiere)", ActionType.CREATE, "site", "Apro il modulo per un nuovo sito..."),
        (r"(?:carica|upload|aggiungi).*foto", ActionType.CREATE, "photo", "Apro il caricamento foto..."),
        
        # Search
        (r"(?:cerca|trova).*foto.*(?:di|con)?\s*(.+)?", ActionType.SEARCH, "photos", "Cerco foto..."),
        (r"(?:cerca|trova)\s+(.+)", ActionType.SEARCH, "global", "Cerco..."),
        
        # Confirmation
        (r"^(?:sì|si|ok|conferma|procedi)$", ActionType.CONFIRM, None, "Confermato."),
        (r"^(?:no|annulla|cancella|stop)$", ActionType.CANCEL, None, "Annullato."),
        
        # Help
        (r"(?:aiuto|help|cosa puoi fare)", ActionType.HELP, None, "Posso: navigare, creare giornali, cercare foto, e rispondere a domande!"),
    ]
    
    def parse(self, text: str) -> VoiceCommand:
        text_lower = text.lower().strip()
        
        for pattern, action, target, response in self.PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                params = {}
                if match.groups() and match.group(1):
                    params["query"] = match.group(1).strip()
                
                logger.info(f"🎤 Voice command: {action} -> {target}")
                return VoiceCommand(action=action, target=target, params=params or None, response_text=response)
        
        return VoiceCommand(action=ActionType.NONE, response_text="")


voice_command_parser = VoiceCommandParser()


def parse_voice_command(text: str) -> Dict[str, Any]:
    cmd = voice_command_parser.parse(text)
    return {
        "action": cmd.action.value,
        "target": cmd.target,
        "params": cmd.params,
        "response_text": cmd.response_text,
        "is_command": cmd.action != ActionType.NONE
    }
