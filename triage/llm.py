"""LLM access through LangChain + Ollama, with an offline fallback.

The fallback keeps the pipeline usable (and testable) when no model server is running:
it writes the root cause from the runbook's "Likely causes" section instead of a model.
"""
from __future__ import annotations

import json
import os
import re

from .models import Incident
from .rag import Runbook

PROMPT = """You are an SRE assistant helping triage a production incident.
Use ONLY the runbook below. Do not invent commands.

Incident: {incident_id} on service {service}
Correlated alerts:
{alerts}

Runbook "{runbook_title}":
{runbook}

Return JSON with exactly these keys:
  "probable_root_cause": one or two sentences,
  "remediation_steps": list of steps copied verbatim from the runbook's Remediation section, most relevant first (max 4).
JSON:"""


class OfflineLLM:
    name = "offline-template"

    def triage(self, incident: Incident, runbook: Runbook) -> dict:
        causes = re.search(r"## Likely causes\n(.*?)(\n## |\Z)", runbook.text, re.S)
        first = ""
        if causes:
            bullets = [l.lstrip("-* ").strip() for l in causes.group(1).splitlines() if l.strip().startswith(("-", "*"))]
            first = bullets[0] if bullets else ""
        alerts = ", ".join(incident.alert_names)
        rc = f"{alerts} on {incident.service}. Most likely cause per runbook '{runbook.title}': {first or 'see runbook'}."
        return {"probable_root_cause": rc, "remediation_steps": runbook.steps[:4]}


class OllamaLLM:
    def __init__(self, model: str | None = None, base_url: str | None = None):
        from langchain_ollama import OllamaLLM as _Ollama  # optional dependency

        self.name = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        self.llm = _Ollama(
            model=self.name,
            base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,
            format="json",
        )

    def triage(self, incident: Incident, runbook: Runbook) -> dict:
        prompt = PROMPT.format(
            incident_id=incident.id,
            service=incident.service,
            alerts="\n".join(f"- {a.text()}" for a in incident.alerts),
            runbook_title=runbook.title,
            runbook=runbook.text[:4000],
        )
        raw = self.llm.invoke(prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
        return {
            "probable_root_cause": str(data.get("probable_root_cause", "")).strip(),
            "remediation_steps": [str(s) for s in data.get("remediation_steps", [])][:4],
        }


def get_llm(mode: str | None = None):
    mode = mode or os.getenv("TRIAGE_LLM", "auto")
    if mode == "offline":
        return OfflineLLM()
    try:
        llm = OllamaLLM()
        if mode == "auto":
            llm.llm.invoke("ping")  # fail fast if the server is not reachable
        return llm
    except Exception:
        if mode == "ollama":
            raise
        return OfflineLLM()
