"""Allow CLI to be executed as a module with python -m flextaxd.cli."""

import sys
from .main import main

if __name__ == "__main__":
    sys.exit(main())