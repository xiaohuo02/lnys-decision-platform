# -*- coding: utf-8 -*-
"""Generate a JWT token for E2E testing and print user/role info"""
import sys, os
sys.path.insert(0, "/opt/lnys/nyshdsjpt")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("SECRET_KEY", "lnys_prod_secret_key_2024_change_me_32chars")

from backend.middleware.auth import create_access_token

# Generate tokens for different roles
roles_map = {
    "admin_token": ("admin", ["platform_admin"]),
    "super_admin_token": ("acui", ["super_admin"]),
    "biz_viewer_token": ("viewer_test", ["biz_viewer"]),
    "biz_operator_token": ("operator_test", ["biz_operator"]),
    "ops_analyst_token": ("analyst_test", ["ops_analyst"]),
}
for name, (user, roles) in roles_map.items():
    token = create_access_token(user, roles)
    print(f"{name}={token}")

# Also check user_roles table
import asyncio
from sqlalchemy import text
from backend.database import async_engine

async def check_roles():
    async with async_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT u.username, ur.role_name FROM users u "
            "JOIN user_roles ur ON u.user_id = ur.user_id "
            "ORDER BY u.username LIMIT 20"
        ))
        print("\n--- DB Users & Roles ---")
        for row in result:
            print(f"  {row[0]}: {row[1]}")

asyncio.run(check_roles())
