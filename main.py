import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import bot
import db
import routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

web_app = FastAPI(title="TORQUM")
web_app.include_router(routes.router)
web_app.mount("/static", StaticFiles(directory="static"), name="static")


async def main():
    await db.init_db()
    cfg = uvicorn.Config(web_app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)), log_level="info")
    server = uvicorn.Server(cfg)
    await asyncio.gather(server.serve(), bot.run_polling())


if __name__ == "__main__":
    asyncio.run(main())
