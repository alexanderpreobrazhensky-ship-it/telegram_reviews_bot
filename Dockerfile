FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .
RUN test -r /app/data/reference/client_vehicle_bridge/lira_normalized_database.sqlite

ENV NODE_ENV=production
CMD ["node", "app.js"]
