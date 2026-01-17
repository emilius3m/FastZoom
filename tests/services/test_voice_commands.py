"""
Unit Tests for Voice Command Schemas

Tests for VoiceCommand, VoiceCommandPlan, VoiceCommandResult models.
"""

import pytest
from pydantic import ValidationError

from app.schemas.voice_commands import (
    VoiceCommand,
    VoiceCommandStep,
    VoiceCommandPlan,
    VoiceCommandResult,
    UIAction,
    UIActionType,
    CommandIntent,
    ToastLevel,
    VoicePlanRequest,
    VoiceExecuteRequest,
)


class TestVoiceCommand:
    """Tests for VoiceCommand schema."""
    
    def test_api_call_intent(self):
        """Test creating an API call command."""
        cmd = VoiceCommand(
            intent=CommandIntent.API_CALL,
            tool="v1_get_sites_list",
            args={},
            explain="Ottiene la lista dei siti",
            confidence=0.95,
        )
        assert cmd.intent == "api_call"
        assert cmd.tool == "v1_get_sites_list"
        assert cmd.confidence == 0.95
        assert cmd.requires_confirmation == False
    
    def test_ui_action_intent(self):
        """Test creating a UI action command."""
        cmd = VoiceCommand(
            intent=CommandIntent.UI_ACTION,
            explain="Naviga alle foto",
            ui_actions=[
                UIAction(
                    action=UIActionType.NAVIGATE,
                    url="/view/site-123/photos"
                )
            ]
        )
        assert cmd.intent == "ui_action"
        assert len(cmd.ui_actions) == 1
        assert cmd.ui_actions[0].action == "navigate"
    
    def test_clarify_intent(self):
        """Test creating a clarification command."""
        cmd = VoiceCommand(
            intent=CommandIntent.CLARIFY,
            explain="Non ho capito",
            clarification_prompt="Puoi specificare quale sito?"
        )
        assert cmd.intent == "clarify"
        assert cmd.clarification_prompt is not None
    
    def test_confidence_validation(self):
        """Test that confidence must be between 0 and 1."""
        # Valid confidence
        cmd = VoiceCommand(
            intent=CommandIntent.CLARIFY,
            explain="Test",
            confidence=0.5
        )
        assert cmd.confidence == 0.5
        
        # Invalid confidence (too high)
        with pytest.raises(ValidationError):
            VoiceCommand(
                intent=CommandIntent.CLARIFY,
                explain="Test",
                confidence=1.5
            )
        
        # Invalid confidence (negative)
        with pytest.raises(ValidationError):
            VoiceCommand(
                intent=CommandIntent.CLARIFY,
                explain="Test",
                confidence=-0.1
            )
    
    def test_requires_confirmation(self):
        """Test requires_confirmation field."""
        cmd = VoiceCommand(
            intent=CommandIntent.API_CALL,
            tool="v1_update_us",
            args={"site_id": "123", "us_id": "456"},
            requires_confirmation=True,
            explain="Aggiorna unità stratigrafica"
        )
        assert cmd.requires_confirmation == True
    
    def test_multi_step_command(self):
        """Test multi-step command plan."""
        cmd = VoiceCommand(
            intent=CommandIntent.API_CALL,
            explain="Piano multi-step",
            steps=[
                VoiceCommandStep(
                    order=1,
                    tool="v1_get_site_dashboard_stats",
                    args={"site_id": "123"},
                    description="Ottieni statistiche"
                ),
                VoiceCommandStep(
                    order=2,
                    tool="v1_list_us",
                    args={"site_id": "123"},
                    depends_on=1,
                    description="Lista US"
                )
            ]
        )
        assert len(cmd.steps) == 2
        assert cmd.steps[1].depends_on == 1


class TestUIAction:
    """Tests for UIAction schema."""
    
    def test_navigate_action(self):
        """Test navigate UI action."""
        action = UIAction(
            action=UIActionType.NAVIGATE,
            url="/view/site-123/photos"
        )
        assert action.action == "navigate"
        assert action.url == "/view/site-123/photos"
    
    def test_focus_action(self):
        """Test focus UI action."""
        action = UIAction(
            action=UIActionType.FOCUS,
            selector="#search-input"
        )
        assert action.action == "focus"
        assert action.selector == "#search-input"
    
    def test_set_field_action(self):
        """Test set_field UI action."""
        action = UIAction(
            action=UIActionType.SET_FIELD,
            selector="input[name='title']",
            value="Nuovo titolo"
        )
        assert action.action == "set_field"
        assert action.value == "Nuovo titolo"
    
    def test_toast_action(self):
        """Test toast UI action."""
        action = UIAction(
            action=UIActionType.TOAST,
            message="Operazione completata",
            level=ToastLevel.SUCCESS
        )
        assert action.action == "toast"
        assert action.level == "success"


class TestVoiceCommandPlan:
    """Tests for VoiceCommandPlan schema."""
    
    def test_successful_plan(self):
        """Test successful command plan."""
        plan = VoiceCommandPlan(
            success=True,
            command=VoiceCommand(
                intent=CommandIntent.API_CALL,
                tool="get_site_photos",
                args={"site_id": "123"},
                explain="Mostra le foto del sito"
            ),
            interpretation="Mostrerò le foto del sito selezionato"
        )
        assert plan.success == True
        assert plan.command is not None
        assert plan.error is None
    
    def test_failed_plan(self):
        """Test failed command plan."""
        plan = VoiceCommandPlan(
            success=False,
            error="Tool 'invalid_tool' not in whitelist"
        )
        assert plan.success == False
        assert plan.command is None
        assert "whitelist" in plan.error


class TestVoiceCommandResult:
    """Tests for VoiceCommandResult schema."""
    
    def test_successful_result(self):
        """Test successful command result."""
        result = VoiceCommandResult(
            success=True,
            data={"photos": [{"id": "1", "name": "photo1.jpg"}]},
            message="Trovate 1 foto",
            ui_actions=[
                UIAction(
                    action=UIActionType.TOAST,
                    message="1 foto trovata",
                    level=ToastLevel.SUCCESS
                )
            ]
        )
        assert result.success == True
        assert result.data is not None
        assert len(result.ui_actions) == 1
    
    def test_failed_result(self):
        """Test failed command result."""
        result = VoiceCommandResult(
            success=False,
            error="Authorization denied",
            message="Non hai i permessi per questa operazione"
        )
        assert result.success == False
        assert result.error is not None


class TestVoicePlanRequest:
    """Tests for VoicePlanRequest schema."""
    
    def test_basic_request(self):
        """Test basic plan request."""
        request = VoicePlanRequest(
            text="mostrami le foto",
            site_id="123",
            current_page="/view/123/dashboard"
        )
        assert request.text == "mostrami le foto"
        assert request.site_id == "123"
    
    def test_request_with_entity(self):
        """Test plan request with current entity."""
        request = VoicePlanRequest(
            text="aggiorna questa US",
            site_id="123",
            current_page="/view/123/us/456",
            current_entity={"type": "us", "id": "456"}
        )
        assert request.current_entity["type"] == "us"


class TestVoiceExecuteRequest:
    """Tests for VoiceExecuteRequest schema."""
    
    def test_unconfirmed_request(self):
        """Test unconfirmed execute request."""
        request = VoiceExecuteRequest(
            command=VoiceCommand(
                intent=CommandIntent.API_CALL,
                tool="get_site_photos",
                args={"site_id": "123"},
                explain="Mostra foto"
            ),
            site_id="123",
            confirmed=False
        )
        assert request.confirmed == False
    
    def test_confirmed_request(self):
        """Test confirmed execute request."""
        request = VoiceExecuteRequest(
            command=VoiceCommand(
                intent=CommandIntent.API_CALL,
                tool="v1_update_us",
                args={"site_id": "123", "us_id": "456"},
                requires_confirmation=True,
                explain="Aggiorna US"
            ),
            site_id="123",
            confirmed=True
        )
        assert request.confirmed == True
