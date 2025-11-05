class MoreError(Exception):
    """Base SDK error."""

class TransportError(MoreError):
    """HTTP/IO transport issues."""

class SoapFaultError(MoreError):
    """SOAP Fault returned by server."""
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

class AuthError(MoreError):
    """Authentication or token issues."""

class ValidationError(MoreError):
    """Local validation failures."""

class ServerError(MoreError):
    """Non-2xx or unexpected server response."""
