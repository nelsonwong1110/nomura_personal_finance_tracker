"""User-facing error types.

Every error that should be shown to the user as a clean message (rather than a
traceback) derives from PftError. The CLI catches PftError and prints it.
"""

from __future__ import annotations


class PftError(Exception):
    """Base class for all user-facing errors."""


class ConfigError(PftError):
    """Invalid or unusable configuration."""


class ValidationError(PftError):
    """A domain value (merchant, category, kind) failed validation."""


class AmountError(PftError):
    """Invalid monetary amount."""


class DateError(PftError):
    """Invalid date."""


class UnknownCategoryError(PftError):
    """A category that does not exist was referenced."""


class ExpressionError(PftError):
    """Invalid rule expression (syntax, unsafe constructs, or evaluation failure)."""


class CsvImportError(PftError):
    """A CSV file could not be imported."""


class NotFoundError(PftError):
    """A referenced record does not exist."""
