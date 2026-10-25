FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY delipick_server/requirements-docker.lock.txt ./requirements-docker.lock.txt
RUN pip install --no-cache-dir -r requirements-docker.lock.txt
COPY delipick_server ./delipick_server
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "delipick_server.deployment.app:app", "--host", "0.0.0.0", "--port", "8000"]
