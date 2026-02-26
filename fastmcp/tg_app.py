"""tg-app — Web UI, роли, формы, опросы."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-app", ["/v1/web"])

if __name__ == "__main__":
    mcp.run()
