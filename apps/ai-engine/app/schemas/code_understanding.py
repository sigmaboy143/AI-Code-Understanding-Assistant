"""Typed request/response schemas for the Code Understanding API.

These models are the public contract of the service. They are deliberately
provider agnostic: nothing here references an LLM, RAG, embedding, or AST
implementation, so any backend can satisfy the contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Guard rails so a single request can never smuggle an unbounded payload.
MAX_SOURCE_CODE_LENGTH = 100_000
MAX_FILE_PATH_LENGTH = 1_024
MAX_QUESTION_LENGTH = 10_000
MAX_CONTEXT_LENGTH = 50_000


def _reject_blank(value: str) -> str:
    """Reject strings that carry no actual content."""
    if not value.strip():
        raise ValueError("must not be empty or whitespace only")
    return value


NonEmptyText = Annotated[str, AfterValidator(_reject_blank)]
"""A string that must contain at least one non-whitespace character."""


class ProgrammingLanguage(str, Enum):
    """Programming language of the submitted code."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    C = "c"
    CPP = "cpp"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    RUBY = "ruby"
    PHP = "php"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    SQL = "sql"
    SHELL = "shell"
    HTML = "html"
    CSS = "css"
    OTHER = "other"


class AnalysisType(str, Enum):
    """Analysis capabilities the engine can be asked to perform."""

    EXPLANATION = "explanation"
    ERROR_EXPLANATION = "error_explanation"
    STRUCTURE = "structure"
    DEPENDENCIES = "dependencies"
    IMPROVEMENTS = "improvements"


class Severity(str, Enum):
    """How important an improvement or impact is."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DependencyKind(str, Enum):
    """Origin of a dependency."""

    BUILTIN = "builtin"
    STANDARD_LIBRARY = "standard_library"
    INTERNAL = "internal"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class CodeSchema(BaseModel):
    """Base model for every code understanding schema."""

    model_config = ConfigDict(extra="forbid")


class CodeUnderstandingRequest(CodeSchema):
    """Payload used to submit code for analysis."""

    source_code: str = Field(
        max_length=MAX_SOURCE_CODE_LENGTH,
        description="Raw source code to analyse.",
    )
    language: ProgrammingLanguage = Field(description="Language of the source code.")
    file_path: str | None = Field(
        default=None,
        max_length=MAX_FILE_PATH_LENGTH,
        description="Optional repository relative filename or path.",
    )
    question: str | None = Field(
        default=None,
        max_length=MAX_QUESTION_LENGTH,
        description="Optional free-form request, e.g. 'why does this return None?'.",
    )
    context: str | None = Field(
        default=None,
        max_length=MAX_CONTEXT_LENGTH,
        description="Optional extra context: related code, logs, or error output.",
    )
    analyses: list[AnalysisType] = Field(
        default_factory=lambda: list(AnalysisType),
        min_length=1,
        description="Analyses to perform. Defaults to every supported analysis.",
    )

    @field_validator("source_code")
    @classmethod
    def _source_code_not_blank(cls, value: str) -> str:
        return _reject_blank(value)

    @field_validator("file_path", "question", "context")
    @classmethod
    def _optional_text_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _reject_blank(value)

    @field_validator("analyses")
    @classmethod
    def _analyses_unique(cls, value: list[AnalysisType]) -> list[AnalysisType]:
        return list(dict.fromkeys(value))


class CodeExplanation(CodeSchema):
    """Plain-language explanation of the submitted code."""

    overview: NonEmptyText = Field(description="Short, high-level description.")
    details: str | None = Field(default=None, description="Longer walkthrough.")


class ErrorExplanation(CodeSchema):
    """Explanation of a bug, error, or exception."""

    message: NonEmptyText = Field(description="The error or exception being explained.")
    explanation: NonEmptyText = Field(description="What the error actually means.")
    likely_causes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)


class CodeElement(CodeSchema):
    """A named structural element found in the submitted code."""

    name: NonEmptyText = Field(description="Element name, e.g. function or class name.")
    kind: str = Field(description="Element kind, e.g. function, class, method.")
    summary: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _line_range_ordered(self) -> CodeElement:
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class StructureAnalysis(CodeSchema):
    """Outline of the code structure."""

    summary: str | None = None
    elements: list[CodeElement] = Field(default_factory=list)


class Dependency(CodeSchema):
    """A library, module, or symbol the code depends on."""

    name: NonEmptyText
    kind: DependencyKind = DependencyKind.UNKNOWN
    version: str | None = None
    description: str | None = None


class ImpactedComponent(CodeSchema):
    """A component affected by a dependency or a change."""

    name: NonEmptyText
    reason: str | None = None
    risk: Severity = Severity.INFO


class DependencyAnalysis(CodeSchema):
    """Dependencies of the code and the components they impact."""

    summary: str | None = None
    dependencies: list[Dependency] = Field(default_factory=list)
    impacts: list[ImpactedComponent] = Field(default_factory=list)


class ImprovementSuggestion(CodeSchema):
    """A concrete improvement proposed for the code."""

    title: NonEmptyText
    description: NonEmptyText
    severity: Severity = Severity.MEDIUM
    category: str | None = Field(default=None, description="e.g. performance, security.")
    line: int | None = Field(default=None, ge=1)


class AnalysisMetadata(CodeSchema):
    """Context describing what was analysed and how confident the result is."""

    language: ProgrammingLanguage
    file_path: str | None = None
    analyses: list[AnalysisType] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CodeUnderstandingResponse(CodeSchema):
    """Result of a code understanding analysis."""

    summary: NonEmptyText = Field(description="Overall plain-language summary.")
    explanation: CodeExplanation | None = None
    error_explanation: ErrorExplanation | None = None
    structure: StructureAnalysis | None = None
    dependencies: DependencyAnalysis | None = None
    improvements: list[ImprovementSuggestion] = Field(default_factory=list)
    metadata: AnalysisMetadata
