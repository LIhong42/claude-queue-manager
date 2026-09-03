import asyncio
import uvicorn
from .config import settings
from .db import init_db
from .scheduler import scheduler
from .api import app

async def main():
    init_db()
    await scheduler.start()
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info")
    await uvicorn.Server(config).serve()

if __name__ == "__main__":
    asyncio.run(main())
