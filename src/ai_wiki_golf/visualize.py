from __future__ import annotations

from pathlib import Path
from typing import Any

import gradio as gr
import yaml


def launch_dashboard(experiment_dir: str) -> None:
    exp_path = Path(experiment_dir).resolve()

    with gr.Blocks(title="AI Wikipedia Golf Dashboard") as demo:
        gr.Markdown("# Wikipedia Golf Runs\n実験ディレクトリを指定し、各プレイの詳細を確認してください。")
        exp_input = gr.Textbox(
            label="Experiment Directory",
            value=str(exp_path),
        )
        refresh_btn = gr.Button("Load Experiment")
        summary_table = gr.Dataframe(
            headers=["Log", "Start", "Goal", "Score", "Steps"],
            datatype=["str", "str", "str", "number", "number"],
            interactive=False,
        )
        log_selector = gr.Dropdown(label="Select Log", choices=[])
        game_md = gr.Markdown(label="Game Summary")
        chat_md = gr.Markdown(label="Chat Log")
        book_md = gr.Markdown(label="Guide")

        def load_overview(path: str):
            exp = Path(path)
            logs_dir = exp / "logs"
            rows: list[list[Any]] = []
            options: list[str] = []
            if logs_dir.exists():
                for log_file in sorted(logs_dir.glob("*.yaml")):
                    data = yaml.safe_load(log_file.read_text(encoding="utf-8"))
                    history = data.get("game", {}).get("history", [])
                    rows.append(
                        [
                            log_file.name,
                            data.get("game", {}).get("start", "-"),
                            data.get("game", {}).get("goal", "-"),
                            data.get("game", {}).get("score", "-"),
                            len(history),
                        ]
                    )
                    options.append(log_file.name)
            default = options[0] if options else None
            return rows, gr.Dropdown.update(choices=options, value=default)

        def load_detail(path: str, log_name: str | None):
            if not log_name:
                return "(ログを選択してください)", "", ""
            log_path = Path(path) / "logs" / log_name
            if not log_path.exists():
                return "ログが見つかりません", "", ""
            data = yaml.safe_load(log_path.read_text(encoding="utf-8"))
            game = data.get("game", {})
            history_lines = [
                f"{idx+1}. {step['current']} -> {step['choice']}" for idx, step in enumerate(game.get("history", []))
            ]
            game_summary = (
                f"**Start:** {game.get('start')}\n\n"
                f"**Goal:** {game.get('goal')}\n\n"
                f"**Score:** {game.get('score')}\n\n"
                "**History:**\n" + ("\n".join(history_lines) if history_lines else "(なし)")
            )
            messages = data.get("messages", [])
            chat_lines = [f"### {m['role']}\n{m['content']}" for m in messages]
            chat_text = "\n\n".join(chat_lines)
            iteration = _infer_iteration(log_name)
            book_path = Path(path) / "books" / f"{iteration}.txt"
            guide_text = book_path.read_text(encoding="utf-8") if book_path.exists() else "(書籍なし)"
            return game_summary, chat_text, guide_text

        event = refresh_btn.click(load_overview, inputs=exp_input, outputs=[summary_table, log_selector])
        event.then(load_detail, inputs=[exp_input, log_selector], outputs=[game_md, chat_md, book_md])
        log_selector.change(load_detail, inputs=[exp_input, log_selector], outputs=[game_md, chat_md, book_md])

    demo.launch()


def _infer_iteration(log_name: str) -> str:
    if log_name.endswith(".yaml"):
        return log_name[:-5]
    return log_name
