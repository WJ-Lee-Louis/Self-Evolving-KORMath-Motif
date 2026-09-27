"""Build the self-contained Omni v2 split without numbered-problem dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path

from prepare_omni_v2 import ROOT, build


OUTPUT = ROOT / "data" / "omni_v2_clean"
# These eight English questions require other numbered problems that the
# independent benchmark example does not include.
EXCLUDED_DEPENDENT_ROWS = frozenset({134, 143, 153, 154, 287, 639, 717, 930})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build(excluded_dependent_rows=EXCLUDED_DEPENDENT_ROWS)
    if not args.check:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = OUTPUT / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit(f"Missing or changed: {path}")
        elif path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Refusing to overwrite changed file: {path}")
        elif not path.exists():
            path.write_bytes(content)
    print("omni_v2_clean: train=1000, val=50, test_id=760; deterministic files verified")


if __name__ == "__main__":
    main()
