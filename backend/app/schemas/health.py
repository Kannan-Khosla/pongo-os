from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessCheck(BaseModel):
    name: str
    ready: bool
    message: str
    count: int | None = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    environment: str
    checks: list[ReadinessCheck]
