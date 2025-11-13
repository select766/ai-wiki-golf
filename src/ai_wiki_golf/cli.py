from __future__ import annotations

import typer

from .evaluation import evaluate_books, summarize_evaluation_results
from .experiment import run_experiment
from .visualize import launch_dashboard

app = typer.Typer(help="Wikipediaゴルフ自動プレイツール")


@app.command()
def run(experiment_dir: str = typer.Argument(..., help="Experiment directory")) -> None:
    """Run an experiment loop."""
    run_experiment(experiment_dir)


@app.command()
def evaluate(experiment_dir: str = typer.Argument(..., help="Experiment directory")) -> None:
    """Evaluate saved books on the predefined dataset."""
    evaluate_books(experiment_dir)


@app.command(name="eval-stats")
def eval_stats(experiment_dir: str = typer.Argument(..., help="Experiment directory")) -> None:
    """Show average success rate for each evaluated book."""

    stats = summarize_evaluation_results(experiment_dir)
    if not stats:
        typer.echo("No evaluation logs found. Please run 'ai-wiki-golf evaluate <experiment_dir>' first.")
        raise typer.Exit(code=1)

    header = f"{'Book':>6} {'Success':>8} {'Attempts':>10} {'Success Rate':>15}"
    typer.echo(header)
    typer.echo("-" * len(header))

    total_success = 0
    total_runs = 0
    for entry in stats:
        rate_pct = entry["success_rate"] * 100
        total_success += entry["success_count"]
        total_runs += entry["total_runs"]
        typer.echo(
            f"{entry['book_index']:>6} {entry['success_count']:>8} {entry['total_runs']:>10} {rate_pct:>13.1f}%"
        )

    if total_runs:
        overall = (total_success / total_runs) * 100
        typer.echo("-" * len(header))
        typer.echo(f"{'ALL':>6} {total_success:>8} {total_runs:>10} {overall:>13.1f}%")


@app.command()
def viz(experiment_dir: str = typer.Argument(".", help="Experiment directory")) -> None:
    """Launch the Gradio dashboard."""
    launch_dashboard(experiment_dir)


if __name__ == "__main__":
    app()
