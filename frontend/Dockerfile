# Build Stage 1

FROM node:22-alpine3.22 AS build
WORKDIR /app

RUN corepack enable

# Copy package.json and your lockfile, here we add pnpm-lock.yaml for illustration
COPY package.json yarn.lock ./

# Install dependencies
RUN yarn install

# Copy the entire project
COPY . ./

# Build the project
RUN yarn run build

# Build Stage 2

FROM node:22-alpine3.22
WORKDIR /app

# Only `.output` folder is needed from the build stage
COPY --from=build /app/.output/ ./

# Change the port and host
ENV PORT=3000
ENV HOST=0.0.0.0

EXPOSE 3000

CMD ["node", "/app/server/index.mjs"]
