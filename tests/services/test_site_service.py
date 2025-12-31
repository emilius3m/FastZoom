"""
Tests for SiteService.
"""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.site_service import SiteService
from app.models import User, ArchaeologicalSite


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_site_by_id(test_db: AsyncSession, mock_site: ArchaeologicalSite):
    """Test retrieving site by ID."""
    # Arrange
    site_service = SiteService()
    
    # Act
    site = await site_service.get_site_by_id(db=test_db, site_id=mock_site.id)
    
    # Assert
    assert site is not None
    assert site.id == mock_site.id
    assert site.name == mock_site.name
    assert site.location == mock_site.location


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_site_by_id_not_found(test_db: AsyncSession):
    """Test retrieving non-existent site returns None."""
    # Arrange
    site_service = SiteService()
    non_existent_id = str(uuid4())
    
    # Act
    site = await site_service.get_site_by_id(db=test_db, site_id=non_existent_id)
    
    # Assert
    assert site is None


@pytest.mark.unit
@pytest.mark.asyncio  
async def test_list_user_sites(
    test_db: AsyncSession,
    mock_user_with_site_access
):
    """Test listing user's accessible sites."""
    # Arrange
    site_service = SiteService()
    user, site, permission = mock_user_with_site_access
    
    # Act
    sites = await site_service.get_user_sites(db=test_db, user_id=str(user.id))
    
    # Assert
    assert len(sites) >= 1
    # Check if our mock site is in the list
    site_ids = [s.id for s in sites]
    assert str(site.id) in site_ids
