"""Command line entry point.

    python -m triage.cli --alerts data/sample_alertmanager.json --logs data/sample_app.log
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .agent import TriageAgent
from .ingest import from_alertmanager, from_logs
from .llm import get_llm
from .ticket import build_ticket, to_markdown


def main() -> None:
    p = argparse.ArgumentParser(description="Triage Prometheus alerts and logs into ITSM tickets")
    p.add_argument("--alerts", type=Path, help="Alertmanager webhook JSON file")
    p.add_argument("--logs", type=Path, help="application log file")
    p.add_argument("--llm", choices=["auto", "ollama", "offline"], default="auto")
    p.add_argument("--json", action="store_true", help="print tickets as JSON")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    alerts = []
    if args.alerts:
        alerts += from_alertmanager(json.loads(args.alerts.read_text()))
    if args.logs:
        alerts += from_logs(args.logs.read_text().splitlines())
    if not alerts:
        p.error("provide --alerts and/or --logs")

    incidents = TriageAgent(llm=get_llm(args.llm)).run(alerts)
    if args.json:
        print(json.dumps([build_ticket(i) for i in incidents], indent=2))
    else:
        for inc in incidents:
            print(to_markdown(inc))


if __name__ == "__main__":
    main()
