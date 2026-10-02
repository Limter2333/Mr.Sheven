"""LLM module: structured extraction and comparison."""

from pipeline.llm.extract import extract_reviews
from pipeline.llm.compare import compare_reviews

__all__ = ["extract_reviews", "compare_reviews"]