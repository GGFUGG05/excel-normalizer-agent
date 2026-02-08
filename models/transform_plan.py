"""Pydantic models for the transformation plan and file profile."""

from __future__ import annotations
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# File profile – what the analyzer tool returns
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    sample_values: list[str] = Field(default_factory=list)


class FileProfile(BaseModel):
    """Structured summary of an Excel file for the LLM to reason about."""
    file_path: str
    sheet_name: str
    total_rows: int
    total_columns: int
    columns: list[ColumnInfo] = Field(default_factory=list)
    sample_rows: list[dict] = Field(
        default_factory=list,
        description="First N rows as list of dicts",
    )
    raw_header_rows: list[list[str]] = Field(
        default_factory=list,
        description="First few raw rows before any header inference, useful for detecting multi-row headers or group headers",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Observations: merged cells, blank rows, repeated headers, etc.",
    )


# ---------------------------------------------------------------------------
# Transformation plan – the core artifact
# ---------------------------------------------------------------------------

class TransformStep(BaseModel):
    """A single transformation step."""
    step: int = Field(description="Step number (1-based)")
    action: str = Field(
        description=(
            "Action identifier, e.g. 'detect_group_headers', 'rename_columns', "
            "'unpivot', 'split_column', 'cast_types', 'drop_rows', 'filter', "
            "'forward_fill_group', 'custom' (for anything non-standard)"
        )
    )
    description: str = Field(
        description="Human-readable explanation of what this step does and why"
    )
    params: dict = Field(
        default_factory=dict,
        description="Action-specific parameters",
    )


class TransformPlan(BaseModel):
    """The full transformation plan – source of truth & documentation."""
    source_description: str = Field(
        description="What the agent understood about the raw input file structure"
    )
    target_description: str = Field(
        description="What the agent understood about the desired output format"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Implicit decisions the agent made that the user should verify",
    )
    steps: list[TransformStep] = Field(
        default_factory=list,
        description="Ordered list of transformation steps",
    )


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    success: bool
    matched_columns: list[str] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)
    extra_columns: list[str] = Field(default_factory=list)
    row_count_expected: int | None = None
    row_count_actual: int | None = None
    dtype_mismatches: list[str] = Field(default_factory=list)
    sample_comparison: str = ""
    error_message: str = ""
