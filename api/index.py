import sys
from pathlib import Path

SOURCE_ROOT = str(Path(__file__).resolve().parents[1] / "src")
if SOURCE_ROOT not in sys.path:
    sys.path.insert(0, SOURCE_ROOT)

from mongodb_vector_test_ui.api.fastapi import app

__all__ = ["app"]
