# AIOps Incident Triage Agent

An AI agent that turns a flood of Prometheus alerts and application logs into a small number of
**triaged, ticket-ready incidents**: correlated, prioritised (P1–P4), matched to a runbook, and
with grounded remediation steps that wait for **human approval**.

```
 Alertmanager webhook ─┐
                       ├─► ingest ─► correlate ─► classify ─► retrieve runbook ─► LLM reasoning ─► guardrails ─► ITSM ticket
 application logs ─────┘   (normalise) (dedup,     (rule-based  (ChromaDB / TF-IDF   (LangChain +     (grounding +   (ServiceNow-style
                                       time window, P1-P4 score)  + alert-name boost)  Ollama llama3.2)  destructive    fields, approve /
                                       dependency                                                       command block)  reject API)
                                       graph)
```

## Why it is built this way

| Decision | Reason |
|---|---|
| Severity is **rule-based**, not LLM-decided | Paging decisions must be explainable and stable. Every ticket shows the score breakdown. |
| Remediation steps must be **copied from a runbook** | Any step the model invents is dropped by the guardrail and counted as a hallucination in the eval. |
| **Destructive commands** (`rm -rf`, `kubectl delete namespace`, `terraform destroy`, `DROP TABLE`…) are never suggested | They are moved to a "blocked – manual decision only" section. |
| Agent **never executes** anything | Every incident is `pending_approval` until an engineer calls `/incidents/{id}/approve`. |
| Works **offline** | Without Ollama/ChromaDB it falls back to a TF-IDF retriever and a template "LLM", so CI and demos always run. |

## Quick start

```bash
pip install -r requirements.txt

# 1. CLI on the sample data (offline mode, no model needed)
python -m triage.cli --alerts data/sample_alertmanager.json --logs data/sample_app.log --llm offline

# 2. With a real local LLM
ollama pull llama3.2 && ollama serve
python -m triage.cli --alerts data/sample_alertmanager.json --logs data/sample_app.log --llm ollama

# 3. As a service that Alertmanager calls
uvicorn triage.api:app --port 8080
curl -X POST localhost:8080/alerts -H 'content-type: application/json' -d @data/sample_alertmanager.json
curl -X POST localhost:8080/logs --data-binary @data/sample_app.log
curl localhost:8080/incidents
curl -X POST localhost:8080/incidents/<INC-ID>/approve

# or everything in containers (agent + Ollama)
docker compose up --build
```

Alertmanager config:

```yaml
receivers:
  - name: triage-agent
    webhook_configs:
      - url: http://triage-agent:8080/alerts
```

## Example output

11 raw signals (5 Alertmanager alerts incl. one resolved, 6 log errors) → **4 incidents**. The DB pool
exhaustion, payments latency and checkout 5xx are recognised as one incident via the service
dependency graph (`checkout-api → payments-api → postgres`):

```
### INC-C2F21254 [P1] DBConnectionPoolExhausted, HighErrorRate, HighLatency, UpstreamTimeout - postgres
Assignment group: DBA-Operations
Severity rationale: score=95: strongest signal HighErrorRate (+40); alert severity label (+20);
  business-critical service [...] (+20); blast radius 3 services (+10); 5 correlated alerts (+5)
Runbook: db-connection-pool (match score 1.40)
Suggested remediation (requires human approval):
  1. Identify and cancel long-running queries with pg_cancel_backend(pid) after confirming with the service owner
  2. Roll back the most recent deployment of the affected service if the issue started right after it
  ...
```

## Evaluation

`eval/labelled_incidents.json` holds 12 hand-labelled incidents (expected priority and runbook).

```bash
python eval/evaluate.py --llm offline     # or --llm ollama
```

| Metric | Offline mode |
|---|---|
| Severity accuracy | 0.917 (11/12) |
| Runbook top-1 accuracy | 1.000 |
| Hallucination rate (LLM steps not in runbook) | 0.000 |

The one miss (E03, an OOMKill on a non-critical batch job labelled P3, scored P4) is a known
trade-off of the weighting. Run with `--llm ollama` to measure how often the real model invents steps.

## Project layout

```
triage/
  ingest.py      Alertmanager webhook + log-line parsing (error signatures -> alerts)
  correlate.py   dedup, time-window grouping, dependency-graph merge
  classify.py    explainable P1-P4 scoring
  rag.py         runbook loader, ChromaDB retriever, TF-IDF fallback, alert-name boosting
  llm.py         LangChain + Ollama (JSON mode, temperature 0) with offline fallback
  guardrails.py  grounding check + destructive-command block
  ticket.py      ServiceNow-style ticket (impact/urgency/priority, CMDB CI, assignment group)
  agent.py       pipeline orchestration
  api.py         FastAPI: /alerts, /logs, /incidents, approve/reject
runbooks/        7 runbooks (DB pool, crashloop/OOM, disk, latency, 5xx, TLS, CPU/memory)
eval/            labelled set + evaluation script
tests/           pytest suite (9 tests)
```

## Ideas to extend

- Pull the service dependency graph from the CMDB instead of a hard-coded dict
- Create the ticket in ServiceNow / Jira via their REST APIs after approval
- Add a Slack approval button instead of the HTTP endpoint
- Feed resolved incidents back into the runbook index
