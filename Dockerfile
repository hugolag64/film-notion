FROM node:22-alpine AS frontend-build

WORKDIR /app/proto-ui
COPY proto-ui/package.json proto-ui/package-lock.json ./
RUN npm ci
COPY proto-ui/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/backstage.db \
    PORT=8090

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY Logo.png ./
COPY backend/ ./backend/
COPY --from=frontend-build /app/proto-ui/dist ./proto-ui/dist

RUN mkdir -p /data
EXPOSE 8090
CMD ["python", "main.py"]
