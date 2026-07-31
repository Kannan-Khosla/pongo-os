from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=200)
    registration_access_code: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class AuthUserRead(BaseModel):
    id: int
    email: EmailStr
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    authenticated: bool
    auth_required: bool = True
    user: AuthUserRead | None = None
