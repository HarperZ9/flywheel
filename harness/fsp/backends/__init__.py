"""Hardware backends: a software secure element and a Windows TPM backend."""

from .software import SoftwareSecureElement

__all__ = ["SoftwareSecureElement"]
