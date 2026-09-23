"""Pure deterministic rubric checks, not a semantic entailment evaluator.

Substring matches cannot establish factual truth or detect all hallucinations.
The risk metric is only a proxy for citation, forbidden-text, and score failures.
"""
from __future__ import annotations

from math import isfinite

from app.schemas.evaluation import EvalOutput, Evidence, ExpectedOutput, Thresholds

SCORER_VERSION = "evidence-rubric-v1"


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def score_output(
    output: EvalOutput, expected: ExpectedOutput, context: list[Evidence]
) -> dict[str, float]:
    """Return five bounded metrics without modifying inputs or performing I/O.

    Source IDs are opaque and case-sensitive. Each cited ID counts once; every
    quote supplied for it must be valid, so repeated or varied valid quotes
    cannot dilute a bad reference. An empty quote means no quote was supplied.
    Numeric agreement is exact equality (no rounding or implicit tolerance).
    """
    answer = _normalize(output.text)
    evidence = {item.id: _normalize(item.text) for item in context}
    references: dict[str, bool] = {}
    for citation in output.citations:
        quote = _normalize(citation.quote)
        valid = citation.source_id in evidence and (
            not quote or quote in evidence[citation.source_id]
        )
        references[citation.source_id] = references.get(citation.source_id, True) and valid

    valid_ids = {source_id for source_id, valid in references.items() if valid}
    citation_accuracy = len(valid_ids) / len(references) if references else 0.0
    score_matches = expected.expected_score is None or output.score == expected.expected_score

    # Every configured required phrase, citation ID, and numeric score is one
    # equally weighted coverage check. The schema guarantees a nonempty rubric.
    coverage_checks = [_normalize(phrase) in answer for phrase in expected.required_phrases]
    coverage_checks.extend(source_id in valid_ids for source_id in expected.required_citation_ids)
    if expected.expected_score is not None:
        coverage_checks.append(score_matches)
    factual_coverage = sum(coverage_checks) / len(coverage_checks)

    forbidden_matches = [_normalize(phrase) in answer for phrase in expected.forbidden_phrases]
    rule_checks = [not matched for matched in forbidden_matches]
    if expected.expected_score is not None:
        rule_checks.append(score_matches)
    rule_compliance = sum(rule_checks) / len(rule_checks) if rule_checks else 1.0

    required_ids = set(expected.required_citation_ids)
    missing_required_ratio = (
        len(required_ids - valid_ids) / len(required_ids) if required_ids else 0.0
    )
    forbidden_ratio = (
        sum(forbidden_matches) / len(forbidden_matches) if forbidden_matches else 0.0
    )
    # Missing citations/evidence fail closed. Required references missing from
    # the valid set also contribute, even if every supplied reference is valid.
    invalid_ratio = (len(references) - len(valid_ids)) / len(references) if references else 1.0
    citation_risk = max(invalid_ratio, missing_required_ratio)
    hallucination_risk = max(citation_risk, forbidden_ratio, float(not score_matches))

    # Weakest-link quality: a strong component cannot compensate for a failed
    # citation, coverage, or rule component.
    quality = min(citation_accuracy, factual_coverage, rule_compliance)
    return {
        "citation_accuracy": float(citation_accuracy),
        "hallucination_risk": float(hallucination_risk),
        "factual_coverage": float(factual_coverage),
        "quality": float(quality),
        "rule_compliance": float(rule_compliance),
    }


def result_passes(metrics: dict[str, float], thresholds: Thresholds) -> bool:
    """Apply inclusive boundaries; incomplete or nonfinite metrics fail closed.

    Critical-case policy belongs to the caller. Rule compliance has no separate
    threshold in the schema and is incorporated into quality by score_output.
    """
    for name in (
        "citation_accuracy", "hallucination_risk", "factual_coverage", "quality", "rule_compliance"
    ):
        value = metrics.get(name)
        if value is None or not isfinite(value) or not 0.0 <= value <= 1.0:
            return False
    return (
        metrics["quality"] >= thresholds.minimum_quality
        and metrics["citation_accuracy"] >= thresholds.minimum_citation_accuracy
        and metrics["factual_coverage"] >= thresholds.minimum_factual_coverage
        and metrics["hallucination_risk"] <= thresholds.maximum_hallucination_risk
    )
