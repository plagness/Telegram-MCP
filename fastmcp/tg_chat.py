"""tg-chat — сообщения, чаты, callbacks."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-chat", ["/v1/messages", "/v1/chats", "/v1/callbacks"])

if __name__ == "__main__":
    mcp.run()
