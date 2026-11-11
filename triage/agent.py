"""End-to-end triage pipeline: ingest -> correlate -> classify -> retrieve -> reason -> guard -> ticket."""
from __future__ import annotations

import logging
from pathlib import Path

from . import guardrails
from .classify import classify
from .correlate import correlate
from .llm import get_llm
from .models import Alert, Incident
from .rag import RunbookIndex

log = logging.getLogger("triage")
DEFAULT_RUNBOOKS = Path(__file__).resolve().parent.parent / "runbooks"


class TriageAgent:
    def __init__(self, runbook_dir: str | Path = DEFAULT_RUNBOOKS, llm=None, retriever_backend: str = "auto"):
        self.index = RunbookIndex(runbook_dir, backend=retriever_backend)
        self.llm = llm or get_llm()
        log.info("retriever=%s llm=%s", self.index.backend, getattr(self.llm, "name", "?"))

    def triage_incident(self, incident: Incident) -> Incident:
        classify(incident)
        query = " ".join(a.text() for a in incident.alerts)
        hits = self.index.search(query, alert_names=incident.alert_names, k=3)
        if not hits:
            incident.probable_root_cause = "No runbook matched; escalate to on-call engineer."
            return incident
        book, score = hits[0]
        incident.runbook, incident.runbook_score = book.name, score

        result = self.llm.triage(incident, book)
        incident.probable_root_cause = result.get("probable_root_cause", "")
        allowed, blocked, rejected = guardrails.apply(result.get("remediation_steps", []), book.steps)
        if rejected:
            log.warning("%s: dropped %d ungrounded step(s) from LLM output", incident.id, len(rejected))
        if not allowed and not blocked:
            # fall back to runbook steps if the model output was unusable
            allowed, blocked, _ = guardrails.apply(book.steps[:4], book.steps)
        incident.remediation_steps, incident.blocked_steps = allowed, blocked
        return incident

    def run(self, alerts: list[Alert]) -> list[Incident]:
        incidents = correlate(alerts)
        log.info("%d alerts -> %d incidents", len(alerts), len(incidents))
        return [self.triage_incident(i) for i in incidents]
