"""Evaluate the triage agent against a labelled incident set.

Metrics
* severity_accuracy   - predicted P1-P4 equals the label
* runbook_top1        - first retrieved runbook equals the label
* hallucination_rate  - share of LLM-suggested steps NOT found in the retrieved runbook
                        (these are dropped by the guardrail, but we still track how often the model invents them)
* blocked_destructive - destructive steps held back for manual decision

    python eval/evaluate.py --llm offline
    python eval/evaluate.py --llm ollama      # with a local Ollama server
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from triage import guardrails  # noqa: E402
from triage.agent import TriageAgent  # noqa: E402
from triage.ingest import from_alertmanager  # noqa: E402
from triage.llm import get_llm  # noqa: E402


class RecordingLLM:
    """Wraps the real LLM to record raw suggestions before the guardrail filters them."""

    def __init__(self, inner):
        self.inner, self.name, self.last = inner, getattr(inner, "name", "?"), None

    def triage(self, incident, runbook):
        self.last = (self.inner.triage(incident, runbook), runbook)
        return self.last[0]


def to_payload(case: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "alerts": [
            {
                "status": "firing",
                "labels": {k: v for k, v in a.items() if k != "summary"},
                "annotations": {"summary": a.get("summary", "")},
                "startsAt": now,
            }
            for a in case["alerts"]
        ]
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="offline", choices=["offline", "ollama", "auto"])
    ap.add_argument("--cases", type=Path, default=ROOT / "eval" / "labelled_incidents.json")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "report.json")
    args = ap.parse_args()

    rec = RecordingLLM(get_llm(args.llm))
    agent = TriageAgent(llm=rec)
    cases = json.loads(args.cases.read_text())

    rows, sev_ok, rb_ok, suggested, ungrounded, blocked = [], 0, 0, 0, 0, 0
    for case in cases:
        incidents = agent.run(from_alertmanager(to_payload(case)))
        inc = max(incidents, key=lambda i: len(i.alerts))
        raw, book = rec.last
        _, b, rejected = guardrails.apply(raw.get("remediation_steps", []), book.steps)
        suggested += len(raw.get("remediation_steps", []))
        ungrounded += len(rejected)
        blocked += len(b)
        s_ok = inc.severity == case["expected_severity"]
        r_ok = inc.runbook == case["expected_runbook"]
        sev_ok += s_ok
        rb_ok += r_ok
        rows.append({"id": case["id"], "severity": inc.severity, "expected_severity": case["expected_severity"],
                     "runbook": inc.runbook, "expected_runbook": case["expected_runbook"],
                     "severity_ok": s_ok, "runbook_ok": r_ok})

    n = len(cases)
    report = {
        "llm": rec.name,
        "retriever": agent.index.backend,
        "cases": n,
        "severity_accuracy": round(sev_ok / n, 3),
        "runbook_top1_accuracy": round(rb_ok / n, 3),
        "hallucination_rate": round(ungrounded / suggested, 3) if suggested else 0.0,
        "blocked_destructive_steps": blocked,
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(f"{'case':<5} {'sev':<4} {'exp':<4} {'runbook':<20} {'expected':<20}")
    for r in rows:
        mark = "" if r["severity_ok"] and r["runbook_ok"] else "  <-- mismatch"
        print(f"{r['id']:<5} {r['severity']:<4} {r['expected_severity']:<4} {r['runbook']:<20} {r['expected_runbook']:<20}{mark}")
    print({k: v for k, v in report.items() if k != "rows"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
