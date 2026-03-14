import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.database.db import SessionLocal
from app.models.user_activity import UserActivity

async def test():
    async with SessionLocal() as db:
        print("Testing log_us_action...")
        act1 = await UserActivity.log_us_action(
            db=db,
            user_id="00000000-0000-0000-0000-000000000000",
            action="create",
            us_id="33333333-3333-3333-3333-333333333333",
            site_id="22222222-2222-2222-2222-222222222222",
            us_code="US-TEST"
        )
        print(f"Created US activity: {act1.activity_type} - {act1.id}")
        
        print("Testing log_usm_action...")
        act2 = await UserActivity.log_usm_action(
            db=db,
            user_id="00000000-0000-0000-0000-000000000000",
            action="update",
            usm_id="44444444-4444-4444-4444-444444444444",
            site_id="22222222-2222-2222-2222-222222222222",
            usm_code="USM-TEST"
        )
        print(f"Created USM activity: {act2.activity_type} - {act2.id}")

        print("Testing log_tma_action...")
        act3 = await UserActivity.log_tma_action(
            db=db,
            user_id="00000000-0000-0000-0000-000000000000",
            action="delete",
            tomba_id="11111111-1111-1111-1111-111111111111",
            site_id="22222222-2222-2222-2222-222222222222",
            nct="12345678"
        )
        print(f"Created TMA activity: {act3.activity_type} - {act3.id}")
        
        await db.rollback() # cleanup
        print("Rollback successful. Models and methods are fully functional.")

if __name__ == "__main__":
    asyncio.run(test())
