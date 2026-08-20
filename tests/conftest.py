import sys
from pathlib import Path

# Make the repo importable as `monoamine_calc` without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
