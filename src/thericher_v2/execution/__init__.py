"""Execution boundary helpers.

No broker adapter is implemented in the interim foundation.
"""

from .emergency import EmergencyStore

__all__ = ["EmergencyStore"]
