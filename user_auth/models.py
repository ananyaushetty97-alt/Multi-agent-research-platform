import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


PASSWORD_LETTER_REGEX = re.compile(r"[A-Za-z]")
PASSWORD_DIGIT_REGEX = re.compile(r"\d")
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$")


class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Name cannot be empty or whitespace.")
        if len(cleaned) > 80:
            raise ValueError("Name must be 80 characters or fewer.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError("Invalid email format.")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("Password must be between 8 and 128 characters.")
        if not PASSWORD_LETTER_REGEX.search(v):
            raise ValueError("Password must contain at least one letter.")
        if not PASSWORD_DIGIT_REGEX.search(v):
            raise ValueError("Password must contain at least one digit.")
        return v

    @model_validator(mode="after")
    def validate_password_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., min_length=10, description="Google Identity Services ID token")


class UserResponse(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    username: str
    role: str = "user"
    email_verified: bool = False


class AuthConfigResponse(BaseModel):
    google_client_id: Optional[str] = None


class UserSessionRecord(BaseModel):
    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
