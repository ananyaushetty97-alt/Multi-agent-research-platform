import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator

PASSWORD_LETTER_REGEX = re.compile(r"[A-Za-z]")
PASSWORD_DIGIT_REGEX = re.compile(r"\d")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$")

COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890",
    "qwerty123", "admin123", "welcome1", "letmein1", "research123", "abc12345",
    "iloveyou", "monkey123", "dragon123", "sunshine", "princess", "football"
}


class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Name cannot be empty or whitespace.")
        if len(cleaned) > 100:
            raise ValueError("Name must be 100 characters or fewer.")
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
        if v.lower() in COMMON_PASSWORDS:
            raise ValueError("This password is too common and easily guessed. Please choose a stronger password.")
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


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned.isdigit() or len(cleaned) != 6:
            raise ValueError("Verification code must be exactly 6 digits.")
        return cleaned


class ResendOtpRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("Password must be between 8 and 128 characters.")
        if v.lower() in COMMON_PASSWORDS:
            raise ValueError("This password is too common and easily guessed.")
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


class UserStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="'active' or 'suspended'")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("active", "suspended"):
            raise ValueError("Status must be either 'active' or 'suspended'.")
        return val


class UserResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    username: str
    role: str = "user"
    auth_provider: str = "email"  # 'email', 'google', 'both'
    email_verified: bool = False
    status: str = "active"  # 'active', 'suspended'
    google_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


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


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    role: str
    content: str
    search_results: Optional[List[Dict[str, Any]]] = None
    score: Optional[Dict[str, Any]] = None
    intent: Optional[str] = None
    seconds: Optional[float] = None
    cached: bool = False
    created_at: datetime


class ActivityLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    event_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime
