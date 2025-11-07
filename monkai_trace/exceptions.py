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
