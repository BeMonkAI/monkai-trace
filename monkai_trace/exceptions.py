"""Custom exceptions for MonkAI client"""


class MonkAIError(Exception):
    """Base exception for MonkAI errors"""
    pass


class MonkAIAuthError(MonkAIError):
    """Authentication/authorization error"""
    pass


class MonkAIValidationError(MonkAIError):
    """Data validation error"""
    pass


class MonkAIServerError(MonkAIError):
    """Server-side error"""
    pass


class MonkAINetworkError(MonkAIError):
    """Network/connection error"""
    pass


class MonkAIAPIError(MonkAIError):
    """API request error (after retries exhausted)"""
    pass


class MonkAIAnonymizerNotReady(MonkAIError):
    """Raised when custom anonymization rules are required but unavailable.

    This is raised by the upload pipeline when ``RulesClient.get()`` has never
    succeeded — sending the payload would mean transmitting raw content that
    only the baseline rules touched. We block to avoid leaking PII the tenant
    expects to be redacted by their custom rules.
    """
    pass


class MonkAIRecordDiscardedError(MonkAIAPIError):
    """Raised in strict_dedup mode when the server reports records were deduplicated.

    Attributes:
        dropped_count: number of records the server dropped as duplicates
        inserted_count: number of records the server actually inserted
        total_received: total records sent in the request
    """
    def __init__(
        self,
        message: str,
        *,
        dropped_count: int,
        inserted_count: int,
        total_received: int,
    ):
        super().__init__(message)
        self.dropped_count = dropped_count
        self.inserted_count = inserted_count
        self.total_received = total_received
