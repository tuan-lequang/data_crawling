"""Input validation. Raises ValueError with a readable message."""
import re

from config import MAX_KEYWORD_LENGTH, MAX_PRODUCTS, SORT_OPTIONS

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def validate_keyword(keyword) -> str:
    if not isinstance(keyword, str):
        raise ValueError("Please enter a keyword.")
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", keyword).split())
    if not cleaned:
        raise ValueError("Please enter a keyword.")
    if len(cleaned) > MAX_KEYWORD_LENGTH:
        raise ValueError(f"Keyword is too long (max {MAX_KEYWORD_LENGTH} characters).")
    return cleaned


def validate_limit(limit) -> int:
    # bool is a subclass of int; reject it explicitly
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("Number of products must be a whole number.")
    if not 1 <= limit <= MAX_PRODUCTS:
        raise ValueError(f"Number of products must be between 1 and {MAX_PRODUCTS}.")
    return limit


def validate_sort(sort) -> str:
    if sort not in SORT_OPTIONS.values():
        raise ValueError("Unknown sort option.")
    return sort
