from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic_ms(self) -> int: ...

    def sleep_ms(self, ms: int) -> None: ...


class SystemClock:
    def monotonic_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def sleep_ms(self, ms: int) -> None:
        time.sleep(max(ms, 0) / 1000)
