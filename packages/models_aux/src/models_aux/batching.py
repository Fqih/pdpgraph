# SPDX-License-Identifier: Apache-2.0
"""Dynamic batching (05 §4): items from concurrent requests are grouped into one model call of
up to `max_batch` items, waiting at most `max_wait_ms` for more. One worker per model, so model
calls never overlap; each call runs in a thread so the event loop stays responsive."""

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Self


class Batcher[I, O]:
    def __init__(
        self, fn: Callable[[list[I]], list[O]], *, max_batch: int, max_wait_ms: float
    ) -> None:
        self._fn = fn
        self._max_batch = max_batch
        self._max_wait = max_wait_ms / 1000
        self._queue: asyncio.Queue[tuple[I, asyncio.Future[O]]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        self._worker = asyncio.create_task(self._run())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def submit(self, items: Sequence[I]) -> list[O]:
        if self._worker is None:
            raise RuntimeError("batcher is not running")
        loop = asyncio.get_running_loop()
        futures = [loop.create_future() for _ in items]
        for item, future in zip(items, futures, strict=True):
            self._queue.put_nowait((item, future))
        return list(await asyncio.gather(*futures))

    async def _collect(self) -> list[tuple[I, asyncio.Future[O]]]:
        batch = [await self._queue.get()]
        deadline = asyncio.get_running_loop().time() + self._max_wait
        while len(batch) < self._max_batch:
            if not self._queue.empty():
                batch.append(self._queue.get_nowait())
                continue
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._queue.get(), remaining))
            except TimeoutError:
                break
        return batch

    async def _run(self) -> None:
        while True:
            batch = [(i, f) for i, f in await self._collect() if not f.done()]
            if not batch:
                continue
            try:
                outputs = await asyncio.to_thread(self._fn, [item for item, _ in batch])
                if len(outputs) != len(batch):
                    raise RuntimeError(
                        f"model returned {len(outputs)} outputs for {len(batch)} inputs"
                    )
            except Exception as exc:
                for _, future in batch:
                    if not future.done():
                        future.set_exception(exc)
                continue
            for (_, future), output in zip(batch, outputs, strict=True):
                if not future.done():
                    future.set_result(output)
