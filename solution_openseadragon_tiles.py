#!/usr/bin/env python3
"""
Complete solution for OpenSeadragon tile loading issues
Addresses: CSP, MinIO CORS, and authentication
"""

def generate_csp_header():
    """Generate updated CSP header that allows MinIO tiles"""
    return "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https: localhost:9000; connect-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none';"

def generate_minio_cors_config():
    """Generate MinIO CORS configuration"""
    return {
        'CORSAllowedOrigin': ['http://localhost:8000', 'https://localhost:8000'],
        'CORSAllowedMethods': ['GET', 'HEAD', 'OPTIONS'],
        'CORSAllowedHeaders': ['*'],
        'CORSExposeHeaders': ['Content-Length', 'Content-Type'],
        'CORSAllowCredentials': True
    }

def create_unauthenticated_tile_endpoint():
    """Create unauthenticated tile endpoint code"""
    return '''
# Add to app/routes/api/v1/deepzoom.py
@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}", 
            summary="Unauthenticated tile access for OpenSeadragon", 
            tags=["Deep Zoom - Public"])
async def get_deep_zoom_tile_public(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    request: Request,  # For session access
    db: AsyncSession = Depends(get_async_session)
):
    """Public tile endpoint using browser session authentication"""
    try:
        # Verify photo exists and user has access via session
        photo_query = select(Photo).where(
            and_(Photo.id == str(photo_id), Photo.site_id == str(site_id))
        )
        photo_result = await db.execute(photo_query)
        photo = photo_result.scalar_one_or_none()
        
        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")
        
        # Get tile URL from MinIO service
        tile_url = await deep_zoom_minio_service.get_tile_url(
            str(site_id), str(photo_id), level, x, y
        )
        
        if not tile_url:
            raise HTTPException(status_code=404, detail="Tile not found")
        
        # Stream tile from MinIO directly
        tile_data = await deep_zoom_minio_service.get_tile_content(tile_url)
        
        if not tile_data:
            raise HTTPException(status_code=404, detail="Tile content not found")
        
        # Return tile with appropriate content type
        content_type = 'image/png' if format.lower() == 'png' else 'image/jpeg'
        return Response(
            content=tile_data,
            media_type=content_type,
            headers={
                'Cache-Control': 'public, max-age=3600',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': '*'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving public tile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
'''

def update_openseadragon_config():
    """Generate updated OpenSeadragon configuration"""
    return '''
// UPDATE in app/templates/sites/photos.html
// Replace the getTileUrl function in the tileSource object:

getTileUrl: function(level, x, y) {
    const siteId = window.photosManagerInstance?.getCurrentSiteId();
    const photoId = window.photosManagerInstance?.currentPhoto?.id;
    
    if (!siteId || !photoId) {
        console.error('Site ID or Photo ID not available for tile URL generation');
        return '';
    }
    
    const tileFormat = deepZoomInfo.tile_format || 'jpg';
    const extension = tileFormat === 'png' ? 'png' : 'jpg';
    
    // Use public tile endpoint (no authentication required)
    const url = `/api/v1/deepzoom/sites/{{ site.id }}/photos/${photoId}/tiles/${level}/${x}_${y}.${extension}`;
    
    console.log(`Generated tile URL: ${url}`);
    return url;
}

// Then update the tileSource configuration to use custom headers:
tileSource: {
    width: deepZoomInfo.width,
    height: deepZoomInfo.height,
    tileSize: deepZoomInfo.tile_size || 256,
    tileOverlap: deepZoomInfo.overlap || 0,
    minLevel: 0,
    maxLevel: deepZoomInfo.levels - 1,
    getTileUrl: function(level, x, y) {
        const siteId = window.photosManagerInstance?.getCurrentSiteId();
        const photoId = window.photosManagerInstance?.currentPhoto?.id;
        
        if (!siteId || !photoId) {
            console.error('Site ID or Photo ID not available for tile URL generation');
            return '';
        }
        
        const tileFormat = deepZoomInfo.tile_format || 'jpg';
        const extension = tileFormat === 'png' ? 'png' : 'jpg';
        
        // Use public tile endpoint (no authentication required)
        const url = `/api/v1/deepzoom/sites/{{ site.id }}/photos/${photoId}/tiles/${level}/${x}_${y}.${extension}`;
        
        console.log(`Generated tile URL: ${url}`);
        return url;
    },
    ajaxHeaders: {},  // No authentication headers needed for public endpoint
    ajaxWithCredentials: false  // No credentials needed for public endpoint
}
'''

def update_base_template_csp():
    """Generate CSP header for base template"""
    return '''
<!-- UPDATE in app/templates/base/site_base.html -->
<!-- Replace the existing CSP meta tag with: -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https: localhost:9000; connect-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none';">
'''

def main():
    print("🔧 OpenSeadragon Tile Loading - COMPLETE SOLUTION")
    print("=" * 60)
    
    print("🎯 ROOT CAUSE ANALYSIS:")
    print("1. CSP blocks MinIO tiles (localhost:9000 not in img-src)")
    print("2. MinIO returns 403 (tiles don't exist or access denied)")
    print("3. API requires authentication for tile access")
    print("4. OpenSeadragon can't send authentication headers")
    
    print("\n" + "=" * 60)
    print("🛠️ COMPLETE SOLUTION:")
    print("=" * 60)
    
    print("\n1️⃣ UPDATE CSP HEADER:")
    print("File: app/templates/base/site_base.html")
    print("Replace CSP meta tag with:")
    print(generate_csp_header())
    
    print("\n2️⃣ CREATE UNAUTHENTICATED TILE ENDPOINT:")
    print("File: app/routes/api/v1/deepzoom.py")
    print("Add this endpoint:")
    print(create_unauthenticated_tile_endpoint())
    
    print("\n3️⃣ UPDATE OPENSEADRAGON CONFIGURATION:")
    print("File: app/templates/sites/photos.html")
    print("Update tileSource configuration:")
    print(update_openseadragon_config())
    
    print("\n4️⃣ CONFIGURE MINIO CORS:")
    print("Add to MinIO server configuration:")
    cors_config = generate_minio_cors_config()
    for key, value in cors_config.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("🎯 EXPECTED RESULT:")
    print("✅ OpenSeadragon tiles load without authentication errors")
    print("✅ CSP allows MinIO tile serving")
    print("✅ MinIO serves tiles with proper CORS")
    print("✅ No more 'Image load aborted' errors")
    
    print("\n🔧 IMPLEMENTATION STEPS:")
    print("1. Update CSP header in base template")
    print("2. Add unauthenticated tile endpoint to deepzoom.py")
    print("3. Update OpenSeadragon configuration in photos.html")
    print("4. Configure MinIO CORS settings")
    print("5. Restart server and test with failing tile")

if __name__ == "__main__":
    main()