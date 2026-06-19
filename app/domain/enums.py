from enum import StrEnum


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class InputKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class GenerationStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TransactionKind(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"
    REFUND = "refund"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
