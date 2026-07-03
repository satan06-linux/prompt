# ForgePrompt Phase 7 — ServiceResult
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from services.errors import ForgeError


@dataclass
class ServiceResult:
    """
    Uniform return envelope for every ForgePrompt service method.

    Fields:
        success     : True on happy path, False on any error.
        data        : Payload returned by the service on success.
        error       : ForgeError instance on failure (None on success).
        retryable   : Convenience copy of error.retryable (False on success).
        error_code  : Convenience copy of error.error_code (None on success).
        metadata    : Arbitrary dict for structured supplementary context
                      (timing, pagination cursors, warnings, etc.).
        trace_id    : Distributed trace identifier threaded through the call.
        duration_ms : Wall-clock milliseconds the operation took.
    """

    success: bool
    data: Any = None
    error: Optional[ForgeError] = None
    retryable: bool = False
    error_code: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    trace_id: Optional[str] = None
    duration_ms: int = 0

    # ------------------------------------------------------------------
    # Factory class-methods
    # ------------------------------------------------------------------

    @classmethod
    def ok(
        cls,
        data: Any = None,
        trace_id: Optional[str] = None,
        duration_ms: int = 0,
        **metadata,
    ) -> "ServiceResult":
        """
        Build a successful ServiceResult.

        Args:
            data        : The payload to return to the caller.
            trace_id    : Optional distributed trace ID.
            duration_ms : Optional elapsed time in milliseconds.
            **metadata  : Any additional key/value pairs stored in metadata.

        Returns:
            ServiceResult with success=True.
        """
        return cls(
            success=True,
            data=data,
            error=None,
            retryable=False,
            error_code=None,
            metadata=metadata,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

    @classmethod
    def success(
        cls,
        data: Any = None,
        trace_id: Optional[str] = None,
        duration_ms: int = 0,
        **metadata,
    ) -> "ServiceResult":
        """
        Alias for ``ok()``.  Kept for backward compatibility with callers
        that use ``ServiceResult.success(data=...)``.
        """
        return cls.ok(data=data, trace_id=trace_id, duration_ms=duration_ms, **metadata)

    @classmethod
    def fail(
        cls,
        error: Union[ForgeError, None] = None,
        trace_id: Optional[str] = None,
        duration_ms: int = 0,
        # Convenience kwargs — used by callers that pass error_code/message
        # directly instead of constructing a ForgeError first.
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        retryable: bool = False,
        **metadata,
    ) -> "ServiceResult":
        """
        Build a failed ServiceResult.

        Accepts either a pre-built ``ForgeError`` as the first positional
        argument, or individual ``error_code`` / ``message`` / ``retryable``
        keyword arguments for a lightweight inline failure path.

        Args:
            error       : A ForgeError instance (takes precedence if supplied).
            trace_id    : Optional distributed trace ID.
            duration_ms : Optional elapsed time in milliseconds.
            error_code  : Short error identifier (used when ``error`` is None).
            message     : Human-readable error description (used when ``error`` is None).
            retryable   : Whether the caller may safely retry (used when ``error`` is None).
            **metadata  : Any additional key/value pairs stored in metadata.

        Returns:
            ServiceResult with success=False.
        """
        if error is None:
            # Build a minimal ForgeError from the convenience kwargs.
            error = ForgeError(
                message=message or "An error occurred.",
                error_code=error_code or "FORGE_ERROR",
                retryable=retryable,
            )

        merged_meta = {**error.metadata, **metadata}
        return cls(
            success=False,
            data=None,
            error=error,
            retryable=error.retryable,
            error_code=error.error_code,
            metadata=merged_meta,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_error(self) -> bool:
        """True when the result represents a failure."""
        return not self.success

    @property
    def is_success(self) -> bool:
        """True when the result represents a success.  Alias for ``self.success``."""
        return self.success

    @property
    def error_message(self) -> Optional[str]:
        """
        Convenience accessor for the human-readable error message.
        Returns None on success so callers can do ``res.error_message or ''``.
        """
        return self.error.message if self.error else None

    @property
    def value(self) -> Any:
        """Alias for ``self.data`` — used by callers that prefer ``res.value``."""
        return self.data

    def unwrap(self) -> Any:
        """
        Return ``self.data`` on success, or raise ``self.error`` on failure.

        This mirrors the Rust / Result<T,E> unwrap() idiom and is useful
        in contexts where callers want to propagate errors via exceptions.

        Raises:
            ForgeError: the stored error when success is False.
        """
        if not self.success:
            raise self.error
        return self.data

    def unwrap_or(self, default: Any) -> Any:
        """Return self.data on success, or default on failure."""
        return self.data if self.success else default

    def map(self, func) -> "ServiceResult":
        """
        Apply func to self.data and return a new ServiceResult.
        On failure, propagates the error unchanged.
        """
        if not self.success:
            return self
        try:
            return ServiceResult.ok(
                data=func(self.data),
                trace_id=self.trace_id,
                duration_ms=self.duration_ms,
                **self.metadata,
            )
        except ForgeError as exc:
            return ServiceResult.fail(exc, trace_id=self.trace_id)

    def to_dict(self) -> dict:
        """Serialise to a plain dict (e.g. for JSON API responses)."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
            "retryable": self.retryable,
            "error_code": self.error_code,
            "metadata": self.metadata,
            "trace_id": self.trace_id,
            "duration_ms": self.duration_ms,
        }

    def __bool__(self) -> bool:
        """Allow ``if result:`` usage."""
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"ServiceResult(ok, data={self.data!r}, trace_id={self.trace_id!r})"
        return (
            f"ServiceResult(fail, error_code={self.error_code!r}, "
            f"retryable={self.retryable!r}, trace_id={self.trace_id!r})"
        )


__all__ = ["ServiceResult"]
