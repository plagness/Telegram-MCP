"""tg-polls — опросы, реакции, обновления (polling/ack/history)."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-polls", ["/v1/polls", "/v1/reactions", "/v1/updates"])

if __name__ == "__main__":
    mcp.run()
