"""Make `import app` work when pytest runs from the repository root, without a real key."""
import os
import sys
from pathlib import Path

os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
