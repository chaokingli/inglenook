"""Exception hierarchy for the VRAM gate."""


class InglenookError(Exception):
    """Base error for the gate."""


class ConfigError(InglenookError):
    """Raised when a config file is missing or invalid."""


class VramError(InglenookError):
    """Raised when VRAM cannot be read."""
