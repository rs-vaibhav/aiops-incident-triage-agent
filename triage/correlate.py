"""Group related alerts into incidents to reduce alert noise."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from .models import Alert, Incident

# Services that commonly cause alerts in other services. A symptom alert on a
# dependant is merged into the incident of the dependency when both fire together.
DEFAULT_DEPENDENCIES: dict[str, list[str]] = {
    "checkout-api": ["payments-api", "postgres"],
    "payments-api": ["postgres"],
    "orders-api": ["postgres"],
}


def correlate(
    alerts: list[Alert],
    window: timedelta = timedelta(minutes=10),
    dependencies: dict[str, list[str]] | None = None,
) -> list[Incident]:
    """Correlate alerts in three passes:

    1. drop resolved alerts and duplicates (same fingerprint)
    2. group alerts for the same service that start within `window` of each other
    3. merge groups whose service depends on another service that is also alerting
    """
    deps = dependencies if dependencies is not None else DEFAULT_DEPENDENCIES

    seen: set[str] = set()
    firing: list[Alert] = []
    for a in sorted(alerts, key=lambda x: x.starts_at):
        if a.status != "firing" or a.fingerprint in seen:
            continue
        seen.add(a.fingerprint)
        firing.append(a)

    groups: list[list[Alert]] = []
    for a in firing:
        for g in groups:
            if g[0].service == a.service and a.starts_at - g[-1].starts_at <= window:
                g.append(a)
                break
        else:
            groups.append([a])

    # Merge dependant-service groups into the group of the failing dependency.
    by_service = {g[0].service: g for g in groups}
    merged_into: dict[int, int] = {}
    for i, g in enumerate(groups):
        for dep in deps.get(g[0].service, []):
            target = by_service.get(dep)
            if target is not None and abs(target[0].starts_at - g[0].starts_at) <= window:
                merged_into[i] = groups.index(target)
                break

    final: dict[int, list[Alert]] = {}
    for i, g in enumerate(groups):
        root = i
        while root in merged_into:
            root = merged_into[root]
        final.setdefault(root, []).extend(g)

    incidents = []
    for root, group in final.items():
        group.sort(key=lambda x: x.starts_at)
        key = "|".join(sorted(a.fingerprint for a in group))
        inc_id = "INC-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()
        incidents.append(Incident(id=inc_id, service=groups[root][0].service, alerts=group, opened_at=group[0].starts_at))
    return sorted(incidents, key=lambda i: i.opened_at)
