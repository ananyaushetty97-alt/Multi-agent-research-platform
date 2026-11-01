"""
Authentication and user authorization schemas.
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, examples=["admin", "user"])
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: UserRole
    username: str


class UserRecord(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: UserRole
    is_active: bool = True
    created_at: datetime


class InitialAdminProvisionRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12, max_length=128)
    email: Optional[str] = None
    provisioning_token: str = Field(..., description="Server-side one-time provisioning secret")
