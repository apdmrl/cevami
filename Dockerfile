FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace/app
COPY requirements-production.lock ./
RUN python -m pip install --no-cache-dir pip==26.3 && python -m pip install --no-cache-dir -r requirements-production.lock \
    && groupadd --gid 10001 cevami && useradd --uid 10001 --gid 10001 --no-create-home cevami
COPY --chown=10001:10001 hadis_web ./hadis_web
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 deploy/healthcheck.py deploy/entrypoint.sh ./deploy/
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["sh","/workspace/app/deploy/entrypoint.sh"]
