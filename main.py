"""Entry point. Run with: python main.py"""

import logging
import os

from nicegui import app, ui

from parking_finder.api import AutobahnClient
from parking_finder.dashboard import Dashboard
from parking_finder.settings import load_settings


def register(client: AutobahnClient) -> None:
    @ui.page("/")
    def index() -> None:
        ui.colors(
            primary="#0c2340",
            secondary="#8a6a00",
            accent="#ffcc00",
            positive="#047857",
            negative="#9f1239",
            warning="#c2410c",
        )
        Dashboard(client).build()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    client = AutobahnClient(
        timeout=settings.timeout,
        verify=settings.ssl_verify,
        base_url=settings.base_url,
    )
    register(client)

    async def _close() -> None:
        await client.aclose()

    app.on_shutdown(_close)
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Smart Autobahn Parking Finder",
        reload=False,
        show=settings.open_browser,
        favicon="🚚",
        on_air=True if settings.on_air else None,
        storage_secret=os.environ.get("STORAGE_SECRET", "local-dev-only"),
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
