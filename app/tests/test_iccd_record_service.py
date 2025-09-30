"""Tests for ICCDRecordService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.iccd_records import ICCDRecordService
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
def iccd_record_service(mock_db_session, mock_repository):
    """Create an ICCDRecordService instance with mocked dependencies."""
    service = ICCDRecordService(mock_db_session)
    service.repository = mock_repository
    return service


@pytest.mark.asyncio
async def test_check_site_access_success(iccd_record_service, mock_db_session):
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
        mp.setattr("app.services.iccd_records.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        site, permission = await iccd_record_service.check_site_access(site_id, user_id)
        
        # Assert
        assert site == mock_site


@pytest.mark.asyncio
async def test_check_site_access_site_not_found(iccd_record_service, mock_db_session):
    """Test site access check when site doesn't exist."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = None # No site found
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.services.iccd_records.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act & Assert
        with pytest.raises(BusinessLogicError) as exc_info:
            await iccd_record_service.check_site_access(site_id, user_id)
        
        assert "Sito archeologico non trovato" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_get_site_records_success(iccd_record_service, mock_repository):
    """Test getting site records successfully."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    mock_record = MagicMock()
    mock_record.id = uuid4()
    mock_record.site_id = site_id
    mock_record.schema_type = "RA"
    mock_record.level = "P"
    mock_record.to_dict.return_value = {
        "id": str(mock_record.id),
        "schema_type": "RA",
        "level": "P"
    }
    
    mock_repository.get_site_records.return_value = ([mock_record], 1)
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_read.return_value = True
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await iccd_record_service.get_site_records(site_id, user_id)
    
    # Assert
    assert result["site_id"] == str(site_id)
    assert len(result["records"]) == 1
    assert result["records"][0]["schema_type"] == "RA"


@pytest.mark.asyncio
async def test_create_record_success(iccd_record_service, mock_repository):
    """Test creating a record successfully."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    
    record_data = {
        "schema_type": "RA",
        "level": "P",
        "iccd_data": {
            "CD": {
                "NCT": {
                    "NCTR": "12",
                    "NCTN": "24000001"
                }
            }
        },
        "cataloging_institution": "Test Institution"
    }
    
    mock_new_record = MagicMock()
    mock_new_record.id = uuid4()
    mock_new_record.nct_region = "12"
    mock_new_record.nct_number = "24000001"
    mock_new_record.get_nct.return_value = "12/24000001"
    mock_new_record.to_dict.return_value = {
        "id": str(mock_new_record.id),
        "nct": "12/24000001"
    }
    
    mock_repository.check_nct_exists.return_value = False
    mock_repository.create_record.return_value = mock_new_record
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await iccd_record_service.create_record(site_id, record_data, user_id)
    
    # Assert
    assert result["message"] == "Scheda ICCD creata con successo"
    assert str(result["record_id"]) == str(mock_new_record.id)
    assert result["nct"] == "12/240001"


@pytest.mark.asyncio
async def test_create_record_missing_required_field(iccd_record_service):
    """Test creating a record with missing required fields."""
    # Arrange
    site_id = uuid4()
    user_id = uuid4()
    record_data = {
        "schema_type": "RA",
        # Missing required fields
    }
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act & Assert
    with pytest.raises(BusinessLogicError) as exc_info:
        await iccd_record_service.create_record(site_id, record_data, user_id)
    
    assert "Campo obbligatorio mancante" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_get_record_by_id_success(iccd_record_service, mock_repository):
    """Test getting a record by ID successfully."""
    # Arrange
    site_id = uuid4()
    record_id = uuid4()
    user_id = uuid4()
    
    mock_record = MagicMock()
    mock_record.id = record_id
    mock_record.site_id = site_id
    mock_record.to_dict.return_value = {
        "id": str(record_id),
        "schema_type": "RA"
    }
    
    mock_repository.get_record_by_id.return_value = mock_record
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_read.return_value = True
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await iccd_record_service.get_record_by_id(site_id, record_id, user_id)
    
    # Assert
    assert result["id"] == str(record_id)
    assert result["schema_type"] == "RA"


@pytest.mark.asyncio
async def test_update_record_success(iccd_record_service, mock_repository):
    """Test updating a record successfully."""
    # Arrange
    site_id = uuid4()
    record_id = uuid4()
    user_id = uuid4()
    
    update_data = {
        "level": "C",
        "status": "validated"
    }
    
    mock_record = MagicMock()
    mock_record.id = record_id
    mock_record.site_id = site_id
    mock_record.level = "P"
    mock_record.status = "draft"
    mock_record.to_dict.return_value = {
        "id": str(record_id),
        "level": "C",
        "status": "validated"
    }
    
    mock_repository.get_record_by_id.return_value = mock_record
    
    # Mock the permission check
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_write.return_value = True
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await iccd_record_service.update_record(site_id, record_id, update_data, user_id)
    
    # Assert
    assert result["message"] == "Scheda ICCD aggiornata con successo"
    assert mock_record.level == "C"
    assert mock_record.status == "validated"


@pytest.mark.asyncio
async def test_validate_record_success(iccd_record_service, mock_repository):
    """Test validating a record successfully."""
    # Arrange
    site_id = uuid4()
    record_id = uuid4()
    user_id = uuid4()
    
    validation_data = {
        "is_valid": True,
        "notes": "Valid record"
    }
    
    mock_record = MagicMock()
    mock_record.id = record_id
    mock_record.site_id = site_id
    mock_record.level = "P"
    mock_record.status = "draft"
    mock_record.get_nct.return_value = "12/24000001"
    mock_record.to_dict.return_value = {
        "id": str(record_id),
        "status": "validated"
    }
    
    # Mock the is_complete_for_level method
    mock_record.is_complete_for_level.return_value = (True, [])
    
    mock_repository.get_record_by_id.return_value = mock_record
    
    # Mock the permission check (admin required for validation)
    mock_site = MagicMock()
    mock_permission = MagicMock()
    mock_permission.can_admin.return_value = True  # Admin permission
    iccd_record_service.check_site_access = AsyncMock(return_value=(mock_site, mock_permission))
    
    # Act
    result = await iccd_record_service.validate_record(site_id, record_id, validation_data, user_id)
    
    # Assert
    assert result["message"] == "Scheda ICCD validata con successo"
    assert mock_record.status == "validated"
    assert mock_record.validated_by == user_id