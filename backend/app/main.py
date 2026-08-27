import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bulk.runner import poll_forever
from app.db import run_migrations
from app.routers import auth, bulk, health, labels, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    stop_event = asyncio.Event()
    poller_task = asyncio.create_task(poll_forever(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await poller_task


app = FastAPI(title="Shipment Label Printing Portal", lifespan=lifespan)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(labels.router, prefix="/api")
app.include_router(bulk.router, prefix="/api")
