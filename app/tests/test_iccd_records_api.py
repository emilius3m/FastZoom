"""Tests for ICCD Records API routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from app.app import app
from app.services.iccd_records import ICCDRecordService
from app.exceptions import BusinessLogicError


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


@pytest.fixture
def mock_iccd_record_service():
    """Mock the ICCD record service."""
    service = MagicMock(spec=ICCDRecordService)
    return service


@pytest.mark.asyncio
async def test_get_site_iccd_records_success(client, mock_iccd_record_service):
    """Test getting site ICCD records successfully."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    expected_result = {
        "site_id": site_id,
        "records": [
            {
                "id": str(uuid4()),
                "schema_type": "RA",
                "level": "P",
                "nct": "12/2400001"
            }
        ],
        "pagination": {
            "page": 1,
            "size": 20,
            "total": 1,
            "pages": 1
        },
        "filters": {}
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.get_site_records.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/iccd/sites/{site_id}/records")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["site_id"] == site_id
            assert len(data["records"]) == 1
            assert data["records"][0]["schema_type"] == "RA"


@pytest.mark.asyncio
async def test_get_site_iccd_records_business_error(client, mock_iccd_record_service):
    """Test getting site ICCD records with business error."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    # Mock the service to raise a BusinessLogicError
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.get_site_records.side_effect = BusinessLogicError(
            "Permessi di lettura richiesti", 403
        )
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/iccd/sites/{site_id}/records")
            
            # Assert
            assert response.status_code == 403
            assert "Permessi di lettura richiesti" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_iccd_record_success(client, mock_iccd_record_service):
    """Test creating an ICCD record successfully."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    record_data = {
        "schema_type": "RA",
        "level": "P",
        "iccd_data": {
            "CD": {
                "NCT": {
                    "NCTR": "12",
                    "NCTN": "240001"
                }
            }
        },
        "cataloging_institution": "Test Institution"
    }
    
    expected_result = {
        "message": "Scheda ICCD creata con successo",
        "record_id": str(uuid4()),
        "nct": "12/2400001",
        "record": {
            "id": str(uuid4()),
            "schema_type": "RA",
            "level": "P"
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.create_record.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/iccd/sites/{site_id}/records", json=record_data)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Scheda ICCD creata con successo"
            assert data["nct"] == "12/240001"


@pytest.mark.asyncio
async def test_create_iccd_record_business_error(client, mock_iccd_record_service):
    """Test creating an ICCD record with business error."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    record_data = {
        "schema_type": "RA",
        "level": "P",
        "iccd_data": {
            "CD": {
                "NCT": {
                    "NCTR": "12",
                    "NCTN": "24001"
                }
            }
        },
        "cataloging_institution": "Test Institution"
    }
    
    # Mock the service to raise a BusinessLogicError
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.create_record.side_effect = BusinessLogicError(
            "Permessi di scrittura richiesti", 403
        )
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/iccd/sites/{site_id}/records", json=record_data)
            
            # Assert
            assert response.status_code == 403
            assert "Permessi di scrittura richiesti" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_iccd_record_success(client, mock_iccd_record_service):
    """Test getting an ICCD record successfully."""
    # Arrange
    site_id = str(uuid4())
    record_id = str(uuid4())
    user_id = uuid4()
    
    expected_result = {
        "id": record_id,
        "schema_type": "RA",
        "level": "P",
        "nct": "12/24000001"
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.get_record_by_id.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/iccd/sites/{site_id}/records/{record_id}")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["schema_type"] == "RA"
            assert data["nct"] == "12/2400001"


@pytest.mark.asyncio
async def test_update_iccd_record_success(client, mock_iccd_record_service):
    """Test updating an ICCD record successfully."""
    # Arrange
    site_id = str(uuid4())
    record_id = str(uuid4())
    user_id = uuid4()
    
    update_data = {
        "level": "C",
        "status": "validated"
    }
    
    expected_result = {
        "message": "Scheda ICCD aggiornata con successo",
        "record": {
            "id": record_id,
            "level": "C",
            "status": "validated"
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.update_record.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.put(f"/api/iccd/sites/{site_id}/records/{record_id}", json=update_data)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Scheda ICCD aggiornata con successo"
            assert data["record"]["level"] == "C"


@pytest.mark.asyncio
async def test_validate_iccd_record_success(client, mock_iccd_record_service):
    """Test validating an ICCD record successfully."""
    # Arrange
    site_id = str(uuid4())
    record_id = str(uuid4())
    user_id = uuid4()
    
    validation_data = {
        "is_valid": True,
        "notes": "Valid record"
    }
    
    expected_result = {
        "message": "Scheda ICCD validata con successo",
        "record": {
            "id": record_id,
            "status": "validated"
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.validate_record.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.post(f"/api/iccd/sites/{site_id}/records/{record_id}/validate", json=validation_data)
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Scheda ICCD validata con successo"
            assert data["record"]["status"] == "validated"


@pytest.mark.asyncio
async def test_get_iccd_statistics_success(client, mock_iccd_record_service):
    """Test getting ICCD statistics successfully."""
    # Arrange
    site_id = str(uuid4())
    user_id = uuid4()
    
    expected_result = {
        "site_id": site_id,
        "statistics": {
            "total_records": 10,
            "validated_records": 5,
            "validation_percentage": 50.0,
            "by_schema_type": {"RA": 5, "SI": 3, "CA": 2},
            "by_level": {"P": 6, "C": 3, "A": 1},
            "by_status": {"draft": 5, "validated": 5}
        }
    }
    
    # Mock the service dependency
    with patch('app.routes.api.iccd_records.get_iccd_record_service') as mock_service_getter:
        mock_service_getter.return_value = mock_iccd_record_service
        mock_iccd_record_service.get_record_statistics.return_value = expected_result
        
        # Mock the security dependency to return a user ID
        with patch('app.core.security.get_current_user_id') as mock_get_current_user:
            mock_get_current_user.return_value = user_id
            
            # Act
            response = client.get(f"/api/iccd/sites/{site_id}/statistics")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["site_id"] == site_id
            assert data["statistics"]["total_records"] == 10
            assert data["statistics"]["validation_percentage"] == 50.0