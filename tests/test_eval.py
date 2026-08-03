"""Tests for evaluation dataset and evaluation helper functions."""

import json
from pathlib import Path

from eval.run_evaluation import (
    GOLDEN_DATASET,
    SAMPLE_DOCUMENT,
    _load_golden_dataset,
    _safe_float,
)


def test_sample_document_exists_and_has_content() -> None:
    assert SAMPLE_DOCUMENT.exists(), f"Sample document missing at {SAMPLE_DOCUMENT}"
    content = SAMPLE_DOCUMENT.read_text(encoding="utf-8")
    assert len(content) > 500
    assert "Acme Corporation" in content
    assert "Annual Leave Policy" in content


def test_golden_dataset_exists_and_loads() -> None:
    assert GOLDEN_DATASET.exists(), f"Golden dataset missing at {GOLDEN_DATASET}"
    dataset = _load_golden_dataset()
    assert isinstance(dataset, list)
    assert len(dataset) >= 20


def test_golden_dataset_schema_and_types() -> None:
    dataset = _load_golden_dataset()
    for index, item in enumerate(dataset):
        assert "question" in item, f"Sample #{index} missing 'question'"
        assert isinstance(item["question"], str) and len(item["question"].strip()) > 0
        assert "ground_truth" in item, f"Sample #{index} missing 'ground_truth'"
        assert isinstance(item["ground_truth"], str) and len(item["ground_truth"].strip()) > 0
        assert "ground_truth_contexts" in item, f"Sample #{index} missing 'ground_truth_contexts'"
        assert isinstance(item["ground_truth_contexts"], list)


def test_golden_contexts_correspond_to_document_text() -> None:
    doc_text = SAMPLE_DOCUMENT.read_text(encoding="utf-8")
    dataset = _load_golden_dataset()

    for item in dataset:
        for context in item["ground_truth_contexts"]:
            # Normalize whitespace to avoid newline formatting mismatches
            normalized_context = " ".join(context.split())
            normalized_doc = " ".join(doc_text.split())
            assert normalized_context in normalized_doc, (
                f"Context excerpt '{context[:60]}...' not found in document"
            )


def test_safe_float_helper() -> None:
    assert _safe_float(None) is None
    assert _safe_float(float("nan")) is None
    assert _safe_float(0.85678) == 0.8568
    assert _safe_float(1) == 1.0
    assert _safe_float("invalid") is None
