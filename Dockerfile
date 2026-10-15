FROM library/python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ARG APP_VERSION=local
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.txt
COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 gunicorn.conf.py ./
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health/live',timeout=2)"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.server:create_app()"]
