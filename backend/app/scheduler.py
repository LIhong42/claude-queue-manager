import asyncio
from .config import settings
from .db import claim_task, claim_scheduled_task, count_running
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

    async def scheduled_worker(self):
        """专门领取调度任务。语义：
        - 只有在调度时间到达 AND 全局 RUNNING 任务数为 0 时，才会开始执行一个调度任务。
        - 当普通 worker 正在运行时,以下分析：
          - 普通 worker 仍可领取其他非定时任务（不受影响）；
          - 此调度 worker 持续等待直到 RUNNING=0。
        - 一次只允许运行一个调度任务（因为要求全局 RUNNING=0）。
        """
        while not self.stop_event.is_set():
            # 全局空闲 → 立即尝试领取已到点的调度任务
            # 全局忙 → 等 1 秒后重试（让普通 worker 有机会完成任务）
            if count_running() > 0:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                continue

            task = claim_scheduled_task()
            if task is None:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                continue

            print(f"[scheduled-worker] claimed {task['id']} (scheduled_at={task.get('scheduled_at')})")
            await run_task(task)
            print(f"[scheduled-worker] completed {task['id']}")

    async def start(self):
        self.stop_event.clear()
        self.tasks = [asyncio.create_task(self.worker(i+1)) for i in range(settings.workers)]
        # Add one dedicated scheduled worker that enforces "0 running" before pickup.
        self.tasks.append(asyncio.create_task(self.scheduled_worker()))

    async def stop(self):
        self.stop_event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

scheduler = Scheduler()