class SnirhError(Exception):
    """Base exception for the get-snirh package."""


class SnirhNetworkError(SnirhError):
    """Raised when an HTTP request to SNIRH fails."""


class SnirhParsingError(SnirhError):
    """Raised when parsing a SNIRH response fails."""


class SnirhDiscoveryError(SnirhError):
    """Raised when a session-scoped discovery endpoint returns an empty
    response (usually a sign the network session was not established)."""
