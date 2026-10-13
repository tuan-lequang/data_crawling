"""Input validation. Raises ValueError with a readable message."""
import re

from config import (MAX_KEYWORD_LENGTH, MAX_PRODUCTS, MAX_REVIEWS_PER_PRODUCT,
                    REVIEW_COLUMNS, SORT_OPTIONS, STANDARD_COLUMNS)

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



def validate_review_count(count) -> int:
    """Validate a positive review sample size; zero must never reach a provider."""
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("Number of reviews must be a whole number.")
    if not 1 <= count <= MAX_REVIEWS_PER_PRODUCT:
        raise ValueError(f"Number of reviews must be between 1 and {MAX_REVIEWS_PER_PRODUCT}.")
    return count


def validate_selected_columns(columns, allowed=None, label="output") -> list[str]:
    """Validate selected field names while preserving the allowed schema order."""
    if columns is None or isinstance(columns, (str, bytes)):
        raise ValueError(f"Please select at least one {label} field.")
    selected = list(columns)
    if not selected:
        raise ValueError(f"Please select at least one {label} field.")
    allowed_columns = list(allowed or STANDARD_COLUMNS)
    if any(column not in allowed_columns for column in selected):
        raise ValueError(f"The selected {label} fields contain an unsupported column.")
    return [column for column in allowed_columns if column in set(selected)]
