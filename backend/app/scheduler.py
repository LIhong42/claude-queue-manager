import asyncio
from .config import settings
from .db import claim_task
from .runner import run_task

class Scheduler:
    def __init__(self):
        self.tasks = []
        self.stop_event = asyncio.Event()

    async def worker(self, worker_id):
        while not self.stop_event.is_set():
            task = claim_task()
            if task is None:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                continue
            print(f"[worker-{worker_id}] claimed {task['id']}")
            await run_task(task)
            print(f"[worker-{worker_id}] completed {task['id']}")

    async def start(self):
        self.stop_event.clear()
        self.tasks = [asyncio.create_task(self.worker(i+1)) for i in range(settings.workers)]

    async def stop(self):
        self.stop_event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

scheduler = Scheduler()
