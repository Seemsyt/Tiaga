"""Backward-compat shim (typo'd module name).

Prefer importing from `tiaga.utils.errors`.
"""

from __future__ import annotations

import warnings

from .errors import AgentError, ConfigError

warnings.warn(
    "`tiaga.utils.erors` is deprecated; import from `tiaga.utils.errors` instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["AgentError", "ConfigError"]
