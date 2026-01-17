"""
Unit Tests for Voice Tools Registry

Tests for voice tool registration, validation, and execution helpers.
"""

import pytest
from uuid import uuid4

from app.services.voice_tools_registry import (
    VOICE_TOOLS_REGISTRY,
    READ_ONLY_TOOLS,
    WRITE_TOOLS,
    VoiceTool,
    ToolCategory,
    get_tool,
    list_tools,
    is_tool_whitelisted,
    validate_tool_args,
    build_path,
    get_tool_descriptions_for_llm,
)


class TestVoiceToolsRegistry:
    """Tests for the voice tools registry."""
    
    def test_registry_has_tools(self):
        """Test that registry is populated."""
        assert len(VOICE_TOOLS_REGISTRY) > 0
        assert len(READ_ONLY_TOOLS) == 30
        assert len(WRITE_TOOLS) == 10
    
    def test_combined_registry(self):
        """Test that combined registry has all tools."""
        expected_count = len(READ_ONLY_TOOLS) + len(WRITE_TOOLS)
        assert len(VOICE_TOOLS_REGISTRY) == expected_count


class TestGetTool:
    """Tests for get_tool function."""
    
    def test_get_existing_tool(self):
        """Test getting an existing tool."""
        tool = get_tool("v1_get_sites_list")
        assert tool is not None
        assert tool.operation_id == "v1_get_sites_list"
        assert tool.http_method == "GET"
    
    def test_get_nonexistent_tool(self):
        """Test getting a non-existent tool."""
        tool = get_tool("nonexistent_tool")
        assert tool is None
    
    def test_get_write_tool(self):
        """Test getting a write tool."""
        tool = get_tool("v1_update_us")
        assert tool is not None
        assert tool.requires_confirmation == True
        assert tool.read_only == False


class TestListTools:
    """Tests for list_tools function."""
    
    def test_list_all_tools(self):
        """Test listing all tools."""
        tools = list_tools()
        assert len(tools) == 40
    
    def test_filter_by_category(self):
        """Test filtering by category."""
        dashboard_tools = list_tools(category=ToolCategory.DASHBOARD)
        assert len(dashboard_tools) > 0
        for tool in dashboard_tools:
            assert tool.category == ToolCategory.DASHBOARD
    
    def test_filter_by_read_only(self):
        """Test filtering by read_only flag."""
        read_only = list_tools(read_only=True)
        assert len(read_only) == 30
        for tool in read_only:
            assert tool.read_only == True
        
        write = list_tools(read_only=False)
        assert len(write) == 10
        for tool in write:
            assert tool.read_only == False
    
    def test_filter_by_site_scoped(self):
        """Test filtering by site_scoped flag."""
        site_scoped = list_tools(site_scoped=True)
        assert len(site_scoped) > 0
        for tool in site_scoped:
            assert tool.site_scoped == True


class TestIsToolWhitelisted:
    """Tests for is_tool_whitelisted function."""
    
    def test_whitelisted_read_tool(self):
        """Test that read tools are whitelisted."""
        assert is_tool_whitelisted("v1_get_sites_list") == True
        assert is_tool_whitelisted("get_site_photos") == True
    
    def test_whitelisted_write_tool(self):
        """Test that write tools are whitelisted."""
        assert is_tool_whitelisted("v1_update_us") == True
        assert is_tool_whitelisted("v1_validate_harris_matrix") == True
    
    def test_non_whitelisted_tool(self):
        """Test that non-whitelisted tools are rejected."""
        assert is_tool_whitelisted("delete_everything") == False
        assert is_tool_whitelisted("execute_sql") == False
        assert is_tool_whitelisted("") == False


class TestValidateToolArgs:
    """Tests for validate_tool_args function."""
    
    def test_valid_args_no_params(self):
        """Test validation with no required params."""
        is_valid, error = validate_tool_args("v1_get_sites_list", {})
        assert is_valid == True
        assert error is None
    
    def test_valid_args_with_path_params(self):
        """Test validation with required path params."""
        is_valid, error = validate_tool_args(
            "get_site_photos",
            {"site_id": "123"}
        )
        assert is_valid == True
        assert error is None
    
    def test_missing_path_param(self):
        """Test validation fails when path param is missing."""
        is_valid, error = validate_tool_args("get_site_photos", {})
        assert is_valid == False
        assert "site_id" in error
    
    def test_missing_body(self):
        """Test validation fails when body is required but missing."""
        is_valid, error = validate_tool_args(
            "v1_update_us",
            {"site_id": "123", "us_id": "456"}
        )
        assert is_valid == False
        assert "body" in error
    
    def test_valid_with_body(self):
        """Test validation passes when body is provided."""
        is_valid, error = validate_tool_args(
            "v1_update_us",
            {"site_id": "123", "us_id": "456", "body": {"description": "new"}}
        )
        assert is_valid == True
    
    def test_nonexistent_tool(self):
        """Test validation fails for non-existent tool."""
        is_valid, error = validate_tool_args("fake_tool", {})
        assert is_valid == False
        assert "not found" in error


class TestBuildPath:
    """Tests for build_path function."""
    
    def test_build_simple_path(self):
        """Test building a path with no params."""
        path = build_path("v1_get_sites_list", {})
        assert path == "/api/v1/unified/dashboard/sites/list"
    
    def test_build_path_with_one_param(self):
        """Test building a path with one param."""
        path = build_path("get_site_photos", {"site_id": "abc-123"})
        assert path == "/api/v1/sites/abc-123/photos"
    
    def test_build_path_with_multiple_params(self):
        """Test building a path with multiple params."""
        path = build_path(
            "v1_get_us",
            {"site_id": "site-123", "us_id": "us-456"}
        )
        assert path == "/api/v1/us/sites/site-123/us/us-456"
    
    def test_build_path_nonexistent_tool(self):
        """Test that non-existent tool returns None."""
        path = build_path("fake_tool", {})
        assert path is None


class TestGetToolDescriptionsForLLM:
    """Tests for get_tool_descriptions_for_llm function."""
    
    def test_returns_list(self):
        """Test that function returns a list."""
        descriptions = get_tool_descriptions_for_llm()
        assert isinstance(descriptions, list)
        assert len(descriptions) == 40
    
    def test_description_format(self):
        """Test that each description has required fields."""
        descriptions = get_tool_descriptions_for_llm()
        for desc in descriptions:
            assert "name" in desc
            assert "description" in desc
            assert "category" in desc
            assert "requires_confirmation" in desc
    
    def test_read_tools_no_confirmation(self):
        """Test that read tools don't require confirmation."""
        descriptions = get_tool_descriptions_for_llm()
        sites_list = next(d for d in descriptions if d["name"] == "v1_get_sites_list")
        assert sites_list["requires_confirmation"] == False
    
    def test_write_tools_with_confirmation(self):
        """Test that certain write tools require confirmation."""
        descriptions = get_tool_descriptions_for_llm()
        update_us = next(d for d in descriptions if d["name"] == "v1_update_us")
        assert update_us["requires_confirmation"] == True


class TestToolCategoryDistribution:
    """Tests for tool category distribution."""
    
    def test_dashboard_tools(self):
        """Test dashboard tools exist."""
        dashboard = list_tools(category=ToolCategory.DASHBOARD)
        assert len(dashboard) >= 5
    
    def test_photos_tools(self):
        """Test photos tools exist."""
        photos = list_tools(category=ToolCategory.PHOTOS)
        assert len(photos) >= 5
    
    def test_harris_matrix_tools(self):
        """Test Harris Matrix tools exist."""
        harris = list_tools(category=ToolCategory.HARRIS_MATRIX)
        assert len(harris) >= 5
    
    def test_us_usm_tools(self):
        """Test US/USM tools exist."""
        us = list_tools(category=ToolCategory.US_USM)
        assert len(us) >= 4


class TestSecurityFlags:
    """Tests for security-related flags on tools."""
    
    def test_update_tools_require_confirmation(self):
        """Test that update tools require confirmation."""
        update_us = get_tool("v1_update_us")
        update_usm = get_tool("v1_update_usm")
        
        assert update_us.requires_confirmation == True
        assert update_usm.requires_confirmation == True
    
    def test_validate_tools_no_confirmation(self):
        """Test that validate tools don't require confirmation."""
        validate_relationship = get_tool("v1_validate_relationship")
        validate_code = get_tool("v1_validate_unit_code")
        validate_matrix = get_tool("v1_validate_harris_matrix")
        
        assert validate_relationship.requires_confirmation == False
        assert validate_code.requires_confirmation == False
        assert validate_matrix.requires_confirmation == False
    
    def test_read_tools_are_readonly(self):
        """Test that GET tools are marked as read_only."""
        for tool in READ_ONLY_TOOLS.values():
            assert tool.read_only == True
            assert tool.http_method == "GET"
    
    def test_write_tools_not_readonly(self):
        """Test that write tools are not marked as read_only."""
        for tool in WRITE_TOOLS.values():
            assert tool.read_only == False
            assert tool.http_method in ["POST", "PUT"]
