"""Launch Laser Photo Studio from Windows Start or with an optional picture or G-code path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lps.app import main  # noqa: E402

main(sys.argv[1:])
