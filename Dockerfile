FROM python:3.12-slim
ARG APP_VERSION=local
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
WORKDIR /srv
COPY --chown=10001:10001 app/ ./app/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health/live',timeout=2)"]
CMD ["python", "-m", "app.server"]
