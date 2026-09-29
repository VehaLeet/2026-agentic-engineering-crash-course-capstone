"""Фонові запуски збору (ручні й планові) в межах одного процесу (один воркер uvicorn)."""

import asyncio
from collections.abc import Awaitable, Callable


class RunManager:
    def __init__(self, job: Callable[[int, str], Awaitable[object]]):
        self._job = job
        self._tasks: set[asyncio.Task] = set()

    @property
    def active(self) -> int:
        return len(self._tasks)

    def start(self, run_id: int, trigger: str) -> asyncio.Task:
        task = asyncio.create_task(self._job(run_id, trigger), name=f"collect-run-{run_id}")
        self._tasks.add(task)  # сильне посилання: інакше GC може прибрати задачу посеред збору
        task.add_done_callback(self._tasks.discard)
        return task

    async def wait_all(self) -> None:
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        """Скасувати незавершені запуски. Їхні рядки лишаться з finished_at IS NULL — це видимий слід."""
        for task in self._tasks:
            task.cancel()
        await self.wait_all()
