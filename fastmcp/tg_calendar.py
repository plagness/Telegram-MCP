"""tg-calendar — события, триггеры, мониторы, бюджет."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-calendar", ["/v1/calendar"])

if __name__ == "__main__":
    mcp.run()
