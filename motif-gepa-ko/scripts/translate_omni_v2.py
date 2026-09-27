"""Translate the fixed v2 training solutions using INFRON_API_KEY from .env."""

import argparse
from pathlib import Path

from motif_gepa_ko.translation import translate_train


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-records", type=int, default=0, help="0 translates every remaining row")
    parser.add_argument("--batch-size", type=int, default=2)
    args = parser.parse_args()
    result = translate_train(
        ROOT / "data/omni_v2/train.jsonl",
        ROOT / "data/omni_v2/train_solutions_ko.jsonl",
        max_records=args.max_records,
        batch_size=args.batch_size,
    )
    print(result)


if __name__ == "__main__":
    main()
