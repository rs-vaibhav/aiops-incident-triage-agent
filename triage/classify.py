"""Deterministic severity scoring.

Severity is kept rule-based on purpose: it drives paging, so it must be explainable
and stable. The LLM is only used for the narrative (root cause wording), never for
deciding who gets woken up.
"""
from __future__ import annotations

from .models import Incident

CRITICAL_SERVICES = {"payments-api", "checkout-api", "postgres", "auth-service"}

# Base impact of each alert type (0-50)
ALERT_WEIGHTS = {
    "ServiceDown": 50,
    "HighErrorRate": 40,
    "SLOErrorBudgetBurn": 50,
    "DBConnectionPoolExhausted": 35,
    "PodCrashLooping": 30,
    "ContainerOOMKilled": 25,
    "HighLatency": 25,
    "UpstreamTimeout": 20,
    "TLSCertificateExpiry": 20,
    "DiskSpaceLow": 20,
    "HighCPUUsage": 10,
    "HighMemoryUsage": 10,
}

HINT_WEIGHTS = {"critical": 20, "error": 10, "warning": 5, "info": 0}


def score(incident: Incident) -> tuple[int, list[str]]:
    reasons: list[str] = []
    top = max(incident.alerts, key=lambda a: ALERT_WEIGHTS.get(a.name, 10))
    s = ALERT_WEIGHTS.get(top.name, 10)
    reasons.append(f"strongest signal {top.name} (+{s})")

    hint = max((HINT_WEIGHTS.get((a.severity_hint or "info").lower(), 0) for a in incident.alerts), default=0)
    if hint:
        s += hint
        reasons.append(f"alert severity label (+{hint})")

    services = {a.service for a in incident.alerts}
    if services & CRITICAL_SERVICES:
        s += 20
        reasons.append(f"business-critical service {sorted(services & CRITICAL_SERVICES)} (+20)")

    if len(services) > 1:
        s += 10
        reasons.append(f"blast radius {len(services)} services (+10)")

    if len(incident.alerts) >= 4:
        s += 5
        reasons.append(f"{len(incident.alerts)} correlated alerts (+5)")
    return s, reasons


def classify(incident: Incident) -> Incident:
    s, reasons = score(incident)
    if s >= 85:
        sev = "P1"
    elif s >= 60:
        sev = "P2"
    elif s >= 35:
        sev = "P3"
    else:
        sev = "P4"
    incident.severity = sev
    incident.severity_reason = f"score={s}: " + "; ".join(reasons)
    return incident
