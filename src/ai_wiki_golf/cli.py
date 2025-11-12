from __future__ import annotations

from pathlib import Path

import typer

from .evaluation import evaluate_books
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


@app.command()
def viz(experiment_dir: str = typer.Argument(".", help="Experiment directory")) -> None:
    """Launch the Gradio dashboard."""
    launch_dashboard(experiment_dir)


if __name__ == "__main__":
    app()
