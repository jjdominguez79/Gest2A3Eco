from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str
    service: str
    version: str
