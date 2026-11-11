"""Core data models used across the triage pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

SEVERITIES = ["P1", "P2", "P3", "P4"]  # P1 = most critical


@dataclass
class Alert:
    """A single alert, normalised from Prometheus Alertmanager or a log line."""

    name: str
    service: str
    status: str = "firing"
    severity_hint: str | None = None          # "critical" / "warning" / "info" label, if present
    instance: str | None = None
    summary: str = ""
    description: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    starts_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "prometheus"                # prometheus | logs
    fingerprint: str = ""

    def text(self) -> str:
        """Human readable representation used for retrieval and prompts."""
        return f"{self.name} on {self.service} ({self.instance or 'n/a'}): {self.summary} {self.description}".strip()


@dataclass
class Incident:
    """A group of correlated alerts that most likely share one root cause."""

    id: str
    service: str
    alerts: list[Alert]
    opened_at: datetime
    severity: str = "P4"
    severity_reason: str = ""
    probable_root_cause: str = ""
    runbook: str | None = None
    runbook_score: float = 0.0
    remediation_steps: list[str] = field(default_factory=list)
    blocked_steps: list[str] = field(default_factory=list)
    status: str = "pending_approval"          # pending_approval | approved | rejected

    @property
    def alert_names(self) -> list[str]:
        return sorted({a.name for a in self.alerts})

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["opened_at"] = self.opened_at.isoformat()
        for a in d["alerts"]:
            a["starts_at"] = a["starts_at"].isoformat()
        return d
