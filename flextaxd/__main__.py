"""Allow FlexTaxD to be executed as a module with python -m flextaxd."""

import sys
from flextaxd.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
