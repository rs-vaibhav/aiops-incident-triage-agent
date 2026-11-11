"""Render an incident as an ITSM ticket (ServiceNow-style fields)."""
from __future__ import annotations

from .models import Incident

IMPACT_URGENCY = {"P1": (1, 1), "P2": (1, 2), "P3": (2, 2), "P4": (3, 3)}
ASSIGNMENT_GROUPS = {
    "postgres": "DBA-Operations",
    "payments-api": "Payments-SRE",
    "checkout-api": "Commerce-SRE",
    "orders-api": "Commerce-SRE",
    "auth-service": "Identity-Platform",
}


def build_ticket(incident: Incident) -> dict:
    impact, urgency = IMPACT_URGENCY[incident.severity]
    return {
        "number": incident.id,
        "short_description": f"[{incident.severity}] {', '.join(incident.alert_names)} - {incident.service}",
        "cmdb_ci": incident.service,
        "impact": impact,
        "urgency": urgency,
        "priority": incident.severity,
        "assignment_group": ASSIGNMENT_GROUPS.get(incident.service, "GTS-Operations"),
        "category": "Infrastructure" if incident.service in {"postgres", "node", "kubernetes"} else "Application",
        "opened_at": incident.opened_at.isoformat(),
        "description": "\n".join(
            [
                f"Probable root cause: {incident.probable_root_cause}",
                f"Severity rationale: {incident.severity_reason}",
                "",
                "Correlated alerts:",
                *[f"  - {a.starts_at:%H:%M:%S} {a.name} ({a.source}) {a.instance or ''} {a.summary}" for a in incident.alerts],
                "",
                f"Runbook: {incident.runbook} (match score {incident.runbook_score:.2f})",
                "Suggested remediation (requires human approval):",
                *[f"  {i}. {s}" for i, s in enumerate(incident.remediation_steps, 1)],
                *(["Blocked (destructive, manual decision only):", *[f"  - {s}" for s in incident.blocked_steps]] if incident.blocked_steps else []),
            ]
        ),
        "state": "New" if incident.status == "pending_approval" else incident.status.title(),
    }


def to_markdown(incident: Incident) -> str:
    t = build_ticket(incident)
    return f"### {t['number']} {t['short_description']}\n\nAssignment group: **{t['assignment_group']}**\n\n```\n{t['description']}\n```\n"
