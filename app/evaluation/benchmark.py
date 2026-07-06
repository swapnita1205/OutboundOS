import argparse
import asyncio
from time import perf_counter

from app.evaluation.runner import EvaluationRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark OutboundOS workflow")
    parser.add_argument("--dataset-size", type=int, default=50)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=3)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    durations: list[float] = []
    for _ in range(args.rounds):
        started = perf_counter()
        runner = EvaluationRunner(
            dataset_size=args.dataset_size,
            max_concurrency=args.max_concurrency,
        )
        await runner.run()
        durations.append(perf_counter() - started)

    avg = sum(durations) / len(durations)
    print(
        {
            "benchmark_rounds": args.rounds,
            "dataset_size": args.dataset_size,
            "avg_duration_sec": round(avg, 4),
            "min_duration_sec": round(min(durations), 4),
            "max_duration_sec": round(max(durations), 4),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
