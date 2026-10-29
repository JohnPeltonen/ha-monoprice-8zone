import sys
from pathlib import Path

# The package's __init__.py imports homeassistant from Phase 2 on, so tests load amp.py on its own.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "custom_components" / "monoprice_8zone"))
