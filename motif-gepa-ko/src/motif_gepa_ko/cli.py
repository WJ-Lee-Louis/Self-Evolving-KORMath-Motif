"""Local command line for bounded GEPA experiments and held-out evaluation."""

import argparse
from pathlib import Path

from motif_gepa_ko.artifacts import audit_saved_run
from motif_gepa_ko.experiment import evaluate_run, optimize_run
from motif_gepa_ko.settings import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Motif 3 한국어 GEPA 실험")
    sub = parser.add_subparsers(dest="command", required=True)
    optimize = sub.add_parser("optimize")
    optimize.add_argument("--run-id", required=True)
    optimize.add_argument("--max-metric-calls", type=int, default=180)
    optimize.add_argument("--max-api-calls", type=int, default=250)
    optimize.add_argument("--minibatch-size", type=int, default=3)
    optimize.add_argument("--dataset", choices=("hrm8k_v1", "omni_v1"), default="hrm8k_v1")
    optimize.add_argument(
        "--batch-sampling", choices=("auto", "epoch_shuffled", "omni_difficulty_1_3_1"),
        default="auto",
    )
    optimize.add_argument("--seed", type=int, default=0)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--run-id", required=True)
    evaluate.add_argument("--dataset", choices=("hrm8k_v1", "omni_v1"), default="hrm8k_v1")
    evaluate.add_argument(
        "--split", required=True,
        choices=("test_id", "test_ood_math_l1_l2", "test_ood_math_l3_l5"),
    )
    evaluate.add_argument("--limit", type=int, default=20, help="0이면 전체 분할")
    evaluate.add_argument("--max-api-calls", type=int, default=100)
    audit = sub.add_parser("audit", help="저장된 실험 기록을 API 호출 없이 재검사")
    audit.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    runs_dir = PROJECT_ROOT / "runs"
    if args.command == "optimize":
        summary = optimize_run(
            data_dir=PROJECT_ROOT / "data" / args.dataset,
            prompts_dir=PROJECT_ROOT / "prompts",
            runs_dir=runs_dir,
            run_id=args.run_id,
            max_metric_calls=args.max_metric_calls,
            max_api_calls=args.max_api_calls,
            minibatch_size=args.minibatch_size,
            seed=args.seed,
            batch_sampling=args.batch_sampling,
        )
    elif args.command == "evaluate":
        summary = evaluate_run(
            data_dir=PROJECT_ROOT / "data" / args.dataset,
            runs_dir=runs_dir,
            run_id=args.run_id,
            split=args.split,
            limit=args.limit,
            max_api_calls=args.max_api_calls,
        )
    else:
        summary = audit_saved_run(args.run_dir)
    for key, value in summary.items():
        print(f"{key}: {value}")
    if args.command == "audit" and not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
