"""
Test script to verify the OAuth2 login fix
"""
import asyncio
import aiohttp
import json

async def test_oauth2_login():
    """Test OAuth2 login endpoint"""
    url = "http://localhost:8000/auth/token"
    
    # OAuth2 form data
    data = {
        "username": "superuser@admin.com",
        "password": "admin"  # Assuming this is the test password
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, headers=headers) as response:
                print(f"Status: {response.status}")
                print(f"Headers: {dict(response.headers)}")
                
                if response.status == 204:
                    print("✅ OAuth2 login successful!")
                    cookies = session.cookie_jar.filter_cookies(url)
                    if "access_token" in cookies:
                        print(f"Token cookie set: {cookies['access_token'].value[:50]}...")
                else:
                    text = await response.text()
                    print(f"❌ Login failed: {text}")
                    
        except aiohttp.ClientConnectorError:
            print("❌ Could not connect to the server. Make sure the application is running on localhost:8000")
        except Exception as e:
            print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_oauth2_login())