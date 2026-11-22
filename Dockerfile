FROM node:22-alpine AS ui
WORKDIR /site
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY --from=ui /site/dist web/dist
ENV PORT=8080
CMD ["sh","-c","exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
