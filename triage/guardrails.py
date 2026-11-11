"""Safety checks applied to every suggested remediation step.

Rules:
* A step must come from the retrieved runbook (grounding) - anything the LLM invents is dropped.
* Destructive commands are never auto-suggested; they are moved to `blocked_steps` for a human.
* Nothing is executed by the agent. Every incident waits for human approval.
"""
from __future__ import annotations

import re

DESTRUCTIVE = [
    r"\brm\s+-rf\b",
    r"\bkubectl\s+delete\s+(namespace|ns|pvc|pv|node)\b",
    r"\bdrop\s+(table|database)\b",
    r"\btruncate\b",
    r"\bterraform\s+destroy\b",
    r"\bmkfs\b",
    r"\bshutdown\b|\breboot\b",
    r"--force\b",
]
DESTRUCTIVE_RE = re.compile("|".join(DESTRUCTIVE), re.I)


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().rstrip("."))


def is_destructive(step: str) -> bool:
    return bool(DESTRUCTIVE_RE.search(step))


def apply(steps: list[str], runbook_steps: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (allowed, blocked_destructive, rejected_ungrounded)."""
    grounded = {normalise(s) for s in runbook_steps}
    allowed, blocked, rejected = [], [], []
    for s in steps:
        if normalise(s) not in grounded:
            rejected.append(s)
        elif is_destructive(s):
            blocked.append(s)
        else:
            allowed.append(s)
    return allowed, blocked, rejected
