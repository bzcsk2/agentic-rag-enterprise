"""Unit tests for AtomicToolBudget (contract §6 / §6a).

Covers basic ops, multi-unit reservation, and concurrency safety.
"""

from __future__ import annotations

import threading

import pytest

from agentic_rag_enterprise.planner.budget import AtomicToolBudget


def test_basic_reserve() -> None:
    budget = AtomicToolBudget(total=5)
    assert budget.remaining() == 5
    assert budget.used() == 0

    assert budget.try_reserve(1) is True
    assert budget.remaining() == 4
    assert budget.used() == 1

    assert budget.try_reserve(3) is True
    assert budget.remaining() == 1
    assert budget.used() == 4

    # Exhausted: cannot reserve 2 when only 1 remains.
    assert budget.try_reserve(2) is False
    assert budget.remaining() == 1
    assert budget.used() == 4


def test_reserve_exact_total() -> None:
    budget = AtomicToolBudget(total=3)
    assert budget.try_reserve(3) is True
    assert budget.remaining() == 0
    assert budget.used() == 3

    # Cannot reserve any more.
    assert budget.try_reserve(1) is False


def test_reserve_zero() -> None:
    budget = AtomicToolBudget(total=5)
    assert budget.try_reserve(0) is True  # reserving 0 always succeeds
    assert budget.remaining() == 5
    assert budget.used() == 0


def test_negative_total_raises() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        AtomicToolBudget(total=-1)


def test_negative_n_raises() -> None:
    budget = AtomicToolBudget(total=5)
    with pytest.raises(ValueError, match="must be >= 0"):
        budget.try_reserve(-1)


def test_zero_total() -> None:
    budget = AtomicToolBudget(total=0)
    assert budget.remaining() == 0
    assert budget.used() == 0
    assert budget.try_reserve(1) is False
    assert budget.try_reserve(0) is True  # reserving 0 succeeds even on empty budget


def test_concurrent_racing() -> None:
    """Two threads racing for the last remaining unit: exactly one succeeds."""
    budget = AtomicToolBudget(total=1)
    results: list[bool] = []
    lock = threading.Lock()

    def reserve() -> None:
        ok = budget.try_reserve(1)
        with lock:
            results.append(ok)

    t1 = threading.Thread(target=reserve)
    t2 = threading.Thread(target=reserve)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sum(results) == 1  # exactly one success
    assert budget.used() == 1
    assert budget.remaining() == 0


def test_concurrent_multi_unit() -> None:
    """Multiple threads trying to reserve multi-unit chunks: total never overspent."""
    budget = AtomicToolBudget(total=6)
    results: list[bool] = []
    lock = threading.Lock()

    def reserve_4() -> None:
        ok = budget.try_reserve(4)
        with lock:
            results.append(ok)

    def reserve_3() -> None:
        ok = budget.try_reserve(3)
        with lock:
            results.append(ok)

    t1 = threading.Thread(target=reserve_4)
    t2 = threading.Thread(target=reserve_3)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # With total=6, a 4-unit and a 3-unit can't both succeed (7 > 6).
    successes = sum(results)
    assert successes == 1  # exactly one succeeds
    total_used = budget.used()
    assert total_used in (4, 3)
    assert budget.remaining() == 6 - total_used
