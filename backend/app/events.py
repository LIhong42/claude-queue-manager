import asyncio

class EventBus:
    def __init__(self):
        self.clients = set()

    async def subscribe(self):
        q = asyncio.Queue()
        self.clients.add(q)
        return q

    def unsubscribe(self, q):
        self.clients.discard(q)

    async def publish(self, event):
        for q in list(self.clients):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

events = EventBus()
