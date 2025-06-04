"""Models for request payloads."""

from pydantic import BaseModel


class SaveProfileRequest(BaseModel):
    username: str
    timestamp: str
    options_base64: str


class LoadProfileRequest(BaseModel):
    username: str
    timestamp: str | None = None
