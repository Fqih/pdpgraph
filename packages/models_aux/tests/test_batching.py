# SPDX-License-Identifier: Apache-2.0
"""Dynamic batching: concurrent requests share one model call (05 §4)."""

import asyncio

import pytest

from models_aux.batching import Batcher


def _recording(calls: list[list[int]]):  # type: ignore[no-untyped-def]
    def fn(items: list[int]) -> list[int]:
        calls.append(list(items))
        return [i * 10 for i in items]

    return fn


async def test_concurrent_submissions_are_merged_in_order() -> None:
    calls: list[list[int]] = []
    batcher = Batcher(_recording(calls), max_batch=16, max_wait_ms=50)
    async with batcher:
        a, b = await asyncio.gather(batcher.submit([1, 2]), batcher.submit([3]))
    assert (a, b) == ([10, 20], [30])
    assert calls == [[1, 2, 3]]


async def test_max_batch_splits_large_requests() -> None:
    calls: list[list[int]] = []
    batcher = Batcher(_recording(calls), max_batch=4, max_wait_ms=1)
    async with batcher:
        out = await batcher.submit(list(range(10)))
    assert out == [i * 10 for i in range(10)]
    assert [len(c) for c in calls] == [4, 4, 2]


async def test_errors_reach_every_caller_and_worker_survives() -> None:
    def boom(items: list[int]) -> list[int]:
        if 0 in items:
            raise RuntimeError("model failed")
        return items

    batcher = Batcher(boom, max_batch=8, max_wait_ms=1)
    async with batcher:
        with pytest.raises(RuntimeError, match="model failed"):
            await batcher.submit([0, 1])
        assert await batcher.submit([5]) == [5]


async def test_wrong_output_length_is_an_error() -> None:
    batcher = Batcher(lambda items: items[:-1], max_batch=8, max_wait_ms=1)
    async with batcher:
        with pytest.raises(RuntimeError, match="returned 1 outputs for 2 inputs"):
            await batcher.submit([1, 2])


async def test_submit_before_start_fails() -> None:
    with pytest.raises(RuntimeError, match="not running"):
        await Batcher(lambda items: items, max_batch=1, max_wait_ms=1).submit([1])
