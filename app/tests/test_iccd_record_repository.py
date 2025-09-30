"""Tests for ICCDRecordRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.iccd_records import ICCDRecord
from app.repositories.iccd_records import ICCDRecordRepository


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def iccd_record_repository(mock_db_session):
    """Create an ICCDRecordRepository instance with mocked session."""
    return ICCDRecordRepository(mock_db_session)


@pytest.mark.asyncio
async def test_get_site_records(iccd_record_repository, mock_db_session):
    """Test getting all records for a site with filters."""
    # Arrange
    site_id = uuid4()
    mock_record = MagicMock(spec=ICCDRecord)
    mock_record.id = uuid4()
    mock_record.site_id = site_id
    mock_record.schema_type = "RA"
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalars().all.return_value = [mock_record]
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.iccd_records.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result, total = await iccd_record_repository.get_site_records(site_id)
        
        # Assert
        assert result == [mock_record]
        assert total >= 0
        mock_db_session.execute.assert_called()


@pytest.mark.asyncio
async def test_get_record_by_id(iccd_record_repository, mock_db_session):
    """Test getting a record by ID and site ID."""
    # Arrange
    record_id = uuid4()
    site_id = uuid4()
    mock_record = MagicMock(spec=ICCDRecord)
    mock_record.id = record_id
    mock_record.site_id = site_id
    
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = mock_record
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.iccd_records.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result = await iccd_record_repository.get_record_by_id(record_id, site_id)
        
        # Assert
        assert result == mock_record
        mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_record(iccd_record_repository, mock_db_session):
    """Test creating a new ICCD record."""
    # Arrange
    record_data = {
        "nct_region": "12",
        "nct_number": "24000001",
        "schema_type": "RA",
        "level": "P",
        "iccd_data": {"test": "data"},
        "site_id": uuid4(),
        "created_by": uuid4()
    }
    
    mock_record = MagicMock(spec=ICCDRecord)
    mock_record.id = uuid4()
    for key, value in record_data.items():
        setattr(mock_record, key, value)
    
    # Act
    result = await iccd_record_repository.create_record(record_data)
    
    # Assert
    assert result is not None
    mock_db_session.add.assert_called_once_with(result)
    mock_db_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_record(iccd_record_repository):
    """Test updating an existing ICCD record."""
    # Arrange
    mock_record = MagicMock(spec=ICCDRecord)
    mock_record.id = uuid4()
    mock_record.level = "P"
    
    update_data = {
        "level": "C",
        "status": "validated"
    }
    
    # Act
    result = await iccd_record_repository.update_record(mock_record, update_data)
    
    # Assert
    assert result == mock_record
    assert mock_record.level == "C"
    assert mock_record.status == "validated"


@pytest.mark.asyncio
async def test_check_nct_exists(iccd_record_repository, mock_db_session):
    """Test checking if an NCT code already exists."""
    # Arrange
    mock_query = MagicMock()
    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none.return_value = None  # No record found
    
    # Mock the select query
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.repositories.iccd_records.select", MagicMock(return_value=mock_query))
        mock_db_session.execute.return_value = mock_exec
        
        # Act
        result = await iccd_record_repository.check_nct_exists("12", "240001", None)
        
        # Assert
        assert result is False
        mock_db_session.execute.assert_called_once()