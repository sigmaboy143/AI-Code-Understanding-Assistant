"""Unit tests for the code understanding API schemas."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    MAX_SOURCE_CODE_LENGTH,
    AnalysisMetadata,
    AnalysisType,
    CodeElement,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
    Dependency,
    DependencyAnalysis,
    DependencyKind,
    ErrorExplanation,
    ImprovementSuggestion,
    ProgrammingLanguage,
    Severity,
    StructureAnalysis,
)

SAMPLE_CODE = "def add(a, b):\n    return a + b\n"


# --------------------------------------------------------------------------
# CodeUnderstandingRequest
# --------------------------------------------------------------------------


def test_request_accepts_minimal_valid_payload():
    request = CodeUnderstandingRequest(source_code=SAMPLE_CODE, language="python")

    assert request.source_code == SAMPLE_CODE
    assert request.language is ProgrammingLanguage.PYTHON
    assert request.file_path is None
    assert request.question is None
    assert request.context is None
    assert request.analyses == list(AnalysisType)


def test_request_accepts_full_payload():
    request = CodeUnderstandingRequest(
        source_code=SAMPLE_CODE,
        language="typescript",
        file_path="src/math/add.ts",
        question="Why does this return a string here?",
        context="TypeError: a is not a function",
        analyses=[AnalysisType.EXPLANATION, AnalysisType.ERROR_EXPLANATION],
    )

    assert request.language is ProgrammingLanguage.TYPESCRIPT
    assert request.file_path == "src/math/add.ts"
    assert request.question == "Why does this return a string here?"
    assert request.context == "TypeError: a is not a function"
    assert request.analyses == [AnalysisType.EXPLANATION, AnalysisType.ERROR_EXPLANATION]


@pytest.mark.parametrize("missing", ["source_code", "language"])
def test_request_requires_source_code_and_language(missing):
    payload = {"source_code": SAMPLE_CODE, "language": "python"}
    del payload[missing]

    with pytest.raises(ValidationError) as excinfo:
        CodeUnderstandingRequest(**payload)

    assert missing in str(excinfo.value)


@pytest.mark.parametrize("source_code", ["", "   ", "\n\t "])
def test_request_rejects_blank_source_code(source_code):
    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(source_code=source_code, language="python")


def test_request_rejects_oversized_source_code():
    oversized = "a" * (MAX_SOURCE_CODE_LENGTH + 1)

    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(source_code=oversized, language="python")


def test_request_accepts_source_code_at_max_length():
    at_limit = "a" * MAX_SOURCE_CODE_LENGTH

    request = CodeUnderstandingRequest(source_code=at_limit, language="python")

    assert len(request.source_code) == MAX_SOURCE_CODE_LENGTH


@pytest.mark.parametrize("field", ["file_path", "question", "context"])
def test_request_rejects_blank_optional_text(field):
    payload = {"source_code": SAMPLE_CODE, "language": "python", field: "  "}

    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(**payload)


def test_request_rejects_unknown_language():
    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(source_code=SAMPLE_CODE, language="brainfuck")


def test_request_rejects_unknown_analysis_type():
    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(
            source_code=SAMPLE_CODE,
            language="python",
            analyses=["astrology"],
        )


def test_request_rejects_empty_analysis_list():
    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(
            source_code=SAMPLE_CODE,
            language="python",
            analyses=[],
        )


def test_request_deduplicates_analysis_types():
    request = CodeUnderstandingRequest(
        source_code=SAMPLE_CODE,
        language="python",
        analyses=[AnalysisType.STRUCTURE, AnalysisType.STRUCTURE, AnalysisType.IMPROVEMENTS],
    )

    assert request.analyses == [AnalysisType.STRUCTURE, AnalysisType.IMPROVEMENTS]


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CodeUnderstandingRequest(source_code=SAMPLE_CODE, language="python", prompt="typo")


def test_request_serialises_to_plain_json_values():
    payload = CodeUnderstandingRequest(
        source_code=SAMPLE_CODE,
        language="go",
        analyses=[AnalysisType.DEPENDENCIES],
    ).model_dump(mode="json")

    assert payload["language"] == "go"
    assert payload["analyses"] == ["dependencies"]


def test_request_generates_json_schema():
    schema = CodeUnderstandingRequest.model_json_schema()

    assert "source_code" in schema["properties"]
    assert "language" in schema["properties"]
    assert set(schema["required"]) == {"source_code", "language"}


# --------------------------------------------------------------------------
# CodeUnderstandingResponse
# --------------------------------------------------------------------------


def build_response(**overrides):
    metadata = AnalysisMetadata(
        language=ProgrammingLanguage.PYTHON,
        file_path="app/math.py",
        analyses=[AnalysisType.EXPLANATION],
        confidence=0.82,
    )
    payload = {
        "summary": "Adds two numbers.",
        "explanation": {"overview": "Returns the sum of both arguments."},
        "error_explanation": ErrorExplanation(
            message="TypeError: unsupported operand type(s)",
            explanation="One operand is not numeric.",
            likely_causes=["A string was passed in"],
            suggested_fixes=["Cast the value to int"],
        ),
        "structure": StructureAnalysis(
            summary="Single function.",
            elements=[CodeElement(name="add", kind="function", line_start=1, line_end=2)],
        ),
        "dependencies": DependencyAnalysis(
            dependencies=[Dependency(name="math", kind=DependencyKind.STANDARD_LIBRARY)],
        ),
        "improvements": [
            ImprovementSuggestion(
                title="Add type hints",
                description="Annotate the parameters as int.",
                severity=Severity.LOW,
                category="readability",
                line=1,
            )
        ],
        "metadata": metadata,
    }
    payload.update(overrides)
    return CodeUnderstandingResponse(**payload)


def test_response_accepts_full_result():
    response = build_response()

    assert response.summary == "Adds two numbers."
    assert response.explanation is not None
    assert response.explanation.overview == "Returns the sum of both arguments."
    assert response.error_explanation is not None
    assert response.error_explanation.suggested_fixes == ["Cast the value to int"]
    assert response.structure is not None
    assert response.structure.elements[0].kind == "function"
    assert response.dependencies is not None
    assert response.dependencies.dependencies[0].kind is DependencyKind.STANDARD_LIBRARY
    assert response.improvements[0].severity is Severity.LOW
    assert response.metadata.confidence == pytest.approx(0.82)


def test_response_requires_summary_and_metadata():
    with pytest.raises(ValidationError) as excinfo:
        CodeUnderstandingResponse()

    message = str(excinfo.value)
    assert "summary" in message
    assert "metadata" in message


def test_response_allows_summary_only_with_metadata():
    response = CodeUnderstandingResponse(
        summary="Adds two numbers.",
        metadata=AnalysisMetadata(language="python"),
    )

    assert response.explanation is None
    assert response.error_explanation is None
    assert response.structure is None
    assert response.dependencies is None
    assert response.improvements == []


def test_response_rejects_blank_summary():
    with pytest.raises(ValidationError):
        build_response(summary="   ")


def test_response_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        build_response(metadata=AnalysisMetadata(language="python", confidence=1.5))


def test_response_rejects_unknown_improvement_severity():
    with pytest.raises(ValidationError):
        build_response(
            improvements=[
                {
                    "title": "Add type hints",
                    "description": "Annotate the parameters as int.",
                    "severity": "catastrophic",
                }
            ]
        )


def test_response_rejects_improvement_without_title():
    with pytest.raises(ValidationError):
        build_response(improvements=[{"description": "Annotate the parameters as int."}])


def test_response_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        build_response(provider="openai")


def test_response_default_lists_are_not_shared():
    first = CodeUnderstandingResponse(
        summary="Adds two numbers.", metadata=AnalysisMetadata(language="python")
    )
    second = CodeUnderstandingResponse(
        summary="Adds two numbers.", metadata=AnalysisMetadata(language="python")
    )
    first.improvements.append(
        ImprovementSuggestion(title="Add type hints", description="Annotate parameters.")
    )

    assert second.improvements == []


def test_code_element_rejects_inverted_line_range():
    with pytest.raises(ValidationError):
        CodeElement(name="add", kind="function", line_start=10, line_end=2)


def test_code_element_rejects_zero_line_numbers():
    with pytest.raises(ValidationError):
        CodeElement(name="add", kind="function", line_start=0)


def test_response_generates_json_schema():
    schema = CodeUnderstandingResponse.model_json_schema()

    properties = schema["properties"]
    for field in (
        "summary",
        "explanation",
        "error_explanation",
        "structure",
        "dependencies",
        "improvements",
        "metadata",
    ):
        assert field in properties
    assert set(schema["required"]) == {"summary", "metadata"}
