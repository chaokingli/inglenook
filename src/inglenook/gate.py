from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from inglenook.clock import Clock, SystemClock
from inglenook.occupancy import BusyChecker, Occupancy
from inglenook.policy import plan_ensure
from inglenook.types import (
    Backend,
    DecisionKind,
    EnsureResult,
    Policy,
    VramSnapshot,
)


class VramReader(Protocol):
    def read(self) -> VramSnapshot: ...


class Unloader(Protocol):
    def unload(self, backend: Backend) -> None: ...


class Gate:
    def __init__(
        self,
        registry: Mapping[str, Backend],
        policy: Policy,
        reader: VramReader,
        unloader: Unloader,
        occupancy: Occupancy,
        busy_checker: BusyChecker,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._reader = reader
        self._unloader = unloader
        self._occupancy = occupancy
        self._busy_checker = busy_checker
        self._clock = clock or SystemClock()

    def ensure_free(self, backend_name: str) -> EnsureResult:
        start = self._clock.monotonic_ms()
        deadline = start + self._policy.unload_timeout_s * 1000
        unloaded: list[str] = []
        warning = ""

        while True:
            snap = self._reader.read()
            loaded = self._occupancy.loaded()
            busy = frozenset(
                name
                for name in loaded
                if name in self._registry
                and self._busy_checker.is_busy(self._registry[name])
            )
            plan = plan_ensure(
                backend_name,
                self._registry,
                snap,
                loaded,
                busy,
                self._policy,
            )
            if plan.warning:
                warning = plan.warning
            now = self._clock.monotonic_ms()
            waited = max(now - start, 0)

            if plan.kind is DecisionKind.ADMIT:
                return EnsureResult(
                    admitted=True,
                    status="admitted",
                    unloaded=tuple(unloaded),
                    waited_ms=waited,
                    used_mb=snap.used_mb,
                    free_mb=snap.free_mb,
                    reason="",
                    warning=warning,
                )

            timed_out = now >= deadline
            if plan.kind is DecisionKind.QUEUE:
                if timed_out:
                    return self._reject(
                        snap,
                        unloaded,
                        waited,
                        f"{plan.reason}_timeout",
                        warning,
                    )
                self._clock.sleep_ms(plan.retry_ms or self._policy.poll_interval_ms)
                continue

            if plan.kind is DecisionKind.UNLOAD:
                if timed_out:
                    return self._reject(
                        snap, unloaded, waited, "unload_timeout", warning
                    )
                for name in plan.unload:
                    backend = self._registry.get(name)
                    if backend is None:
                        continue
                    self._unloader.unload(backend)
                    if name not in unloaded:
                        unloaded.append(name)
                self._clock.sleep_ms(self._policy.poll_interval_ms)
                continue

            if plan.reason == "insufficient_vram":
                if timed_out:
                    return self._reject(
                        snap, unloaded, waited, "unload_timeout", warning
                    )
                self._clock.sleep_ms(self._policy.poll_interval_ms)
                continue

            return self._reject(snap, unloaded, waited, plan.reason, warning)

    def _reject(
        self,
        snap: VramSnapshot,
        unloaded: list[str],
        waited: int,
        reason: str,
        warning: str,
    ) -> EnsureResult:
        return EnsureResult(
            admitted=False,
            status="rejected",
            unloaded=tuple(unloaded),
            waited_ms=waited,
            used_mb=snap.used_mb,
            free_mb=snap.free_mb,
            reason=reason,
            warning=warning,
        )
