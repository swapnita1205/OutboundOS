PYTHON ?= python3

.PHONY: install run worker test lint typecheck format check precommit benchmark eval

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run arq app.workers.background.WorkerSettings

eval:
	uv run python -m app.evaluation.run --dataset-size 100

eval-outboundbench:
	uv run python -m app.evaluation.run \
		--dataset data/human_ground_truth/outboundbench_human.csv \
		--dataset-size 100 \
		--max-concurrency 2 \
		--quality-threshold 0.75

publish-benchmark:
	uv run python -m app.evaluation.publish_benchmark \
		app/evaluation/history/$(RUN)/summary.json

benchmark:
	uv run python -m app.evaluation.benchmark --dataset-size 100 --rounds 3

outboundbench-report:
	uv run python -m app.evaluation.dataset_quality_report --input data/human_ground_truth/outboundbench_human.csv

human-ground-truth:
	uv run python -m app.dataset.finalize_human_ground_truth

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

format:
	uv run ruff format .

check: lint typecheck test

precommit:
	uv run pre-commit run --all-files
