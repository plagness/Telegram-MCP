"""tg-media — фото, видео, аудио, документы, стикеры."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-media", ["/v1/media"])

if __name__ == "__main__":
    mcp.run()
