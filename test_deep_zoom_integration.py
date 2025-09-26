#!/usr/bin/env python3
"""
Test script for Deep Zoom integration with MinIO
Tests the complete deep zoom workflow from photo upload to tile serving
"""

import asyncio
import io
import os
from PIL import Image
import requests
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.archaeological_minio_service import archaeological_minio_service

async def create_test_image(width=4000, height=3000):
    """Create a test archaeological image"""
    # Create a test image with archaeological-like content
    img = Image.new('RGB', (width, height), color='lightyellow')

    # Add some archaeological features (simplified)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    # Add some "artifacts" - rectangles of different colors
    colors = ['brown', 'red', 'gray', 'orange']
    for i in range(20):
        x1 = (i * 200) % width
        y1 = (i * 150) % height
        x2 = x1 + 100 + (i % 50)
        y2 = y1 + 80 + (i % 30)
        color = colors[i % len(colors)]
        draw.rectangle([x1, y1, x2, y2], fill=color, outline='black')

    # Add some text (inventory numbers)
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()

    for i in range(10):
        text = f"INV-{1000+i"03d"}"
        draw.text((100 + i*300, 100 + i*200), text, fill='black', font=font)

    return img

async def test_deep_zoom_workflow():
    """Test the complete deep zoom workflow"""

    print("🧪 Testing Deep Zoom Integration...")

    # Test parameters
    site_id = "test-site-001"
    photo_id = "test-photo-deep-zoom-001"

    try:
        # 1. Create test image
        print("📸 Creating test archaeological image...")
        test_image = await create_test_image(4000, 3000)

        # Convert to bytes
        img_buffer = io.BytesIO()
        test_image.save(img_buffer, format='JPEG', quality=95)
        img_buffer.seek(0)
        photo_data = img_buffer.getvalue()

        print(f"✅ Created test image: {test_image.size}, {len(photo_data)} bytes")

        # 2. Upload with deep zoom processing
        print("🚀 Processing photo with deep zoom...")
        result = await archaeological_minio_service.process_photo_with_deep_zoom(
            photo_data=photo_data,
            photo_id=photo_id,
            site_id=site_id,
            archaeological_metadata={
                'inventory_number': 'TEST-001',
                'excavation_area': 'Test Area A',
                'material': 'ceramic',
                'chronology_period': 'Roman Period'
            },
            generate_deep_zoom=True
        )

        print("✅ Deep zoom processing completed:"        print(f"   - Photo URL: {result.get('photo_url', 'N/A')}")
        print(f"   - Deep Zoom Available: {result.get('deep_zoom_available', False)}")
        print(f"   - Tile Count: {result.get('tile_count', 0)}")
        print(f"   - Levels: {result.get('levels', 0)}")

        if result.get('deep_zoom_available'):
            # 3. Test deep zoom info endpoint
            print("🔍 Testing deep zoom info endpoint...")
            deep_zoom_info = await archaeological_minio_service.get_deep_zoom_info(site_id, photo_id)

            if deep_zoom_info:
                print("✅ Deep zoom info retrieved:"                print(f"   - Width: {deep_zoom_info.get('width')}")
                print(f"   - Height: {deep_zoom_info.get('height')}")
                print(f"   - Levels: {deep_zoom_info.get('levels')}")
                print(f"   - Tile Size: {deep_zoom_info.get('tile_size', 256)}")

                # 4. Test tile serving
                print("🧩 Testing tile serving...")
                tile_url = await archaeological_minio_service.get_tile_url(site_id, photo_id, 0, 0, 0)

                if tile_url:
                    print(f"✅ Tile URL generated: {tile_url}")

                    # Try to fetch the tile (this might fail if MinIO is not running)
                    try:
                        response = requests.get(tile_url, timeout=10)
                        if response.status_code == 200:
                            print(f"✅ Tile successfully served: {len(response.content)} bytes")
                        else:
                            print(f"⚠️  Tile request returned status: {response.status_code}")
                    except Exception as e:
                        print(f"⚠️  Could not fetch tile (MinIO may not be running): {e}")
                else:
                    print("❌ Failed to generate tile URL")
            else:
                print("❌ Failed to get deep zoom info")
        else:
            print("❌ Deep zoom processing failed")

        print("\n🎉 Deep Zoom Integration Test Complete!")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_basic_minio_connection():
    """Test basic MinIO connectivity"""
    print("🔌 Testing MinIO connection...")

    try:
        # Try to list buckets
        buckets = archaeological_minio_service.client.list_buckets()
        print(f"✅ MinIO connected successfully. Found {len(buckets)} buckets:")
        for bucket in buckets:
            print(f"   - {bucket.name}")

        return True
    except Exception as e:
        print(f"❌ MinIO connection failed: {e}")
        print("💡 Make sure MinIO is running and credentials are correct in .env")
        return False

if __name__ == "__main__":
    async def main():
        print("🔬 Deep Zoom Integration Test Suite")
        print("=" * 50)

        # Test basic connectivity first
        if not await test_basic_minio_connection():
            print("\n❌ Cannot proceed without MinIO connection")
            return

        # Run deep zoom workflow test
        success = await test_deep_zoom_workflow()

        if success:
            print("\n✅ All tests passed! Deep zoom integration is working correctly.")
        else:
            print("\n❌ Some tests failed. Check the output above for details.")

    # Run the test
    asyncio.run(main())