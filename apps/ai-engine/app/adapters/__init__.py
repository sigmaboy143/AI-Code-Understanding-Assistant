"""Adapters that wrap internal subsystems behind stable interfaces.

Each adapter in this package implements an interface declared alongside it and
composes existing subsystems rather than reimplementing them.  Adapters hold no
corpus and add no new infrastructure.

Public API
----------
- ``IRetrievalAdapter``         — abstract retrieval contract
- ``RepositoryRetrievalAdapter``— concrete filesystem-repository implementation
- ``RetrievalResult``           — typed result returned by ``search``
"""

from .iretrieval_adapter import (
    IRetrievalAdapter,
    RepositoryRetrievalAdapter,
    RetrievalResult,
    expand_dependencies,
)

__all__ = [
    "IRetrievalAdapter",
    "RepositoryRetrievalAdapter",
    "RetrievalResult",
    "expand_dependencies",
]