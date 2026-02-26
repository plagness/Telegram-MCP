"""tg-commerce — боты, Stars платежи, подарки, предсказания."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-commerce", ["/v1/bots", "/v1/bot", "/v1/stars", "/v1/gifts", "/v1/predictions"])

if __name__ == "__main__":
    mcp.run()
