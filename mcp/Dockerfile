FROM node:20-slim

LABEL org.opencontainers.image.title="tgmcp" \
      org.opencontainers.image.description="Telegram-MCP MCP bridge service" \
      org.opencontainers.image.source="https://github.com/plagness/Telegram-MCP.git" \
      ns.module="telegram" \
      ns.component="mcp"

WORKDIR /app

COPY mcp/package.json mcp/tsconfig.json ./
RUN npm install

COPY mcp/src ./src
RUN npm run build

EXPOSE 3335

CMD ["node", "dist/index.js"]
