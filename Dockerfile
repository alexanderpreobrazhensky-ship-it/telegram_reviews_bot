FROM node:20-alpine

WORKDIR /app
ARG APP_BUILD_COMMIT=unknown
ARG APP_BUILD_BRANCH=unknown
ARG APP_BUILD_TIMESTAMP=unknown

ENV APP_BUILD_COMMIT=$APP_BUILD_COMMIT
ENV APP_BUILD_BRANCH=$APP_BUILD_BRANCH
ENV APP_BUILD_TIMESTAMP=$APP_BUILD_TIMESTAMP

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .
RUN node scripts/verifyReferenceDataset.js --strict

ENV NODE_ENV=production
CMD ["node", "app.js"]
