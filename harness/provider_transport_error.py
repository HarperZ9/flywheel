"""Shared typed errors for provider transport parsing boundaries."""


class MalformedProviderOutput(RuntimeError):
    """A provider transport returned malformed or unbounded output."""
