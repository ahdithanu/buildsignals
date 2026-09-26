"""Contract tests for the pure evidence rubric and inclusive threshold gates."""
from math import nextafter

import pytest

from app.schemas.evaluation import Citation, EvalOutput, Evidence, ExpectedOutput, Thresholds
from app.services.eval_scoring import SCORER_VERSION, result_passes, score_output


@pytest.fixture
def context():
    return [Evidence(id="source-1", text="The project has 12 homes. Approval is pending.")]


def test_valid_citation_and_complete_rubric(context):
    metrics = score_output(
        EvalOutput(text="12 homes; approval is pending.", score=75,
                   citations=[Citation(source_id="source-1", quote="12 homes")]),
        ExpectedOutput(required_phrases=["12 homes", "approval is pending"],
                       required_citation_ids=["source-1"], expected_score=75,
                       forbidden_phrases=["guaranteed approval"]),
        context,
    )
    assert SCORER_VERSION == "evidence-rubric-v1"
    assert metrics == {
        "citation_accuracy": 1.0, "hallucination_risk": 0.0,
        "factual_coverage": 1.0, "quality": 1.0, "rule_compliance": 1.0,
    }
    assert all(type(value) is float for value in metrics.values())
    assert result_passes(metrics, Thresholds())


@pytest.mark.parametrize("citations", [
    [], [Citation(source_id="invented")],
    [Citation(source_id="source-1", quote="Approval is granted")],
    [Citation(source_id="SOURCE-1")],
])
def test_missing_invented_wrong_quote_and_case_sensitive_ids(context, citations):
    metrics = score_output(
        EvalOutput(text="12 homes", citations=citations),
        ExpectedOutput(required_phrases=["12 homes"], required_citation_ids=["source-1"]),
        context,
    )
    assert metrics["citation_accuracy"] == 0.0
    assert metrics["hallucination_risk"] == 1.0
    assert metrics["factual_coverage"] == 0.5
    assert metrics["quality"] == 0.0
    assert not result_passes(metrics, Thresholds())


@pytest.mark.parametrize("citations", [[], [Citation(source_id="source-1")]])
def test_no_evidence_is_not_perfect_citation_accuracy(citations):
    metrics = score_output(EvalOutput(text="12 homes", citations=citations),
                           ExpectedOutput(required_phrases=["12 homes"]), [])
    assert metrics["citation_accuracy"] == 0.0
    assert metrics["hallucination_risk"] == 1.0


@pytest.mark.parametrize("quote", ["", "  \t\n ", "  12\t HOMES.\n Approval  IS pending. "])
def test_optional_quotes_and_case_whitespace_normalization(context, quote):
    metrics = score_output(
        EvalOutput(text="  12\n HOMES; Approval\tIS  Pending. ",
                   citations=[Citation(source_id="source-1", quote=quote)]),
        ExpectedOutput(required_phrases=[" 12\t homes ", "APPROVAL  is\npending"]),
        context,
    )
    assert metrics["quality"] == 1.0


def test_quote_requires_contiguous_substring_not_bag_of_words(context):
    metrics = score_output(
        EvalOutput(text="12 homes", citations=[Citation(source_id="source-1", quote="12 Approval")]),
        ExpectedOutput(required_phrases=["12 homes"]), context,
    )
    assert metrics["citation_accuracy"] == 0.0


def test_duplicate_valid_reference_cannot_wash_invalid_reference(context):
    expected = ExpectedOutput(required_phrases=["12 homes"])
    citations = [Citation(source_id="source-1", quote="12 homes"), Citation(source_id="invented")]
    baseline = score_output(EvalOutput(text="12 homes", citations=citations), expected, context)
    repeated = score_output(
        EvalOutput(text="12 homes", citations=citations + [citations[0]] * 90), expected, context,
    )
    assert baseline == repeated
    assert repeated["citation_accuracy"] == 0.5
    assert repeated["hallucination_risk"] == 0.5


def test_varied_valid_quotes_same_source_do_not_inflate_accuracy(context):
    metrics = score_output(
        EvalOutput(text="12 homes", citations=[
            Citation(source_id="source-1", quote="12 homes"),
            Citation(source_id="source-1", quote="Approval is pending"),
            Citation(source_id="invented"),
        ]), ExpectedOutput(required_phrases=["12 homes"]), context,
    )
    assert metrics["citation_accuracy"] == 0.5


@pytest.mark.parametrize("reverse", [False, True])
def test_bad_quote_cannot_be_hidden_by_valid_same_source_citation(context, reverse):
    citations = [Citation(source_id="source-1"), Citation(source_id="source-1", quote="invented")]
    metrics = score_output(
        EvalOutput(text="12 homes", citations=citations[::-1] if reverse else citations),
        ExpectedOutput(required_citation_ids=["source-1"]), context,
    )
    assert metrics["citation_accuracy"] == metrics["factual_coverage"] == 0.0


def test_required_reference_must_be_cited_not_merely_available(context):
    context.append(Evidence(id="source-2", text="Another source"))
    metrics = score_output(
        EvalOutput(text="12 homes", citations=[Citation(source_id="source-1")]),
        ExpectedOutput(required_citation_ids=["source-1", "source-2"]), context,
    )
    assert metrics["citation_accuracy"] == 1.0
    assert metrics["factual_coverage"] == metrics["hallucination_risk"] == 0.5
    assert metrics["quality"] == 0.5


@pytest.mark.parametrize("actual, expected", [(0, 0), (100, 100), (75.5, 75.5), (75, 75.0)])
def test_numeric_agreement_including_zero_and_boundaries(context, actual, expected):
    metrics = score_output(
        EvalOutput(text="Score", score=actual, citations=[Citation(source_id="source-1")]),
        ExpectedOutput(expected_score=expected), context,
    )
    assert metrics["quality"] == 1.0


@pytest.mark.parametrize("score", [None, 0, 74.999999, 76])
def test_numeric_mismatch_or_missing_score(context, score):
    metrics = score_output(
        EvalOutput(text="12 homes", score=score, citations=[Citation(source_id="source-1")]),
        ExpectedOutput(required_phrases=["12 homes", "pending"],
                       required_citation_ids=["source-1"], expected_score=75), context,
    )
    assert metrics["factual_coverage"] == 0.5
    assert metrics["rule_compliance"] == metrics["quality"] == 0.0
    assert metrics["hallucination_risk"] == 1.0


def test_unconfigured_score_does_not_affect_metrics(context):
    output = EvalOutput(text="12 homes", citations=[Citation(source_id="source-1")])
    expected = ExpectedOutput(required_phrases=["12 homes"])
    assert score_output(output, expected, context) == score_output(
        output.model_copy(update={"score": 99}), expected, context,
    )


def test_forbidden_phrases_are_normalized_and_rule_checks_averaged(context):
    metrics = score_output(
        EvalOutput(text="12 homes with GUARANTEED\n APPROVAL", score=75,
                   citations=[Citation(source_id="source-1")]),
        ExpectedOutput(required_phrases=["12 homes"], expected_score=75,
                       forbidden_phrases=[" guaranteed\tapproval ", "risk free"]), context,
    )
    assert metrics["factual_coverage"] == 1.0
    assert metrics["rule_compliance"] == pytest.approx(2 / 3)
    assert metrics["quality"] == metrics["rule_compliance"]
    assert metrics["hallucination_risk"] == 0.5


def test_literal_checks_do_not_claim_semantic_entailment(context):
    metrics = score_output(
        EvalOutput(text="12 homes are already approved", citations=[Citation(source_id="source-1")]),
        ExpectedOutput(required_phrases=["12 homes"]), context,
    )
    # The unsupported assertion is invisible to this deliberately lexical rubric.
    assert metrics["hallucination_risk"] == 0.0


def test_pure_deterministic_and_bounded(context):
    output = EvalOutput(text="12 homes", citations=[Citation(source_id="source-1")])
    expected = ExpectedOutput(required_phrases=["12 homes", "missing"])
    before = (output.model_dump(), expected.model_dump(), [item.model_dump() for item in context])
    metrics = score_output(output, expected, context)
    assert score_output(output, expected, context) == metrics
    assert all(0.0 <= value <= 1.0 for value in metrics.values())
    assert before == (output.model_dump(), expected.model_dump(), [item.model_dump() for item in context])


@pytest.mark.parametrize("boundary", [0.0, 0.5, 1.0])
def test_exact_thresholds_pass(boundary):
    metrics = dict.fromkeys(
        ["citation_accuracy", "hallucination_risk", "factual_coverage", "quality", "rule_compliance"],
        boundary,
    )
    assert result_passes(metrics, Thresholds(
        minimum_quality=boundary, minimum_citation_accuracy=boundary,
        minimum_factual_coverage=boundary, maximum_hallucination_risk=boundary,
    ))


@pytest.mark.parametrize("metric,direction", [
    ("quality", 0.0), ("citation_accuracy", 0.0),
    ("factual_coverage", 0.0), ("hallucination_risk", 1.0),
])
def test_one_float_step_outside_any_threshold_fails(metric, direction):
    metrics = dict.fromkeys(
        ["citation_accuracy", "hallucination_risk", "factual_coverage", "quality", "rule_compliance"],
        0.5,
    )
    metrics[metric] = nextafter(0.5, direction)
    assert not result_passes(metrics, Thresholds(
        minimum_quality=0.5, minimum_citation_accuracy=0.5,
        minimum_factual_coverage=0.5, maximum_hallucination_risk=0.5,
    ))


@pytest.mark.parametrize("metric", [
    "quality", "citation_accuracy", "factual_coverage", "hallucination_risk", "rule_compliance",
])
@pytest.mark.parametrize("bad_value", [None, float("nan"), float("inf"), -0.01, 1.01])
def test_missing_nonfinite_and_out_of_range_metrics_fail_closed(metric, bad_value):
    metrics = dict(citation_accuracy=1.0, factual_coverage=1.0, quality=1.0,
                   rule_compliance=1.0, hallucination_risk=0.0)
    if bad_value is None:
        del metrics[metric]
    else:
        metrics[metric] = bad_value
    assert not result_passes(metrics, Thresholds())
