"""Retrieval over the runbook library.

Uses ChromaDB (with its default embedding model) when available; otherwise falls back
to a small built-in TF-IDF retriever so the project runs fully offline and in CI.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = set("the a an and or of to in on for is are be with this that it if by as at from when".split())


def tokenize(text: str) -> list[str]:
    # split CamelCase alert names: DBConnectionPoolExhausted -> db connection pool exhausted
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


@dataclass
class Runbook:
    name: str
    title: str
    text: str
    alerts: list[str]          # alert names declared in the runbook front-matter
    steps: list[str]           # remediation steps (numbered list under "## Remediation")


def load_runbooks(directory: str | Path) -> list[Runbook]:
    books = []
    for p in sorted(Path(directory).glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), p.stem)
        m = re.search(r"^alerts:\s*(.+)$", text, re.M)
        alerts = [a.strip() for a in m.group(1).split(",")] if m else []
        rem = re.search(r"## Remediation\n(.*?)(\n## |\Z)", text, re.S)
        steps = []
        if rem:
            steps = [re.sub(r"^\d+\.\s*", "", l).strip() for l in rem.group(1).splitlines() if re.match(r"^\d+\.", l.strip())]
        books.append(Runbook(p.stem, title, text, alerts, steps))
    return books


class TfidfRetriever:
    def __init__(self, books: list[Runbook]):
        self.books = books
        self.docs = [Counter(tokenize(b.title + " " + " ".join(b.alerts) * 3 + " " + b.text)) for b in books]
        n = len(books)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in self.docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query: str, k: int = 3) -> list[tuple[Runbook, float]]:
        q = self._vec(Counter(tokenize(query)))
        scored = [(b, sum(q.get(t, 0) * w for t, w in v.items())) for b, v in zip(self.books, self.vecs, strict=True)]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:k]


class ChromaRetriever:
    def __init__(self, books: list[Runbook]):
        import chromadb  # noqa: WPS433 (optional dependency)

        self.books = {b.name: b for b in books}
        client = chromadb.EphemeralClient()
        self.col = client.get_or_create_collection("runbooks", metadata={"hnsw:space": "cosine"})
        self.col.upsert(
            ids=[b.name for b in books],
            documents=[f"{b.title}\nAlerts: {', '.join(b.alerts)}\n{b.text}" for b in books],
        )

    def search(self, query: str, k: int = 3) -> list[tuple[Runbook, float]]:
        res = self.col.query(query_texts=[query], n_results=min(k, len(self.books)))
        return [(self.books[i], 1 - d) for i, d in zip(res["ids"][0], res["distances"][0], strict=True)]


class RunbookIndex:
    """Hybrid retrieval: an exact alert-name match wins, semantic search breaks ties."""

    def __init__(self, directory: str | Path, backend: str = "auto"):
        self.books = load_runbooks(directory)
        self.backend = "tfidf"
        if backend in ("auto", "chroma"):
            try:
                self.retriever = ChromaRetriever(self.books)
                self.backend = "chroma"
            except Exception:  # chromadb missing or model download blocked
                if backend == "chroma":
                    raise
                self.retriever = TfidfRetriever(self.books)
        else:
            self.retriever = TfidfRetriever(self.books)

    def search(self, query: str, alert_names: list[str] | None = None, k: int = 3) -> list[tuple[Runbook, float]]:
        results = self.retriever.search(query, k=len(self.books))
        if alert_names:
            boosted = []
            for b, s in results:
                hits = len(set(alert_names) & set(b.alerts))
                boosted.append((b, s + 0.5 * hits))
            results = sorted(boosted, key=lambda x: x[1], reverse=True)
        return results[:k]
