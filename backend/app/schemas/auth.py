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
    access_level: str
    data_scope: str
    permissions: list[str]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user) -> "AuthUserRead":
        is_demo = user.access_level == "demo"
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            access_level=user.access_level,
            data_scope="mock" if is_demo else "production",
            permissions=["read"] if is_demo else ["read", "write"],
        )


class AuthResponse(BaseModel):
    authenticated: bool
    auth_required: bool = True
    user: AuthUserRead | None = None
