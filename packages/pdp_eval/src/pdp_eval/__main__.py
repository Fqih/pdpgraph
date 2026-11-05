# SPDX-License-Identifier: Apache-2.0
"""`uv run python -m pdp_eval ...`: golden-set labeling CLI (M1.7)."""

import sys

from pdp_eval.cli import main

if __name__ == "__main__":
    sys.exit(main())
