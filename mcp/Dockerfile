FROM node:20-slim

WORKDIR /app

COPY mcp/package.json mcp/tsconfig.json ./
RUN npm install

COPY mcp/src ./src
RUN npm run build

EXPOSE 3335

CMD ["node", "dist/index.js"]
