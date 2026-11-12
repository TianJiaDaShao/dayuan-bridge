"""Root-owned launchd entry point; ignores user Python paths and site modules."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dayuan.cli import main
raise SystemExit(main(['serve', '--system-service']))
