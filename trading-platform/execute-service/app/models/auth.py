"""
Pydantic schemas for wallet auth API requests/responses.
NOTE: This file is superseded by auth_schemas.py. Kept for backwards compat.
"""
# Re-export from the canonical location
from app.models.auth_schemas import *  # noqa: F401, F403
