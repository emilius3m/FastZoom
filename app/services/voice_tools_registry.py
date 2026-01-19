"""
Voice Tools Registry

Whitelist of API operations that can be invoked via voice commands.
Each tool is mapped to its operationId, HTTP method, path template,
and whether it requires user confirmation.

Security principle: LLM can ONLY invoke tools registered here.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List
from uuid import UUID
from enum import Enum
from loguru import logger


class ToolCategory(str, Enum):
    """Tool categories for organization."""
    DASHBOARD = "dashboard"
    NAVIGATION = "navigation"  # UI navigation (no API call)
    PHOTOS = "photos"
    DOCUMENTS = "documents"
    US_USM = "us_usm"
    HARRIS_MATRIX = "harris_matrix"
    FORM_SCHEMAS = "form_schemas"
    ICCD = "iccd"
    GIORNALE = "giornale"  # Giornale di cantiere


@dataclass
class VoiceTool:
    """Definition of a voice-callable tool."""
    operation_id: str
    http_method: str
    path_template: str
    description: str
    category: ToolCategory
    
    # Security flags
    requires_confirmation: bool = False
    read_only: bool = True
    site_scoped: bool = True
    
    # Parameter definitions
    path_params: List[str] = field(default_factory=list)
    query_params: List[str] = field(default_factory=list)
    has_body: bool = False
    
    # Optional permission level required
    permission: Optional[str] = None


# =============================================================================
# VOICE TOOLS REGISTRY - READ-ONLY (30)
# =============================================================================

READ_ONLY_TOOLS: Dict[str, VoiceTool] = {
    # --- Dashboard ---
    "v1_get_sites_list": VoiceTool(
        operation_id="v1_get_sites_list",
        http_method="GET",
        path_template="/api/v1/unified/dashboard/sites/list",
        description="Ottiene la lista dei siti archeologici",
        category=ToolCategory.DASHBOARD,
        site_scoped=False,
    ),
    "v1_get_overview_stats": VoiceTool(
        operation_id="v1_get_overview_stats",
        http_method="GET",
        path_template="/api/v1/unified/dashboard/stats/overview",
        description="Ottiene statistiche generali del dashboard",
        category=ToolCategory.DASHBOARD,
        site_scoped=False,
    ),
    "v1_get_recent_activities": VoiceTool(
        operation_id="v1_get_recent_activities",
        http_method="GET",
        path_template="/api/v1/unified/dashboard/activities/recent",
        description="Ottiene le attività recenti",
        category=ToolCategory.DASHBOARD,
        site_scoped=False,
    ),
    "v1_get_system_status": VoiceTool(
        operation_id="v1_get_system_status",
        http_method="GET",
        path_template="/api/v1/unified/dashboard/system/status",
        description="Ottiene lo stato del sistema",
        category=ToolCategory.DASHBOARD,
        site_scoped=False,
    ),
    "v1_get_unified_documents_count": VoiceTool(
        operation_id="v1_get_unified_documents_count",
        http_method="GET",
        path_template="/api/v1/unified/documents/count",
        description="Conta totale documenti nel sistema",
        category=ToolCategory.DASHBOARD,
        site_scoped=False,
    ),
    "v1_get_site_dashboard_stats": VoiceTool(
        operation_id="v1_get_site_dashboard_stats",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/dashboard/stats",
        description="Statistiche dashboard per un sito specifico",
        category=ToolCategory.DASHBOARD,
        path_params=["site_id"],
    ),
    
    # --- Photos ---
    "get_site_photos": VoiceTool(
        operation_id="get_site_photos",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/photos",
        description="Ottiene le foto di un sito",
        category=ToolCategory.PHOTOS,
        path_params=["site_id"],
        query_params=["limit", "offset", "search"],
    ),
    "get_photo_thumbnail": VoiceTool(
        operation_id="get_photo_thumbnail",
        http_method="GET",
        path_template="/api/v1/photos/{photo_id}/thumbnail",
        description="Ottiene la miniatura di una foto",
        category=ToolCategory.PHOTOS,
        path_params=["photo_id"],
        site_scoped=False,
    ),
    "get_photo_full": VoiceTool(
        operation_id="get_photo_full",
        http_method="GET",
        path_template="/api/v1/photos/{photo_id}/full",
        description="Ottiene la foto a dimensione piena",
        category=ToolCategory.PHOTOS,
        path_params=["photo_id"],
        site_scoped=False,
    ),
    "download_photo": VoiceTool(
        operation_id="download_photo",
        http_method="GET",
        path_template="/api/v1/photos/{photo_id}/download",
        description="Scarica una foto",
        category=ToolCategory.PHOTOS,
        path_params=["photo_id"],
        site_scoped=False,
    ),
    "stream_photo_from_minio": VoiceTool(
        operation_id="stream_photo_from_minio",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/photos/{photo_id}/stream",
        description="Stream foto da MinIO",
        category=ToolCategory.PHOTOS,
        path_params=["site_id", "photo_id"],
    ),
    "search_photos_by_metadata": VoiceTool(
        operation_id="search_photos_by_metadata",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/api/photos/search",
        description="Cerca foto per metadati",
        category=ToolCategory.PHOTOS,
        path_params=["site_id"],
        query_params=["query", "limit"],
    ),
    
    # --- Deep Zoom ---
    "get_deep_zoom_info": VoiceTool(
        operation_id="get_deep_zoom_info",
        http_method="GET",
        path_template="/api/v1/deep-zoom/sites/{site_id}/photos/{photo_id}/info",
        description="Info Deep Zoom per una foto",
        category=ToolCategory.PHOTOS,
        path_params=["site_id", "photo_id"],
    ),
    "get_deep_zoom_processing_status": VoiceTool(
        operation_id="get_deep_zoom_processing_status",
        http_method="GET",
        path_template="/api/v1/deep-zoom/sites/{site_id}/photos/{photo_id}/status",
        description="Stato elaborazione Deep Zoom",
        category=ToolCategory.PHOTOS,
        path_params=["site_id", "photo_id"],
    ),
    "get_processing_queue_status": VoiceTool(
        operation_id="get_processing_queue_status",
        http_method="GET",
        path_template="/api/v1/deep-zoom/sites/{site_id}/processing-queue",
        description="Stato coda elaborazione Deep Zoom",
        category=ToolCategory.PHOTOS,
        path_params=["site_id"],
    ),
    "get_deep_zoom_background_status": VoiceTool(
        operation_id="get_deep_zoom_background_status",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/photos/deep-zoom/background-status",
        description="Stato background Deep Zoom",
        category=ToolCategory.PHOTOS,
        path_params=["site_id"],
    ),
    "get_photo_deep_zoom_task_status": VoiceTool(
        operation_id="get_photo_deep_zoom_task_status",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/photos/{photo_id}/deep-zoom/task-status",
        description="Stato task Deep Zoom per foto",
        category=ToolCategory.PHOTOS,
        path_params=["site_id", "photo_id"],
    ),
    
    # --- Documents ---
    "v1_get_site_documents": VoiceTool(
        operation_id="v1_get_site_documents",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/documents",
        description="Lista documenti del sito",
        category=ToolCategory.DOCUMENTS,
        path_params=["site_id"],
        query_params=["limit", "offset"],
    ),
    "v1_get_document": VoiceTool(
        operation_id="v1_get_document",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/documents/{document_id}",
        description="Dettagli documento",
        category=ToolCategory.DOCUMENTS,
        path_params=["site_id", "document_id"],
    ),
    "v1_download_document": VoiceTool(
        operation_id="v1_download_document",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/documents/{document_id}/download",
        description="Scarica documento",
        category=ToolCategory.DOCUMENTS,
        path_params=["site_id", "document_id"],
    ),
    "v1_get_documents_count": VoiceTool(
        operation_id="v1_get_documents_count",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/documents/count",
        description="Conta documenti del sito",
        category=ToolCategory.DOCUMENTS,
        path_params=["site_id"],
    ),
    
    # --- US/USM ---
    "v1_list_us": VoiceTool(
        operation_id="v1_list_us",
        http_method="GET",
        path_template="/api/v1/us/sites/{site_id}/us",
        description="Lista unità stratigrafiche",
        category=ToolCategory.US_USM,
        path_params=["site_id"],
        query_params=["limit", "offset"],
    ),
    "v1_get_us": VoiceTool(
        operation_id="v1_get_us",
        http_method="GET",
        path_template="/api/v1/us/sites/{site_id}/us/{us_id}",
        description="Dettagli unità stratigrafica",
        category=ToolCategory.US_USM,
        path_params=["site_id", "us_id"],
    ),
    "v1_list_usm": VoiceTool(
        operation_id="v1_list_usm",
        http_method="GET",
        path_template="/api/v1/us/sites/{site_id}/usm",
        description="Lista unità stratigrafiche murarie",
        category=ToolCategory.US_USM,
        path_params=["site_id"],
        query_params=["limit", "offset"],
    ),
    "v1_get_usm": VoiceTool(
        operation_id="v1_get_usm",
        http_method="GET",
        path_template="/api/v1/us/sites/{site_id}/usm/{usm_id}",
        description="Dettagli unità stratigrafica muraria",
        category=ToolCategory.US_USM,
        path_params=["site_id", "usm_id"],
    ),
    
    # --- Harris Matrix ---
    "v1_generate_harris_matrix": VoiceTool(
        operation_id="v1_generate_harris_matrix",
        http_method="GET",
        path_template="/api/v1/harris-matrix/sites/{site_id}",
        description="Genera Harris Matrix per il sito",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
    ),
    "v1_get_matrix_statistics": VoiceTool(
        operation_id="v1_get_matrix_statistics",
        http_method="GET",
        path_template="/api/v1/harris-matrix/sites/{site_id}/statistics",
        description="Statistiche Harris Matrix",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
    ),
    "v1_get_unit_relationships": VoiceTool(
        operation_id="v1_get_unit_relationships",
        http_method="GET",
        path_template="/api/v1/harris-matrix/sites/{site_id}/units/{unit_code}",
        description="Relazioni unità nella matrice",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id", "unit_code"],
    ),
    
    # --- Form Schemas ---
    "get_form_schemas": VoiceTool(
        operation_id="get_form_schemas",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/form-schemas",
        description="Lista schemi form del sito",
        category=ToolCategory.FORM_SCHEMAS,
        path_params=["site_id"],
    ),
    "get_form_schema": VoiceTool(
        operation_id="get_form_schema",
        http_method="GET",
        path_template="/api/v1/sites/{site_id}/form-schemas/{schema_id}",
        description="Dettagli schema form",
        category=ToolCategory.FORM_SCHEMAS,
        path_params=["site_id", "schema_id"],
    ),
    
    # --- Giornale di Cantiere ---
    "v1_get_giornali": VoiceTool(
        operation_id="v1_get_giornali",
        http_method="GET",
        path_template="/api/v1/giornale",
        description="Lista giornali di cantiere",
        category=ToolCategory.GIORNALE,
        site_scoped=False,
        query_params=["limit", "offset"],
    ),
    "v1_get_cantieri": VoiceTool(
        operation_id="v1_get_cantieri",
        http_method="GET",
        path_template="/api/v1/cantieri",
        description="Lista cantieri",
        category=ToolCategory.GIORNALE,
        site_scoped=False,
        query_params=["limit", "offset"],
    ),
    "v1_get_giornale_stats": VoiceTool(
        operation_id="v1_get_giornale_stats",
        http_method="GET",
        path_template="/api/v1/giornale/stats",
        description="Statistiche giornali di cantiere",
        category=ToolCategory.GIORNALE,
        site_scoped=False,
    ),
}


# =============================================================================
# NAVIGATION TOOLS (UI-only, no API call needed)
# These are pseudo-tools that trigger frontend navigation
# =============================================================================

NAVIGATION_TOOLS: Dict[str, VoiceTool] = {
    "nav_goto_sites": VoiceTool(
        operation_id="nav_goto_sites",
        http_method="GET",  # Not used, but required
        path_template="/_nav/sites",  # Special navigation marker
        description="Vai alla lista dei siti",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_goto_giornale": VoiceTool(
        operation_id="nav_goto_giornale",
        http_method="GET",
        path_template="/_nav/giornale",
        description="Vai al giornale di cantiere",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_goto_cantieri": VoiceTool(
        operation_id="nav_goto_cantieri",
        http_method="GET",
        path_template="/_nav/cantieri",
        description="Vai ai cantieri",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_goto_analisi": VoiceTool(
        operation_id="nav_goto_analisi",
        http_method="GET",
        path_template="/_nav/analisi",
        description="Vai alle analisi",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_goto_site": VoiceTool(
        operation_id="nav_goto_site",
        http_method="GET",
        path_template="/_nav/site/{site_name}",
        description="Vai a un sito specifico per nome",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
        path_params=["site_name"],
    ),
    "nav_goto_photos": VoiceTool(
        operation_id="nav_goto_photos",
        http_method="GET",
        path_template="/_nav/site/{site_id}/photos",
        description="Vai alle foto del sito",
        category=ToolCategory.NAVIGATION,
        path_params=["site_id"],
    ),
    "nav_goto_us": VoiceTool(
        operation_id="nav_goto_us",
        http_method="GET",
        path_template="/_nav/site/{site_id}/us",
        description="Vai alle unità stratigrafiche",
        category=ToolCategory.NAVIGATION,
        path_params=["site_id"],
    ),
    "nav_goto_harris": VoiceTool(
        operation_id="nav_goto_harris",
        http_method="GET",
        path_template="/_nav/site/{site_id}/harris-matrix",
        description="Vai alla Harris Matrix",
        category=ToolCategory.NAVIGATION,
        path_params=["site_id"],
    ),
    "nav_goto_documents": VoiceTool(
        operation_id="nav_goto_documents",
        http_method="GET",
        path_template="/_nav/site/{site_id}/documents",
        description="Vai ai documenti del sito",
        category=ToolCategory.NAVIGATION,
        path_params=["site_id"],
    ),
    "nav_goto_dashboard": VoiceTool(
        operation_id="nav_goto_dashboard",
        http_method="GET",
        path_template="/_nav/site/{site_id}/dashboard",
        description="Vai alla dashboard del sito",
        category=ToolCategory.NAVIGATION,
        path_params=["site_id"],
    ),
    "nav_refresh": VoiceTool(
        operation_id="nav_refresh",
        http_method="GET",
        path_template="/_nav/refresh",
        description="Aggiorna la pagina corrente",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_go_back": VoiceTool(
        operation_id="nav_go_back",
        http_method="GET",
        path_template="/_nav/back",
        description="Torna indietro",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "nav_create_element": VoiceTool(
        operation_id="nav_create_element",
        http_method="GET",
        path_template="/_nav/create/{element_type}",
        description="Crea un nuovo elemento (foto, giornale, us)",
        category=ToolCategory.NAVIGATION,
        path_params=["element_type"],
        site_scoped=False,
    ),
    "ui_select_all": VoiceTool(
        operation_id="ui_select_all",
        http_method="GET",
        path_template="/_ui/select/all",
        description="Seleziona tutti gli elementi nella pagina",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "ui_deselect_all": VoiceTool(
        operation_id="ui_deselect_all",
        http_method="GET",
        path_template="/_ui/select/none",
        description="Deseleziona tutti gli elementi",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
    "ui_set_filter": VoiceTool(
        operation_id="ui_set_filter",
        http_method="GET",
        path_template="/_ui/filter",
        description="Imposta un filtro nella pagina corrente",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
        query_params=["filter_key", "filter_value"],
    ),
    "ui_delete_selected": VoiceTool(
        operation_id="ui_delete_selected",
        http_method="GET",
        path_template="/_ui/delete/selected",
        description="Elimina gli elementi selezionati",
        category=ToolCategory.NAVIGATION,
        site_scoped=False,
    ),
}


# =============================================================================
# VOICE TOOLS REGISTRY - WRITE (10)
# =============================================================================

WRITE_TOOLS: Dict[str, VoiceTool] = {
    # --- Harris Matrix Validation (no confirmation needed) ---
    "v1_validate_relationship": VoiceTool(
        operation_id="v1_validate_relationship",
        http_method="POST",
        path_template="/api/v1/harris-matrix/sites/{site_id}/validate-relationship",
        description="Valida una relazione stratigrafica",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=False,  # Validation only
    ),
    "v1_validate_unit_code": VoiceTool(
        operation_id="v1_validate_unit_code",
        http_method="POST",
        path_template="/api/v1/harris-matrix/sites/{site_id}/validate-code",
        description="Valida un codice unità",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=False,  # Validation only
    ),
    "v1_validate_harris_matrix": VoiceTool(
        operation_id="v1_validate_harris_matrix",
        http_method="POST",
        path_template="/api/v1/harris-matrix/sites/{site_id}/validate",
        description="Valida l'intera Harris Matrix",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
        read_only=False,
        requires_confirmation=False,  # Validation only
    ),
    
    # --- Harris Matrix Layout (confirmation needed) ---
    "v1_save_harris_matrix_layout": VoiceTool(
        operation_id="v1_save_harris_matrix_layout",
        http_method="POST",
        path_template="/api/v1/harris-matrix/sites/{site_id}/layout",
        description="Salva layout Harris Matrix",
        category=ToolCategory.HARRIS_MATRIX,
        path_params=["site_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=True,  # Modifies data
    ),
    
    # --- US/USM Updates (confirmation needed) ---
    "v1_update_us": VoiceTool(
        operation_id="v1_update_us",
        http_method="PUT",
        path_template="/api/v1/us/sites/{site_id}/us/{us_id}",
        description="Aggiorna unità stratigrafica",
        category=ToolCategory.US_USM,
        path_params=["site_id", "us_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=True,
        permission="site_editor",
    ),
    "v1_update_usm": VoiceTool(
        operation_id="v1_update_usm",
        http_method="PUT",
        path_template="/api/v1/us/sites/{site_id}/usm/{usm_id}",
        description="Aggiorna unità stratigrafica muraria",
        category=ToolCategory.US_USM,
        path_params=["site_id", "usm_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=True,
        permission="site_editor",
    ),
    "update_us_file_metadata": VoiceTool(
        operation_id="update_us_file_metadata",
        http_method="PUT",
        path_template="/api/v1/us-files/{file_id}/metadata",
        description="Aggiorna metadati file US",
        category=ToolCategory.US_USM,
        path_params=["file_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=True,
        site_scoped=False,
    ),
    
    # --- ICCD Validation (no confirmation needed) ---
    "validate_iccd_data": VoiceTool(
        operation_id="validate_iccd_data",
        http_method="POST",
        path_template="/api/v1/iccd/validate",
        description="Valida dati ICCD",
        category=ToolCategory.ICCD,
        has_body=True,
        read_only=False,
        requires_confirmation=False,  # Validation only
        site_scoped=False,
    ),
    "validate_iccd_record": VoiceTool(
        operation_id="validate_iccd_record",
        http_method="POST",
        path_template="/api/v1/iccd/site/{site_id}/records/{record_id}/validate",
        description="Valida record ICCD",
        category=ToolCategory.ICCD,
        path_params=["site_id", "record_id"],
        read_only=False,
        requires_confirmation=False,  # Validation only
    ),
    "validate_card_creation": VoiceTool(
        operation_id="validate_card_creation",
        http_method="POST",
        path_template="/api/v1/iccd/site/{site_id}/hierarchy/validate-creation",
        description="Valida creazione scheda ICCD",
        category=ToolCategory.ICCD,
        path_params=["site_id"],
        has_body=True,
        read_only=False,
        requires_confirmation=False,  # Validation only
    ),
}


# =============================================================================
# COMBINED REGISTRY
# =============================================================================

VOICE_TOOLS_REGISTRY: Dict[str, VoiceTool] = {**READ_ONLY_TOOLS, **NAVIGATION_TOOLS, **WRITE_TOOLS}


# =============================================================================
# REGISTRY FUNCTIONS
# =============================================================================

def get_tool(operation_id: str) -> Optional[VoiceTool]:
    """Get a tool by its operationId."""
    return VOICE_TOOLS_REGISTRY.get(operation_id)


def list_tools(
    category: Optional[ToolCategory] = None,
    read_only: Optional[bool] = None,
    site_scoped: Optional[bool] = None,
) -> List[VoiceTool]:
    """List tools with optional filtering."""
    tools = list(VOICE_TOOLS_REGISTRY.values())
    
    if category is not None:
        tools = [t for t in tools if t.category == category]
    if read_only is not None:
        tools = [t for t in tools if t.read_only == read_only]
    if site_scoped is not None:
        tools = [t for t in tools if t.site_scoped == site_scoped]
    
    return tools


def get_tool_descriptions_for_llm() -> List[Dict[str, Any]]:
    """
    Format tools for LLM function-calling prompt.
    Returns a list of tool definitions the LLM can select from.
    """
    descriptions = []
    for tool in VOICE_TOOLS_REGISTRY.values():
        desc = {
            "name": tool.operation_id,
            "description": tool.description,
            "category": tool.category.value,
            "requires_confirmation": tool.requires_confirmation,
        }
        
        # Add parameter info
        params = {}
        if tool.path_params:
            for p in tool.path_params:
                params[p] = {"type": "string", "required": True}
        if tool.query_params:
            for p in tool.query_params:
                params[p] = {"type": "string", "required": False}
        if tool.has_body:
            params["body"] = {"type": "object", "required": True}
        
        if params:
            desc["parameters"] = params
        
        descriptions.append(desc)
    
    return descriptions


def is_tool_whitelisted(operation_id: str) -> bool:
    """Check if an operation is in the whitelist."""
    return operation_id in VOICE_TOOLS_REGISTRY


def validate_tool_args(operation_id: str, args: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate arguments for a tool.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    tool = get_tool(operation_id)
    if not tool:
        return False, f"Tool '{operation_id}' not found in registry"
    
    # Check required path params
    for param in tool.path_params:
        if param not in args:
            return False, f"Missing required path parameter: {param}"
    
    # Check body if required
    if tool.has_body and "body" not in args:
        return False, "Missing required body parameter"
    
    return True, None


def build_path(operation_id: str, args: Dict[str, Any]) -> Optional[str]:
    """
    Build the API path from template and args.
    
    Returns:
        The formatted path or None if tool not found
    """
    tool = get_tool(operation_id)
    if not tool:
        return None
    
    path = tool.path_template
    for param in tool.path_params:
        if param in args:
            path = path.replace(f"{{{param}}}", str(args[param]))
    
    return path


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_voice_execution(
    user_id: UUID,
    site_id: Optional[UUID],
    transcript: str,
    operation_id: str,
    args: Dict[str, Any],
    success: bool,
    error: Optional[str] = None,
):
    """
    Log voice command execution for audit trail.
    """
    logger.info(
        "VOICE_EXECUTION",
        extra={
            "user_id": str(user_id),
            "site_id": str(site_id) if site_id else None,
            "transcript": transcript[:200],  # Truncate long transcripts
            "operation_id": operation_id,
            "args_keys": list(args.keys()),
            "success": success,
            "error": error,
        }
    )
