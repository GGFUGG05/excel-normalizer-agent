"""Configuration for the Excel Normalizer Agent."""

import os

# LLM
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-haiku-4-5-20251001"

# Paths
INPUT_DIR = "input"
OUTPUT_DIR = "output"

# Code execution
EXECUTION_TIMEOUT = 60  # seconds
MAX_RETRIES = 3

# Analysis
MAX_SAMPLE_ROWS = 15
MAX_COLUMNS_TO_SHOW = 50
