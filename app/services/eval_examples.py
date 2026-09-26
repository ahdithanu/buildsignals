"""Synthetic golden cases, explicitly marked as captured fixtures rather than live AI."""

from app.schemas.evaluation import DatasetCreate


def example_datasets() -> list[DatasetCreate]:
    definitions = [
        (
            "copilot_answer",
            "Which project needs follow-up?",
            "Example Cedar project has an issued grading permit. Verify the construction schedule.",
            ["issued grading permit", "Verify the construction schedule"],
        ),
        (
            "opportunity_memo",
            "Draft a memo.",
            "Example Cedar project: issued grading permit. Ownership and financing are unknown; request verification.",
            ["issued grading permit", "financing are unknown"],
        ),
        (
            "multi_agent_research",
            "Combine permit and risk research.",
            "Permit agent: Example Cedar has an issued grading permit. Risk agent: financing is unknown. Coordinator: verify financing before recommending action.",
            ["issued grading permit", "financing is unknown", "verify financing"],
        ),
        (
            "score_explanation",
            "Explain the recorded score.",
            "Example Cedar scores 40. The fixture rubric awards 10 for asking price, 20 for price per square foot, and 10 for year built.",
            ["10 for asking price", "20 for price per square foot", "10 for year built"],
        ),
    ]
    datasets = []
    for workflow, question, answer, phrases in definitions:
        evidence = "Example Cedar has an issued grading permit. Ownership and financing are unknown. Fixture score: 40; asking price: 10; price per square foot: 20; year built: 10."
        output = {
            "text": answer,
            "citations": [{"source_id": "fixture:cedar", "quote": "Example Cedar"}],
        }
        expected = {
            "required_phrases": phrases,
            "required_citation_ids": ["fixture:cedar"],
            "forbidden_phrases": ["guaranteed returns"],
        }
        if workflow == "score_explanation":
            output["score"] = 40
            expected["expected_score"] = 40
        datasets.append(
            DatasetCreate.model_validate(
                {
                    "name": f"Example: {workflow}",
                    "description": "Synthetic example for learning the eval runner. A passing fixture is not a production quality certification.",
                    "workflow": workflow,
                    "cases": [
                        {
                            "name": "Evidence-grounded response",
                            "input_json": {"question": question, "example_output": output},
                            "expected_output": expected,
                            "retrieved_context": [{"id": "fixture:cedar", "text": evidence}],
                            "critical": True,
                        }
                    ],
                }
            )
        )
    return datasets
