"""Eval harness runner.

    python -m eval.run [--systems graphrag,baseline] [--limit N]

Runs every question in eval/questions.jsonl through the requested
system(s), scores each with eval/metrics.py, and writes:
  - eval/results.md           human-readable comparison, metric by metric
  - eval/results_detail.jsonl one record per (question, system)

Reports real numbers, including failures — this harness does not try to
make either system look good. See the "Infrastructure" section
results.md always opens with: several categories are honestly
unmeasurable in an environment without reachable embeddings/LLM access,
and that is reported as exactly that, not papered over with a fabricated
score.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from eval import metrics as M

QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"
RESULTS_MD_PATH = Path(__file__).parent / "results.md"
RESULTS_DETAIL_PATH = Path(__file__).parent / "results_detail.jsonl"
ERP_DIR = Path("data/inbox/erp")


@dataclass
class QuestionResult:
    question_id: str
    category: str
    system: str
    question: str
    answer: str
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_sku_ids: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None
    retrieval_precision: float = 0.0
    path_correctness: float | None = None
    hallucination_rate: float | None = None


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_known_entity_ids(erp_dir: Path = ERP_DIR) -> set[str]:
    """All real entity ids from the structured exports — the ground
    truth for the hallucination-rate check. Empty set (not an error) if
    the exports aren't present; hallucination_rate then can't be scored
    for anything, which load_known_entity_ids callers should treat the
    same way as any other 'infra unavailable' case."""
    ids: set[str] = set()
    try:
        sup = json.loads((erp_dir / "suppliers_export.json").read_text())
        ids.update(s["id"] for s in sup.get("suppliers", []))
    except FileNotFoundError:
        pass
    try:
        sku = json.loads((erp_dir / "skus_export.json").read_text())
        ids.update(k["sku_id"] for k in sku.get("skus", []))
    except FileNotFoundError:
        pass
    try:
        cmp_ = json.loads((erp_dir / "components_export.json").read_text())
        ids.update(c["id"] for c in cmp_.get("components", []))
    except FileNotFoundError:
        pass
    try:
        rt = json.loads((erp_dir / "routes_export.json").read_text())
        ids.update(r["route_id"] for r in rt.get("routes", []))
    except FileNotFoundError:
        pass
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(erp_dir / "plants_export.xml").getroot()
        ids.update(p.attrib["id"] for p in root.findall("Plant"))
    except FileNotFoundError:
        pass
    return ids


def run_graphrag_question(q: dict, *, driver=None, embedder=None,
                           index=None) -> QuestionResult:
    from src.retrieve.service import answer_question

    logs: list[str] = []
    t0 = time.monotonic()
    try:
        result = answer_question(q["question"], as_of=q.get("as_of"),
                                  driver=driver, embedder=embedder, index=index,
                                  log_fn=logs.append)
        latency_ms = (time.monotonic() - t0) * 1000
        doc_ids = [sr.doc_id for sr in result.source_refs]
        sku_ids = sorted({p.target_id for p in result.graph_paths
                           if p.target_type == "SKU"})
        answer_text = result.direct_answer
        error = None
        # service.answer_question degrades gracefully on a dispatcher
        # failure (logs and moves on) rather than raising — which means
        # a real infra problem can look identical to a clean "no
        # evidence" result unless we surface it ourselves. Without this,
        # a transient Neo4j/Qdrant outage mid-run would silently score
        # as the system "trying and finding nothing" instead of being
        # reported as what it actually was (see git history: this is
        # exactly what happened with Neo4j's AuthenticationRateLimit
        # during Phase 6 eval runs before this harness carried logs
        # through to the result).
        if not doc_ids and not sku_ids:
            unavailable = [m for m in logs if "unavailable" in m]
            if unavailable:
                error = "degraded: " + "; ".join(unavailable)
    except Exception as exc:   # noqa: BLE001
        latency_ms = (time.monotonic() - t0) * 1000
        doc_ids, sku_ids, answer_text = [], [], ""
        error = f"{type(exc).__name__}: {exc}"

    return QuestionResult(
        question_id=q["id"], category=q["category"], system="graphrag",
        question=q["question"], answer=answer_text,
        retrieved_doc_ids=doc_ids, retrieved_sku_ids=sku_ids,
        latency_ms=latency_ms, cost_usd=0.0,   # GraphRAG never calls an LLM
        error=error,
    )


def run_baseline_question(q: dict, *, embedder, index, chat_client) -> QuestionResult:
    from eval.baseline_vector_rag import BaselineResult, answer_with_vector_rag

    if embedder is None or index is None:
        res = BaselineResult(
            question=q["question"], answer="",
            error="retrieval unavailable: no embedder/Qdrant backend "
                  "reachable (see 'Infrastructure' section)",
        )
    else:
        res = answer_with_vector_rag(q["question"], embedder=embedder, index=index,
                                      chat_client=chat_client)
    cost = M.cost_usd(res.prompt_tokens, res.completion_tokens,
                       res.model or "") if res.model else 0.0
    return QuestionResult(
        question_id=q["id"], category=q["category"], system="baseline",
        question=q["question"], answer=res.answer,
        retrieved_doc_ids=res.retrieved_source_files,
        retrieved_sku_ids=[], latency_ms=res.latency_ms, cost_usd=cost,
        error=res.error,
    )


def score(qr: QuestionResult, q: dict, known_ids: set[str]) -> None:
    expected = q["expected"]
    qr.retrieval_precision = M.retrieval_precision(
        qr.retrieved_doc_ids, expected.get("source_doc_ids") or [])
    qr.path_correctness = M.path_correctness(
        qr.retrieved_sku_ids, expected.get("expected_sku_ids"))
    mentions = M.extract_entity_mentions(qr.answer)
    qr.hallucination_rate = (M.hallucination_rate(mentions, known_ids)
                              if known_ids else None)


def _init_baseline_backends():
    """Best-effort — returns (embedder, index, chat_client), any of
    which may be None if that backend isn't reachable. Mirrors the
    graceful-degradation pattern in src/ingest/pipeline.py."""
    embedder = index = chat_client = None
    try:
        from src.index.embeddings import Embedder
        from src.index.qdrant import QdrantIndex
        emb = Embedder(host=os.environ.get("OLLAMA_EMBED_HOST",
                                            "http://localhost:11434"),
                        model=os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3"),
                        expected_dim=int(os.environ.get("OLLAMA_EMBED_DIM", "1024")))
        dim = emb.ping()
        idx = QdrantIndex(url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
                           vector_dim=dim)
        embedder, index = emb, idx
    except Exception as exc:   # noqa: BLE001
        print(f"[eval] baseline retrieval backend unavailable: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
    api_key = os.environ.get("OLLAMA_CLOUD_API_KEY")
    if api_key:
        from src.extract.client import OllamaChat
        chat_client = OllamaChat(
            host=os.environ.get("OLLAMA_CLOUD_HOST", "https://ollama.com"),
            api_key=api_key,
            model=os.environ.get("OLLAMA_EXTRACT_MODEL", "gpt-oss:20b"),
        )
    return embedder, index, chat_client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--systems", default="graphrag,baseline")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]
    known_ids = load_known_entity_ids()

    embedder = index = chat_client = None
    if "baseline" in systems:
        embedder, index, chat_client = _init_baseline_backends()

    # One Neo4j driver reused across every question in this run, not one
    # per question — see the docstring on run_graphrag_question for why
    # that matters (Neo4j's AuthenticationRateLimit under connection
    # churn, discovered running this harness for real).
    driver = None
    if "graphrag" in systems:
        driver = _init_shared_neo4j_driver()

    try:
        all_results: list[QuestionResult] = []
        for q in questions:
            if "graphrag" in systems:
                qr = run_graphrag_question(q, driver=driver, embedder=embedder,
                                            index=index)
                score(qr, q, known_ids)
                all_results.append(qr)
            if "baseline" in systems:
                qr = run_baseline_question(q, embedder=embedder, index=index,
                                            chat_client=chat_client)
                score(qr, q, known_ids)
                all_results.append(qr)
    finally:
        if driver is not None:
            driver.close()

    RESULTS_DETAIL_PATH.write_text(
        "\n".join(json.dumps(asdict(r)) for r in all_results) + "\n"
    )
    md = render_results_md(all_results, questions, systems,
                            baseline_backends_live=(embedder is not None,
                                                     chat_client is not None),
                            graph_live=(driver is not None))
    RESULTS_MD_PATH.write_text(md)
    print(md)
    return 0


def _init_shared_neo4j_driver():
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.environ.get("NEO4J_USER", "neo4j"),
                  os.environ.get("NEO4J_PASSWORD", "")),
        )
        with driver.session() as s:
            s.run("RETURN 1")
        return driver
    except Exception as exc:   # noqa: BLE001
        print(f"[eval] Neo4j unavailable: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return None


def render_results_md(results: list[QuestionResult], questions: list[dict],
                       systems: list[str],
                       baseline_backends_live: tuple[bool, bool],
                       graph_live: bool = False) -> str:
    emb_live, llm_live = baseline_backends_live
    lines: list[str] = []
    lines.append("# Phase 6 eval results\n")
    lines.append(f"Questions: {len(questions)}. Systems: {', '.join(systems)}.\n")
    lines.append("## Infrastructure actually reachable during this run\n")
    lines.append(f"- Neo4j: {'reachable' if graph_live else '**NOT reachable**'}")
    lines.append(f"- Qdrant/embeddings: {'reachable' if emb_live else '**NOT reachable**'}")
    llm_note = ("reachable" if llm_live else
                "**NOT reachable** (no OLLAMA_CLOUD_API_KEY / not run)")
    lines.append(f"- Ollama Cloud (baseline answer LLM): {llm_note}")
    lines.append("")
    if not emb_live:
        lines.append(
            "**Every metric that depends on semantic retrieval is honestly "
            "unmeasurable in this run, for both systems** — this sandboxed "
            "environment's egress proxy blocks `ollama.com` outright "
            "(confirmed: `curl https://ollama.com/install.sh` returns "
            "connect_rejected/403), so no embeddings could be produced "
            "anywhere. Numbers below of 0.0 for semantic-dependent "
            "categories mean 'no evidence could be retrieved', not 'the "
            "system tried and got it wrong.'\n"
        )

    by_system: dict[str, list[QuestionResult]] = {}
    for r in results:
        by_system.setdefault(r.system, []).append(r)

    lines.append("## Overall (all categories)\n")
    lines.append("| System | Mean retrieval precision | Mean path correctness "
                  "(n scored) | Mean hallucination rate (n scored) | "
                  "p50 latency (ms) | p95 latency (ms) | Total cost (USD) | "
                  "Errors |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for sysname in systems:
        rs = by_system.get(sysname, [])
        lines.append(_overall_row(sysname, rs))
    lines.append("")

    lines.append("## By category\n")
    categories = sorted({q["category"] for q in questions})
    for cat in categories:
        lines.append(f"### {cat}\n")
        lines.append("| System | Mean retrieval precision | Mean path "
                      "correctness (n) | Mean hallucination rate (n) | "
                      "Errors |")
        lines.append("|---|---|---|---|---|")
        for sysname in systems:
            rs = [r for r in by_system.get(sysname, []) if r.category == cat]
            lines.append(_category_row(sysname, rs))
        lines.append("")

    lines.append("## Failures (every error, not summarised away)\n")
    any_errors = False
    for r in results:
        if r.error:
            any_errors = True
            lines.append(f"- `{r.system}` / `{r.question_id}` "
                          f"({r.category}): {r.error}")
    if not any_errors:
        lines.append("No hard errors — every question returned a result "
                      "object (possibly 'no evidence found'), nothing raised.")
    lines.append("")
    return "\n".join(lines)


def _overall_row(sysname: str, rs: list[QuestionResult]) -> str:
    if not rs:
        return f"| {sysname} | (no results) | | | | | | |"
    precision = _mean(r.retrieval_precision for r in rs)
    pc_vals = [r.path_correctness for r in rs if r.path_correctness is not None]
    hr_vals = [r.hallucination_rate for r in rs if r.hallucination_rate is not None]
    lat = M.latency_stats([r.latency_ms for r in rs])
    total_cost = sum(r.cost_usd for r in rs)
    n_errors = sum(1 for r in rs if r.error)
    return (f"| {sysname} | {precision:.3f} | "
            f"{_fmt_mean(pc_vals)} | {_fmt_mean(hr_vals)} | "
            f"{lat.p50_ms:.1f} | {lat.p95_ms:.1f} | {total_cost:.4f} | "
            f"{n_errors}/{len(rs)} |")


def _category_row(sysname: str, rs: list[QuestionResult]) -> str:
    if not rs:
        return f"| {sysname} | (no results) | | | |"
    precision = _mean(r.retrieval_precision for r in rs)
    pc_vals = [r.path_correctness for r in rs if r.path_correctness is not None]
    hr_vals = [r.hallucination_rate for r in rs if r.hallucination_rate is not None]
    n_errors = sum(1 for r in rs if r.error)
    return (f"| {sysname} | {precision:.3f} | {_fmt_mean(pc_vals)} | "
            f"{_fmt_mean(hr_vals)} | {n_errors}/{len(rs)} |")


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _fmt_mean(values: list[float]) -> str:
    if not values:
        return "n/a (0 scored)"
    return f"{_mean(values):.3f} ({len(values)})"


if __name__ == "__main__":
    raise SystemExit(main())
