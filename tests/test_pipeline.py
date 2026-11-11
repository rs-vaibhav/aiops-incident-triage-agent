import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from triage import guardrails
from triage.agent import TriageAgent
from triage.classify import classify
from triage.correlate import correlate
from triage.ingest import from_alertmanager, from_logs
from triage.llm import OfflineLLM
from triage.models import Alert
from triage.rag import RunbookIndex

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def make(name, service, minutes=0, sev="warning", fp=None):
    return Alert(name=name, service=service, severity_hint=sev,
                 starts_at=datetime(2026, 10, 12, 10, tzinfo=UTC) + timedelta(minutes=minutes),
                 fingerprint=fp or f"{name}-{service}-{minutes}")


def test_parse_alertmanager_skips_nothing_and_reads_labels():
    alerts = from_alertmanager(json.loads((DATA / "sample_alertmanager.json").read_text()))
    assert len(alerts) == 5
    assert alerts[0].service == "postgres" and alerts[0].severity_hint == "critical"
    assert alerts[0].labels["cluster"] == "aks-prod-centralindia"   # commonLabels merged


def test_log_signatures():
    alerts = from_logs((DATA / "sample_app.log").read_text().splitlines())
    names = [a.name for a in alerts]
    assert "DBConnectionPoolExhausted" in names
    assert "ContainerOOMKilled" in names and "PodCrashLooping" in names
    assert "TLSCertificateExpiry" in names
    assert all(a.source == "logs" for a in alerts)


def test_correlation_dedups_and_merges_dependencies():
    alerts = [
        make("DBConnectionPoolExhausted", "postgres", 0, "critical"),
        make("HighLatency", "payments-api", 2),
        make("HighLatency", "payments-api", 2),                       # duplicate fingerprint
        make("DiskSpaceLow", "logging-node", 30),
    ]
    alerts[2].fingerprint = alerts[1].fingerprint
    incidents = correlate(alerts)
    assert len(incidents) == 2
    db = next(i for i in incidents if i.service == "postgres")
    assert {a.service for a in db.alerts} == {"postgres", "payments-api"}


def test_resolved_alerts_ignored():
    a = make("HighCPUUsage", "x")
    a.status = "resolved"
    assert correlate([a]) == []


def test_severity_levels():
    p1 = classify(correlate([make("ServiceDown", "auth-service", sev="critical")])[0])
    p4 = classify(correlate([make("HighCPUUsage", "reporting-batch")])[0])
    assert p1.severity == "P1" and p4.severity == "P4"
    assert "score=" in p1.severity_reason


def test_retrieval_finds_right_runbook():
    idx = RunbookIndex(ROOT / "runbooks", backend="tfidf")
    top, _ = idx.search("connection pool exhausted on postgres", alert_names=["DBConnectionPoolExhausted"])[0]
    assert top.name == "db-connection-pool"
    top, _ = idx.search("x509 certificate has expired")[0]
    assert top.name == "tls-cert-expiry"


def test_guardrails_block_destructive_and_ungrounded():
    rb = ["Prune unused images", "rm -rf /var/log/* on the node to free space immediately"]
    allowed, blocked, rejected = guardrails.apply(rb + ["sudo reboot the cluster"], rb)
    assert allowed == ["Prune unused images"]
    assert blocked == ["rm -rf /var/log/* on the node to free space immediately"]
    assert rejected == ["sudo reboot the cluster"]


class HallucinatingLLM:
    name = "fake"

    def triage(self, incident, runbook):
        return {"probable_root_cause": "made up", "remediation_steps": ["kubectl delete node everything"]}


def test_agent_falls_back_to_runbook_when_llm_invents_steps():
    agent = TriageAgent(llm=HallucinatingLLM(), retriever_backend="tfidf")
    [inc] = agent.run([make("PodCrashLooping", "orders-api")])
    assert inc.runbook == "pod-crashloop"
    assert inc.remediation_steps and all("delete node" not in s for s in inc.remediation_steps)


def test_end_to_end_offline_and_api():
    agent = TriageAgent(llm=OfflineLLM(), retriever_backend="tfidf")
    incidents = agent.run(from_alertmanager(json.loads((DATA / "sample_alertmanager.json").read_text())))
    assert incidents[0].severity == "P1" and incidents[0].runbook == "db-connection-pool"

    import triage.api as api
    api._agent = agent
    client = TestClient(api.app)
    r = client.post("/alerts", json=json.loads((DATA / "sample_alertmanager.json").read_text()))
    assert r.status_code == 200
    num = r.json()["incidents"][0]["number"]
    assert client.post(f"/incidents/{num}/approve").json()["state"] == "Approved"
    assert client.get("/healthz").json() == {"status": "ok"}
