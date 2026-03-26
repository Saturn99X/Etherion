# Frontend (Next.js) container image for Cloud Run
FROM node:20-alpine AS builder
WORKDIR /app

# Install deps with npm; tolerate stale lock by falling back to npm install
COPY package*.json ./
RUN npm ci || npm install

# Build
COPY . .
RUN npm run build

# Runtime image
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_PUBLIC_ETHERION_ENABLED=1

# Copy built app
COPY --from=builder /app ./

# Cloud Run will set PORT; default to 3000 locally
ENV PORT=3000
EXPOSE 3000

# Start Next.js on the provided PORT
CMD ["sh", "-c", "npm run start -- -p ${PORT}"]
