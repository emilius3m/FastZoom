"""Tests for GeographicMapRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.geographic_maps import GeographicMap
from app.repositories.geographic_maps import GeographicMapRepository


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def geographic_map_repository(mock_db_session):
    """Create a GeographicMapRepository instance with mocked session."""
    return GeographicMapRepository(mock_db_session)


@pytest.mark.asyncio
async def test_get_site_maps(geographic_map_repository, mock_db_session):
    """Test getting all maps for a site."""
    # Arrange
    site_id = uuid4()
    mock_map = MagicMock(spec=GeographicMap)
    mock_map.id = uuid4()
    mock_map.site_id = site_id
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalars().all.return_value = [mock_map]
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.geographic_maps.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result = await geographic_map_repository.get_site_maps(site_id)
        
        # Assert
        assert result == [mock_map]
        mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_map_by_id(geographic_map_repository, mock_db_session):
    """Test getting a map by ID and site ID."""
    # Arrange
    map_id = uuid4()
    site_id = uuid4()
    mock_map = MagicMock(spec=GeographicMap)
    mock_map.id = map_id
    mock_map.site_id = site_id
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = mock_map
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.geographic_maps.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result = await geographic_map_repository.get_map_by_id(map_id, site_id)
        
        # Assert
        assert result == mock_map
        mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_map(geographic_map_repository, mock_db_session):
    """Test creating a new geographic map."""
    # Arrange
    map_data = {
        "site_id": uuid4(),
        "name": "Test Map",
        "description": "Test Description"
    }
    
    mock_map = MagicMock(spec=GeographicMap)
    mock_map.id = uuid4()
    for key, value in map_data.items():
        setattr(mock_map, key, value)
    
    # Act
    result = await geographic_map_repository.create_map(map_data)
    
    # Assert
    assert result is not None
    mock_db_session.add.assert_called_once_with(result)
    mock_db_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_map(geographic_map_repository, mock_db_session):
    """Test deleting a geographic map."""
    # Arrange
    map_id = uuid4()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    
    mock_db_session.execute.return_value = mock_result
    
    # Act
    result = await geographic_map_repository.delete_map(map_id)
    
    # Assert
    assert result is True
    mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_map_layers(geographic_map_repository, mock_db_session):
    """Test getting all layers for a map."""
    # Arrange
    map_id = uuid4()
    mock_layer = MagicMock()
    mock_layer.map_id = map_id
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalars().all.return_value = [mock_layer]
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.geographic_maps.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result = await geographic_map_repository.get_map_layers(map_id)
        
        # Assert
        assert result == [mock_layer]
        mock_db_session.execute.assert_called_once()