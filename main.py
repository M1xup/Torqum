import asyncio
import logging
import os
import shutil

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
    # разовая миграция: переносим старую базу из корня в data/, если она там уже есть
    if os.path.exists("torqum.db") and not os.path.exists(config.DB_PATH):
        shutil.copy2("torqum.db", config.DB_PATH)
        log_msg = f"База перенесена: torqum.db -> {config.DB_PATH}"
        logging.getLogger("torqum").info(log_msg)
    await db.init_db()
    cfg = uvicorn.Config(web_app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)), log_level="info")
    server = uvicorn.Server(cfg)
    await asyncio.gather(server.serve(), bot.run_polling())


if __name__ == "__main__":
    asyncio.run(main())
