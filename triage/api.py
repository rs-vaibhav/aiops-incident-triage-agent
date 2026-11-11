"""FastAPI service. Point Alertmanager's webhook receiver at POST /alerts.

    receivers:
      - name: triage-agent
        webhook_configs:
          - url: http://triage-agent:8080/alerts
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .agent import TriageAgent
from .ingest import from_alertmanager, from_logs
from .ticket import build_ticket, to_markdown

app = FastAPI(title="AIOps Incident Triage Agent", version="1.0.0")
_agent: TriageAgent | None = None
INCIDENTS: dict[str, object] = {}


def agent() -> TriageAgent:
    global _agent
    if _agent is None:
        _agent = TriageAgent()
    return _agent


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/alerts")
async def receive_alerts(request: Request):
    payload = await request.json()
    incidents = agent().run(from_alertmanager(payload))
    for inc in incidents:
        INCIDENTS[inc.id] = inc
    return {"incidents": [build_ticket(i) for i in incidents]}


@app.post("/logs")
async def receive_logs(request: Request):
    body = (await request.body()).decode()
    incidents = agent().run(from_logs(body.splitlines()))
    for inc in incidents:
        INCIDENTS[inc.id] = inc
    return {"incidents": [build_ticket(i) for i in incidents]}


@app.get("/incidents")
def list_incidents():
    return [build_ticket(i) for i in INCIDENTS.values()]


@app.get("/incidents/{incident_id}", response_class=PlainTextResponse)
def get_incident(incident_id: str):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return to_markdown(inc)


@app.post("/incidents/{incident_id}/{decision}")
def decide(incident_id: str, decision: str):
    """Human-in-the-loop: an engineer approves or rejects the suggested remediation."""
    if decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve or reject")
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    inc.status = "approved" if decision == "approve" else "rejected"
    return build_ticket(inc)
