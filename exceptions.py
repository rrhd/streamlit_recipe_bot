class RateLimitHeaderNotFoundError(Exception):
    """Raised when the Retry-After header is missing from the rate limit response."""

    pass
