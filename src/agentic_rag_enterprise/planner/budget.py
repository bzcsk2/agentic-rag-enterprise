"""E-018 AtomicToolBudget (build plan §13.4, contract §6 / §6a).

Thread-safe budget with a single ``try_reserve(n)`` API.  There is **no** separate
``reserve`` + ``consume`` step — reservation *is* the consumption transition.
"""

from __future__ import annotations

import threading


class AtomicToolBudget:
    """Atomic shared Tool-Call budget.

    Thread-safe via ``threading.Lock``.  All accounting goes through this single
    object; steps MUST NOT keep their own counters.
    """

    def __init__(self, total: int) -> None:
        if total < 0:
            raise ValueError(f"total must be >= 0, got {total}")
        self._total = total
        self._used = 0
        self._lock = threading.Lock()

    def try_reserve(self, n: int = 1) -> bool:
        """Atomically attempt to spend ``n`` units.

        Returns:
            True on success (``remaining -= n``, ``used += n``).
            False if insufficient units remain — nothing is changed.
        """
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        with self._lock:
            if self._used + n > self._total:
                return False
            self._used += n
        return True

    def used(self) -> int:
        """Total units reserved so far (thread-safe read)."""
        with self._lock:
            return self._used

    def remaining(self) -> int:
        """Units still available (thread-safe read)."""
        with self._lock:
            return self._total - self._used
