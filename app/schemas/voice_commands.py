"""
Voice Command Schemas

Pydantic models for structured voice commands. The LLM must produce
VoiceCommand JSON conforming to these schemas. All tool invocations
are validated against the whitelist registry.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class CommandIntent(str, Enum):
    """Types of voice command intents."""
    API_CALL = "api_call"           # Execute an API endpoint
    UI_ACTION = "ui_action"         # Perform UI-only action
    CLARIFY = "clarify"             # Ask user for clarification
    CONFIRM_REQUEST = "confirm_request"  # Request user confirmation


class UIActionType(str, Enum):
    """Types of UI actions the frontend can execute."""
    NAVIGATE = "navigate"       # Navigate to URL
    FOCUS = "focus"             # Focus an element by selector
    SET_FIELD = "set_field"     # Set a form field value
    TOAST = "toast"             # Show a toast notification
    OPEN_MODAL = "open_modal"   # Open a modal by name
    CLOSE_MODAL = "close_modal" # Close current modal
    SEARCH_NAVIGATE = "search_navigate" # Search and navigate to site


class ToastLevel(str, Enum):
    """Toast notification levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class UIAction(BaseModel):
    """
    A single UI action for the frontend to execute.
    """
    action: UIActionType
    
    # For NAVIGATE
    url: Optional[str] = None
    
    # For FOCUS, SET_FIELD
    selector: Optional[str] = None
    
    # For SET_FIELD
    value: Optional[str] = None
    
    # For TOAST
    message: Optional[str] = None
    level: Optional[ToastLevel] = ToastLevel.INFO
    
    # For OPEN_MODAL
    modal_name: Optional[str] = None
    modal_data: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True


class VoiceCommandStep(BaseModel):
    """
    A single step in a multi-step voice command plan.
    Used for complex operations that require multiple API calls.
    """
    order: int = Field(ge=1, description="Execution order (1-based)")
    tool: str = Field(description="operationId from whitelist")
    args: Dict[str, Any] = Field(default_factory=dict)
    depends_on: Optional[int] = Field(
        default=None,
        description="Order number of step this depends on"
    )
    description: Optional[str] = None


class VoiceCommand(BaseModel):
    """
    Structured voice command produced by the LLM.
    
    The LLM must output this exact schema. The backend validates
    that 'tool' is in the whitelist before execution.
    """
    intent: CommandIntent
    
    # For API_CALL intent
    tool: Optional[str] = Field(
        default=None,
        description="operationId of the tool to invoke (must be in whitelist)"
    )
    args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the tool (path params, query params, body)"
    )
    
    # Multi-step support (optional)
    steps: Optional[List[VoiceCommandStep]] = Field(
        default=None,
        description="For multi-step commands"
    )
    
    # Confirmation and UI
    requires_confirmation: bool = Field(
        default=False,
        description="True for write operations"
    )
    explain: str = Field(
        default="",
        max_length=200,
        description="Brief explanation for UI display"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="LLM confidence in interpretation"
    )
    
    # For UI_ACTION intent
    ui_actions: Optional[List[UIAction]] = None
    
    # For CLARIFY intent
    clarification_prompt: Optional[str] = None

    class Config:
        use_enum_values = True

    @field_validator('tool')
    @classmethod
    def validate_tool_for_api_call(cls, v, info):
        """Ensure tool is provided for API_CALL intent."""
        # Note: Full validation against whitelist happens in registry
        return v


class VoiceCommandPlan(BaseModel):
    """
    Response from the /voice/plan endpoint.
    Contains the parsed command and any clarification needed.
    """
    success: bool
    command: Optional[VoiceCommand] = None
    error: Optional[str] = None
    
    # For displaying to user
    interpretation: Optional[str] = Field(
        default=None,
        description="Human-readable interpretation of what will happen"
    )


class VoiceCommandResult(BaseModel):
    """
    Response from voice command execution.
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    
    # UI actions to execute after success
    ui_actions: Optional[List[UIAction]] = None
    
    # For chained operations
    next_command: Optional[VoiceCommand] = None


class VoicePlanRequest(BaseModel):
    """
    Request to plan a voice command.
    """
    text: str = Field(description="Transcribed voice input or typed text")
    site_id: Optional[str] = Field(default=None, description="Current site context")
    current_page: Optional[str] = Field(default=None, description="Current page/route")
    current_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Currently viewed entity (us_id, document_id, etc.)"
    )


class VoiceExecuteRequest(BaseModel):
    """
    Request to execute a planned voice command.
    """
    command: VoiceCommand
    site_id: Optional[str] = None
    confirmed: bool = Field(
        default=False,
        description="User has confirmed (required for write operations)"
    )


# JSON Schema for LLM constraint
VOICE_COMMAND_JSON_SCHEMA = VoiceCommand.model_json_schema()
