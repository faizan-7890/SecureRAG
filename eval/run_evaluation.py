"""SecureRAG — Ragas Evaluation Pipeline.

Ingests the sample policy document, queries the RAG pipeline for each
golden-dataset question, and evaluates retrieval + generation quality
using the Ragas framework.

Usage:
    .\.venv\Scripts\python.exe -m eval.run_evaluation
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DATASET = PROJECT_ROOT / "data" / "eval" / "golden_dataset.json"
SAMPLE_DOCUMENT = PROJECT_ROOT / "data" / "eval" / "company_policy.txt"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("securerag.eval")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_golden_dataset() -> list[dict]:
    """Load the curated golden evaluation dataset."""
    if not GOLDEN_DATASET.exists():
        logger.error("Golden dataset not found at %s", GOLDEN_DATASET)
        sys.exit(1)
    with GOLDEN_DATASET.open(encoding="utf-8") as f:
        dataset = json.load(f)
    logger.info("Loaded %d golden samples from %s", len(dataset), GOLDEN_DATASET.name)
    return dataset


def _ingest_sample_document(settings) -> int:
    """Ingest the sample policy document and return the chunk count."""
    from app.services.ingestion import DocumentIngestionService

    if not SAMPLE_DOCUMENT.exists():
        logger.error("Sample document not found at %s", SAMPLE_DOCUMENT)
        sys.exit(1)

    service = DocumentIngestionService(settings)
    result = service.ingest(SAMPLE_DOCUMENT, SAMPLE_DOCUMENT.name)
    logger.info("Ingested '%s' → %d chunks", result.filename, result.chunks)
    return result.chunks


def _query_rag(question: str, settings) -> tuple[str, list[str]]:
    """Query the RAG pipeline and return (answer, retrieved_contexts)."""
    from app.services.rag_service import RAGService

    service = RAGService(settings)

    # Get the raw retrieved chunks (for context evaluation)
    chunks = service._retrieve(question)
    contexts = [chunk.document.page_content for chunk in chunks]

    # Get the full answer
    response = service.answer(question)

    return response.answer, contexts


def _run_ragas_evaluation(samples: list[dict]) -> dict:
    """Build a Ragas EvaluationDataset and evaluate."""
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerCorrectness,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )
    from langchain_openai import ChatOpenAI

    from app.core.config import get_settings

    settings = get_settings()

    ragas_samples = []
    for s in samples:
        ragas_samples.append(
            SingleTurnSample(
                user_input=s["question"],
                retrieved_contexts=s["retrieved_contexts"],
                response=s["response"],
                reference=s["ground_truth"],
            )
        )

    dataset = EvaluationDataset(samples=ragas_samples)

    # Use the same OpenAI model configured in the project for judge calls.
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
    )

    metrics = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm),
        ContextPrecision(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
        AnswerCorrectness(llm=evaluator_llm),
    ]

    logger.info("Running Ragas evaluation with %d metrics...", len(metrics))
    result = evaluate(dataset=dataset, metrics=metrics)

    return result


def _save_results(result, samples: list[dict], duration_s: float) -> Path:
    """Persist the evaluation results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Build per-sample detail
    df = result.to_pandas()
    per_sample = []
    for i, row in df.iterrows():
        per_sample.append({
            "question": samples[i]["question"],
            "ground_truth": samples[i]["ground_truth"],
            "response": samples[i]["response"],
            "retrieved_contexts_count": len(samples[i]["retrieved_contexts"]),
            "faithfulness": _safe_float(row.get("faithfulness")),
            "answer_relevancy": _safe_float(row.get("answer_relevancy")),
            "context_precision": _safe_float(row.get("context_precision")),
            "context_recall": _safe_float(row.get("context_recall")),
            "answer_correctness": _safe_float(row.get("answer_correctness")),
        })

    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "duration_seconds": round(duration_s, 1),
        "sample_count": len(samples),
        "aggregate_scores": {
            "faithfulness": _safe_float(df.get("faithfulness", []).mean() if "faithfulness" in df else None),
            "answer_relevancy": _safe_float(df.get("answer_relevancy", []).mean() if "answer_relevancy" in df else None),
            "context_precision": _safe_float(df.get("context_precision", []).mean() if "context_precision" in df else None),
            "context_recall": _safe_float(df.get("context_recall", []).mean() if "context_recall" in df else None),
            "answer_correctness": _safe_float(df.get("answer_correctness", []).mean() if "answer_correctness" in df else None),
        },
        "per_sample": per_sample,
    }

    out_path = RESULTS_DIR / "evaluation_results.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Results saved to %s", out_path)
    return out_path


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None for NaN/None."""
    if value is None:
        return None
    try:
        f = float(value)
        import math
        return round(f, 4) if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def _print_summary(result) -> None:
    """Print a formatted summary table to the console."""
    df = result.to_pandas()

    print("\n" + "=" * 64)
    print("  SecureRAG — Ragas Evaluation Summary")
    print("=" * 64)

    metric_names = [
        ("faithfulness", "Faithfulness"),
        ("answer_relevancy", "Answer Relevancy"),
        ("context_precision", "Context Precision"),
        ("context_recall", "Context Recall"),
        ("answer_correctness", "Answer Correctness"),
    ]

    for col, label in metric_names:
        if col in df.columns:
            mean = df[col].mean()
            mini = df[col].min()
            maxi = df[col].max()
            print(f"  {label:<22s}  avg={mean:.3f}  min={mini:.3f}  max={maxi:.3f}")
        else:
            print(f"  {label:<22s}  (not available)")

    print("=" * 64)
    print(f"  Samples evaluated: {len(df)}")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    from app.core.config import Settings, get_settings

    settings = get_settings()

    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY is required for evaluation. Set it in your .env file.")
        sys.exit(1)

    # Use a temporary Chroma directory so evaluation doesn't pollute production data.
    tmp_dir = TemporaryDirectory(prefix="securerag_eval_")
    eval_settings = Settings(
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        chroma_path=Path(tmp_dir.name) / "chroma_eval",
        chroma_collection="securerag_eval",
        upload_dir=settings.upload_dir,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.top_k,
        retrieval_candidate_k=settings.retrieval_candidate_k,
        similarity_threshold=settings.similarity_threshold,
        citation_excerpt_chars=settings.citation_excerpt_chars,
    )

    logger.info("=" * 50)
    logger.info("SecureRAG — Ragas Evaluation Pipeline")
    logger.info("=" * 50)

    # Step 1: Load golden dataset
    golden = _load_golden_dataset()

    # Step 2: Ingest sample document
    logger.info("Ingesting sample document...")
    _ingest_sample_document(eval_settings)

    # Step 3: Query the RAG pipeline for each golden question
    logger.info("Querying RAG pipeline for %d questions...", len(golden))
    samples = []
    for i, item in enumerate(golden, 1):
        question = item["question"]
        answer, contexts = _query_rag(question, eval_settings)
        samples.append({
            "question": question,
            "ground_truth": item["ground_truth"],
            "ground_truth_contexts": item.get("ground_truth_contexts", []),
            "response": answer,
            "retrieved_contexts": contexts,
        })
        logger.info("  [%d/%d] %s", i, len(golden), question[:80])

    # Step 4: Run Ragas evaluation
    start = time.perf_counter()
    result = _run_ragas_evaluation(samples)
    duration = time.perf_counter() - start

    # Step 5: Print summary and save
    _print_summary(result)
    _save_results(result, samples, duration)

    # Cleanup
    tmp_dir.cleanup()
    logger.info("Evaluation complete.")


if __name__ == "__main__":
    main()
