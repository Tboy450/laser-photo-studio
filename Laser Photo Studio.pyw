"""Double-click to start Laser Photo Studio (or drag a picture / .nc file onto its desktop icon)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lps.app import main  # noqa: E402

main(sys.argv[1:])
