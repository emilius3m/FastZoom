"""Tests for GeographicMapService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.geographic_maps import GeographicMapService
from app.exceptions import BusinessLogicError


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_repository():
    """Mock repository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def geographic_map_service(mock_db_session, mock_repository):
    """Create a GeographicMapService instance with mocked dependencies."""
    service = GeographicMapService(mock_db_session)
    service.repository = mock_repository
    return service


@pytest.mark.asyncio
async def test_check_site_access_success(geographic_map_service, mock_db_session):
    """Test successful site access check."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_read.return_value = True
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = mock_site
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.services.geographic_maps.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        site, permission = await geographic_map_service.check_site_access(site_id, user_id)
        
        # Assert
        assert site == mock_site


@pytest.mark.asyncio
async def test_check_site_access_site_not_found(geographic_map_service, mock_db_session):
    """Test site access check when site doesn't exist."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = None  # No site found
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.services.geographic_maps.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act & Assert
        with pytest.raises(BusinessLogicError) as exc_info:
            await geographic_map_service.check_site_access(site_id, user_id)
        
        assert "Sito archeologico non trovato" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_get_site_maps_success(geographic_map_service, mock_repository):
    """Test getting site maps successfully."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    mock_map = MagicMock()
    mock_map.id = uuid4()
    mock_map.site_id = site_id
    mock_map.name = "Test Map"
    mock_map.bounds_north = 41.0
    mock_map.bounds_south = 40.0
    mock_map.bounds_east = 13.0
    mock_map.bounds_west = 12.0
    mock_map.center_lat = 40.5
    mock_map.center_lng = 12.5
    mock_map.created_at = None
    mock_map.updated_at = None
    
    mock_repository.get_site_maps.return_value = [mock_map]
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_read.return_value = True
    geographic_map_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await geographic_map_service.get_site_maps(site_id, user_id)
    
    # Assert
    assert len(result) == 1
    assert result[0]["name"] == "Test Map"
    assert result[0]["bounds"]["north"] == 41.0


@pytest.mark.asyncio
async def test_create_map_success(geographic_map_service, mock_repository):
    """Test creating a map successfully."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    map_data = {
        "name": "New Map",
        "bounds": {
            "north": 41.0,
            "south": 40.0,
            "east": 13.0,
            "west": 12.0
        },
        "center": {
            "lat": 40.5,
            "lng": 12.5
        },
        "is_default": True
    }
    
    mock_new_map = MagicMock()
    mock_new_map.id = uuid4()
    mock_new_map.site_id = site_id
    mock_new_map.name = "New Map"
    
    mock_repository.update_map_default_status = AsyncMock()
    mock_repository.create_map.return_value = mock_new_map
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    geographic_map_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await geographic_map_service.create_map(site_id, map_data, user_id)
    
    # Assert
    assert result["message"] == "Mappa geografica creata con successo"
    assert str(result["map_id"]) == str(mock_new_map.id)
    mock_repository.update_map_default_status.assert_called_once_with(site_id)


@pytest.mark.asyncio
async def test_create_map_permission_denied(geographic_map_service):
    """Test creating a map with insufficient permissions."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    map_data = {"name": "New Map"}
    
    # Mock the permission check to return permission that can't write
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = False
    geographic_map_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act & Assert
    with pytest.raises(BusinessLogicError) as exc_info:
        await geographic_map_service.create_map(site_id, map_data, user_id)
    
    assert "Permessi di scrittura richiesti" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_delete_map_success(geographic_map_service, mock_repository):
    """Test deleting a map successfully."""
    # Arrange
    site_id = uuid4()
    map_id = uuid4()
    user_id = uuid4()
    
    mock_map = MagicMock()
    mock_map.id = map_id
    mock_map.site_id = site_id
    
    mock_repository.get_map_by_id.return_value = mock_map
    mock_repository.delete_map.return_value = True
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    geographic_map_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await geographic_map_service.delete_map(site_id, map_id, user_id)
    
    # Assert
    assert result["message"] == "Mappa geografica eliminata con successo"
    mock_repository.delete_map.assert_called_once_with(map_id)


@pytest.mark.asyncio
async def test_create_marker_success(geographic_map_service, mock_repository):
    """Test creating a marker successfully."""
    # Arrange
    site_id = uuid4()
    map_id = uuid4()
    user_id = uuid4()
    
    marker_data = {
        "latitude": 40.5,
        "longitude": 12.5,
        "title": "Test Marker"
    }
    
    mock_new_marker = MagicMock()
    mock_new_marker.id = uuid4()
    mock_new_marker.map_id = map_id
    mock_new_marker.site_id = site_id
    
    mock_map = MagicMock()
    mock_map.id = map_id
    mock_map.site_id = site_id
    
    mock_repository.get_map_by_id.return_value = mock_map
    mock_repository.create_marker.return_value = mock_new_marker
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    geographic_map_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await geographic_map_service.create_marker(site_id, map_id, marker_data, user_id)
    
    # Assert
    assert result["message"] == "Marker salvato con successo"
    assert str(result["marker_id"]) == str(mock_new_marker.id)
    mock_repository.create_marker.assert_called_once()