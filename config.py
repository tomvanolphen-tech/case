import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

MODEL_NAME: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
TENANTS_DIR: Path = BASE_DIR / "tenants"
RUNS_DIR: Path = BASE_DIR / "runs"
SAMPLES_DIR: Path = BASE_DIR / "samples"

DEFAULT_CONFIDENCE_THRESHOLD: float = 0.85
FEW_SHOT_EXAMPLES_COUNT: int = 3
