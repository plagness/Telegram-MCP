"""tg-utils — баланс, шаблоны, статистика, форумы, вебхуки, чеклисты."""

import logging
from common import create_openapi_mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

mcp = create_openapi_mcp("tg-utils", [
    "/v1/balance",
    "/v1/templates",
    "/v1/commands",
    "/v1/stats",
    "/v1/webhook",
    "/v1/forums",
    "/v1/stories",
    "/v1/checklists",
    "/v1/suggested-posts",
    "/v1/users",
])

if __name__ == "__main__":
    mcp.run()
