"""
Tests for DashboardService.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_service import DashboardService
from app.models import ArchaeologicalSite


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_site_statistics(test_db: AsyncSession, mock_site: ArchaeologicalSite):
    """Test retrieving site statistics."""
    # Act
    stats = await DashboardService.get_statistics(db=test_db, site_id=mock_site.id)
    
    # Assert
    assert stats is not None
    assert "photos_count" in stats
    assert "documents_count" in stats
    assert "us_usm_count" in stats
    assert "giornali_totali" in stats
    assert "giornali_validati" in stats
    assert "users_count" in stats
    assert "storage_mb" in stats
    assert "recent_photos" in stats
    assert "last_updated" in stats
    
    # Values should be non-negative integers or floats
    assert stats["photos_count"] >= 0
    assert stats["documents_count"] >= 0
    assert stats["storage_mb"] >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_recent_activities(test_db: AsyncSession, mock_site: ArchaeologicalSite):
    """Test retrieving recent activities."""
    # Act
    activities = await DashboardService.get_recent_activities(
        db=test_db,
        site_id=mock_site.id,
        limit=10
    )
    
    # Assert
    assert activities is not None
    assert isinstance(activities, list)
    # Empty list is valid for new site


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_dashboard_data(test_db: AsyncSession, mock_site: ArchaeologicalSite):
    """Test retrieving complete dashboard data."""
    # Act
    dashboard_data = await DashboardService.get_dashboard_data(
        db=test_db,
        site_id=mock_site.id
    )
    
    # Assert
    assert dashboard_data is not None
    assert "stats" in dashboard_data
    assert "recent_activities" in dashboard_data
    assert "recent_photos" in dashboard_data
    assert "team_members" in dashboard_data
    
    # Verify nested data structure
    assert isinstance(dashboard_data["stats"], dict)
    assert isinstance(dashboard_data["recent_activities"], list)
    assert isinstance(dashboard_data["recent_photos"], list)
    assert isinstance(dashboard_data["team_members"], list)
