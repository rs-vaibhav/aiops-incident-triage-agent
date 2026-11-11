"""Turn raw signals (Alertmanager webhooks and application logs) into Alert objects."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from .models import Alert


def _parse_time(value: str | None) -> datetime:
    if not value or value.startswith("0001-"):
        return datetime.now(UTC)
    value = value.replace("Z", "+00:00")
    # Alertmanager can send nanosecond precision; trim to microseconds for fromisoformat
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    return datetime.fromisoformat(value)


def _fingerprint(labels: dict[str, str]) -> str:
    raw = json.dumps(labels, sort_keys=True).encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def from_alertmanager(payload: dict[str, Any]) -> list[Alert]:
    """Parse an Alertmanager webhook payload (version 4).

    Reference: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
    """
    alerts: list[Alert] = []
    common = payload.get("commonLabels", {})
    for raw in payload.get("alerts", []):
        labels = {**common, **raw.get("labels", {})}
        ann = raw.get("annotations", {})
        alerts.append(
            Alert(
                name=labels.get("alertname", "UnknownAlert"),
                service=labels.get("service") or labels.get("job") or labels.get("app") or "unknown",
                status=raw.get("status", payload.get("status", "firing")),
                severity_hint=labels.get("severity"),
                instance=labels.get("instance") or labels.get("pod"),
                summary=ann.get("summary", ""),
                description=ann.get("description", ""),
                labels=labels,
                starts_at=_parse_time(raw.get("startsAt")),
                source="prometheus",
                fingerprint=raw.get("fingerprint") or _fingerprint(labels),
            )
        )
    return alerts


# Example log line:
# 2026-10-12T10:01:22Z ERROR payments-api pod=payments-7d9f "connection pool exhausted (max=20)"
LOG_RE = re.compile(
    r"^(?P<ts>\S+)\s+(?P<level>ERROR|CRITICAL|FATAL|WARN(?:ING)?)\s+(?P<service>[\w.-]+)"
    r"(?:\s+pod=(?P<pod>[\w.-]+))?\s+\"?(?P<msg>.*?)\"?$"
)

# Known error signatures -> synthetic alert names. Keeps log-derived alerts comparable to metric alerts.
LOG_SIGNATURES = [
    (re.compile(r"connection pool exhausted|too many connections|remaining connection slots", re.I), "DBConnectionPoolExhausted"),
    (re.compile(r"no space left on device|disk full", re.I), "DiskSpaceLow"),
    (re.compile(r"OOMKilled|out of memory", re.I), "ContainerOOMKilled"),
    (re.compile(r"back-off restarting|CrashLoopBackOff", re.I), "PodCrashLooping"),
    (re.compile(r"certificate (has )?expired|x509", re.I), "TLSCertificateExpiry"),
    (re.compile(r"timeout|timed out|deadline exceeded", re.I), "UpstreamTimeout"),
]


def from_logs(lines: Iterable[str]) -> list[Alert]:
    """Extract alerts from ERROR/WARN log lines that match a known signature."""
    alerts: list[Alert] = []
    for line in lines:
        m = LOG_RE.match(line.strip())
        if not m:
            continue
        msg = m["msg"]
        name = next((n for rx, n in LOG_SIGNATURES if rx.search(msg)), None)
        if name is None:
            continue
        level = m["level"].upper()
        labels = {"alertname": name, "service": m["service"], "source": "logs"}
        if m["pod"]:
            labels["pod"] = m["pod"]
        alerts.append(
            Alert(
                name=name,
                service=m["service"],
                severity_hint="critical" if level in {"CRITICAL", "FATAL"} else ("warning" if level.startswith("WARN") else "error"),
                instance=m["pod"],
                summary=msg,
                labels=labels,
                starts_at=_parse_time(m["ts"]),
                source="logs",
                fingerprint=_fingerprint(labels),
            )
        )
    return alerts
