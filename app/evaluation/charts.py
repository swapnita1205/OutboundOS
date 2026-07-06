from pathlib import Path

import matplotlib.pyplot as plt

from app.evaluation.models import EvaluationSummary, HistoricalRun


def generate_report_charts(
    summary: EvaluationSummary,
    history: list[HistoricalRun],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _save_metric_bar_chart(summary, output_dir / "metric_scores.png")
    _save_history_trend_chart(history, output_dir / "historical_trends.png")


def _save_metric_bar_chart(summary: EvaluationSummary, path: Path) -> None:
    labels = [
        "Research",
        "ICP",
        "Persona",
        "Pain Point",
        "Reviewer",
        "Similarity",
    ]
    values = [
        summary.research_accuracy,
        summary.icp_accuracy,
        summary.persona_accuracy,
        summary.pain_point_accuracy,
        summary.reviewer_agreement,
        summary.email_similarity,
    ]
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.bar(labels, values, color="#6366f1")
    axis.set_ylim(0, 1)
    axis.set_ylabel("Score")
    axis.set_title("Evaluation Metric Scores")
    axis.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _save_history_trend_chart(history: list[HistoricalRun], path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 8))
    if not history:
        for axis in axes:
            axis.text(0.5, 0.5, "No historical runs yet", ha="center", va="center")
            axis.set_axis_off()
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return

    x = list(range(1, len(history) + 1))
    axes[0].plot(x, [item.avg_latency_ms for item in history], marker="o", color="#22c55e")
    axes[0].set_title("Average Latency Trend")
    axes[0].set_ylabel("Latency (ms)")
    axes[0].grid(alpha=0.2)

    axes[1].plot(x, [item.avg_cost_usd for item in history], marker="o", color="#f59e0b")
    axes[1].set_title("Average Cost Trend")
    axes[1].set_ylabel("Cost (USD)")
    axes[1].set_xlabel("Run #")
    axes[1].grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
