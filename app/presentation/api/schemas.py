from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.domain.enums import GenerationStatus, InputKind, MediaKind


class AuthRegisterRequest(BaseModel):
    external_user_id: UUID
    callback_url: HttpUrl


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_user_id: UUID
    balance_tokens: int
    callback_url: HttpUrl
    created_at: datetime


class AuthRegisterResponse(UserResponse):
    api_key: str


class BalanceResponse(BaseModel):
    user_id: UUID
    balance_tokens: int
    reserved_tokens: int
    available_tokens: int


class PaymentWebhookRequest(BaseModel):
    external_user_id: UUID
    amount: int = Field(gt=0)


class GenerationCreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    callback_url: HttpUrl | None = None


class ImageToImageRequest(GenerationCreateRequest):
    source_image_url: HttpUrl


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    media_kind: MediaKind
    input_kind: InputKind
    status: GenerationStatus
    prompt: str
    source_image_url: HttpUrl | None = None
    callback_url: HttpUrl | None = None
    provider_name: str | None = None
    provider_task_id: str | None = None
    result_url: HttpUrl | None = None
    result_payload: dict | None = None
    error_message: str | None = None
    reserved_tokens: int
    created_at: datetime
    updated_at: datetime
