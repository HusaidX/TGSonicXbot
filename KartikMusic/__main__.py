# All rights reserved.

import asyncio
import importlib
import os
import signal
from contextlib import suppress

from aiohttp import web

from KartikMusic import Kartik, app, config, db, logger, stop, thumb, userbot, yt
from KartikMusic.plugins import all_modules


async def idle():
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()


async def start_web_server():
    port = int(os.environ.get("PORT", 8080))

    async def health_check(request):
        return web.Response(text="OK", status=200)

    web_app = web.Application()
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/health", health_check)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server started on port {port}.")


async def main():
    await start_web_server()
    await db.connect()
    await thumb.start()
    await app.boot()
    await userbot.boot()
    await Kartik.boot()

    for module in all_modules:
        importlib.import_module(f"KartikMusic.plugins.{module}")
    logger.info(f"Loaded {len(all_modules)} modules.")

    if config.COOKIES_URL:
        await yt.save_cookies(config.COOKIES_URL)

    sudoers = await db.get_sudoers()
    app.sudoers.update(sudoers)
    app.bl_users.update(await db.get_blacklisted())
    logger.info(f"Loaded {len(app.sudoers)} sudo users.")

    await idle()
    asyncio.create_task(stop())


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        pass
