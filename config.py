import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

MODEL_NAME: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
TENANTS_DIR: Path = BASE_DIR / "tenants"
RUNS_DIR: Path = BASE_DIR / "runs"
SAMPLES_DIR: Path = BASE_DIR / "samples"

DEFAULT_CONFIDENCE_THRESHOLD: float = 0.85
FEW_SHOT_EXAMPLES_COUNT: int = 3

# Bookkeeping API
BOOKKEEPING_ENV: str = os.getenv("BOOKKEEPING_ENV", "test")
BOOKKEEPING_API_URL_TEST: str = os.getenv("BOOKKEEPING_API_URL_TEST", "https://api.boekhouding.test/v1")
BOOKKEEPING_API_URL_PROD: str = os.getenv("BOOKKEEPING_API_URL_PROD", "https://api.boekhouding.nl/v1")


def bookkeeping_api_url(env: str | None = None) -> str:
    target = env or BOOKKEEPING_ENV
    if target == "prod":
        return BOOKKEEPING_API_URL_PROD
    return BOOKKEEPING_API_URL_TEST
