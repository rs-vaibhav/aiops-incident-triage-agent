FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY triage ./triage
COPY runbooks ./runbooks
RUN useradd -r -u 10001 app
USER 10001
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["uvicorn", "triage.api:app", "--host", "0.0.0.0", "--port", "8080"]
