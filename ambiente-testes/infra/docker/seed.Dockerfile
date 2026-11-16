FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY scripts/lib/database/requirements.txt /opt/seed-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /opt/seed-requirements.txt
WORKDIR /workspace
CMD ["python", "/workspace/scripts/lib/database/seed_data.py", "--help"]
