"""Tests for Geographic Maps API routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from app.app import app
from app.services.geographic_maps import GeographicMapService
from app.exceptions import BusinessLogicError


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


@pytest.fixture
def mock_geographic_map_service():
    """Mock the geographic map service."""
    service = MagicMock(spec=GeographicMapService)
    return service


@pytest.mark.asyncio
async def test_get_site_geographic_maps_success(client, mock_geographic_map_service):
    """Test getting site geographic maps successfully."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    mock_maps = [
        {
            "id": str(uuid4()),
            "name": "Test Map",
            "bounds": {"north": 41.0, "south": 40.0, "east": 13.0, "west": 12.0},
            "center": {"lat": 40.5, "lng": 12.5},
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }
    ]
    
    # Mock the service dependency
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.get_site_maps.return_value = mock_maps
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/geographic-map/site/{site_id}/maps")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["site_id"] == site_id
            assert len(data["maps"]) == 1
            assert data["maps"][0]["name"] == "Test Map"


@pytest.mark.asyncio
async def test_get_site_geographic_maps_business_error(client, mock_geographic_map_service):
    """Test getting site geographic maps with business error."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    # Mock the service to raise a BusinessLogicError
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.get_site_maps.side_effect = BusinessLogicError(
            "Permessi di lettura richiesti", 403
        )
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/geographic-map/site/{site_id}/maps")
            
            # Assert
            assert response.status_code == 403
            assert "Permessi di lettura richiesti" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_geographic_map_success(client, mock_geographic_map_service):
    """Test creating a geographic map successfully."""
    # Arrange
    site_id = str(uuid4())
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
    
    expected_result = {
        "message": "Mappa geografica creata con successo",
        "map_id": str(uuid4()),
        "map_data": {
            "id": str(uuid4()),
            "name": "New Map"
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.create_map.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/geographic-map/site/{site_id}/maps", json=map_data)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Mappa geografica creata con successo"
            assert data["map_id"] == expected_result["map_id"]


@pytest.mark.asyncio
async def test_create_geographic_map_business_error(client, mock_geographic_map_service):
    """Test creating a geographic map with business error."""
    # Arrange
    site_id = str(uuid4())
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
        }
    }
    
    # Mock the service to raise a BusinessLogicError
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.create_map.side_effect = BusinessLogicError(
            "Permessi di scrittura richiesti", 403
        )
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/geographic-map/site/{site_id}/maps", json=map_data)
            
            # Assert
            assert response.status_code == 403
            assert "Permessi di scrittura richiesti" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_geographic_map_details_success(client, mock_geographic_map_service):
    """Test getting geographic map details successfully."""
    # Arrange
    site_id = str(uuid4())
    map_id = str(uuid4())
    user_id = uuid4()
    
    expected_result = {
        "id": map_id,
        "site_id": site_id,
        "name": "Test Map",
        "bounds": {"north": 41.0, "south": 40.0, "east": 13.0, "west": 12.0},
        "center": {"lat": 40.5, "lng": 12.5},
        "layers": [],
        "markers": []
    }
    
    # Mock the service dependency
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.get_map_details.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/geographic-map/site/{site_id}/maps/{map_id}")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Test Map"
            assert data["id"] == map_id


@pytest.mark.asyncio
async def test_delete_geographic_map_success(client, mock_geographic_map_service):
    """Test deleting a geographic map successfully."""
    # Arrange
    site_id = str(uuid4())
    map_id = str(uuid4())
    user_id = uuid4()
    
    expected_result = {
        "message": "Mappa geografica eliminata con successo"
    }
    
    # Mock the service dependency
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.delete_map.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.delete(f"/api/geographic-map/site/{site_id}/maps/{map_id}")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Mappa geografica eliminata con successo"


@pytest.mark.asyncio
async def test_create_marker_success(client, mock_geographic_map_service):
    """Test creating a marker successfully."""
    # Arrange
    site_id = str(uuid4())
    map_id = str(uuid4())
    user_id = uuid4()
    
    marker_data = {
        "latitude": 40.5,
        "longitude": 12.5,
        "title": "Test Marker"
    }
    
    expected_result = {
        "message": "Marker salvato con successo",
        "marker_id": str(uuid4()),
        "marker_data": {
            "id": str(uuid4()),
            "title": "Test Marker"
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.geographic_maps.get_geographic_map_service') as mock_service_getter:
        mock_service_getter.return_value = mock_geographic_map_service
        mock_geographic_map_service.create_marker.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/geographic-map/site/{site_id}/maps/{map_id}/markers", json=marker_data)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Marker salvato con successo"
            assert data["marker_id"] == expected_result["marker_id"]