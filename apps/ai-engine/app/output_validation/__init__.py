"""Output validation package (Task 10).

Public API
----------
- ``ValidationError``  — raised when provider output cannot be normalised
- ``validate_llm_response``  — validate + normalise a raw ``LLMResponse``
"""

from app.output_validation.validator import (
    OutputValidationError,
    validate_llm_response,
)

__all__ = [
    "OutputValidationError",
    "validate_llm_response",
]
