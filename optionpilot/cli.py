"""OptionPilot CLI (Typer): interactive and headless modes.

    optionpilot "分析 SPY 的買點策略"        # headless: run one task and exit
    optionpilot                              # interactive: persistent session
    optionpilot --auto-approve "..."         # skip approval gating (headless automation)

Mirrors ml-intern's interactive/headless split. Interactive mode is human-in-loop by default
(approval prompts on expensive tools), matching the Phase 1 design.
"""

from __future__ import annotations

import typer
from rich.console import Console

from optionpilot import __version__
from optionpilot.agent.approval import auto_approve, interactive_approval
from optionpilot.agent.loop import ExperimentLoop
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.tools import register_default_tools

app = typer.Typer(add_completion=False, help="OptionPilot — options-strategy research agent.")
console = Console()


def _build_loop(config: Config, auto: bool) -> ExperimentLoop:
    approval = auto_approve if auto else interactive_approval
    router = ToolRouter(approval_fn=approval)
    register_default_tools(router, config)
    return ExperimentLoop(config=config, router=router)


@app.command()
def main(
    task: str = typer.Argument(None, help="Task to run. Omit for interactive mode."),
    auto_approve_flag: bool = typer.Option(
        False, "--auto-approve", help="Auto-approve all tool calls (headless automation)."
    ),
    model: str = typer.Option(None, "--model", help="Override the LiteLLM model string."),
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
):
    if version:
        console.print(f"OptionPilot {__version__}")
        raise typer.Exit()

    config = Config.load()
    if model:
        config = Config.load().__class__(**{**config.__dict__, "model": model})
    config.ensure_dirs()

    loop = _build_loop(config, auto=auto_approve_flag or task is not None)

    if task:
        console.print(loop.run(task))
        return

    console.print(f"[bold]OptionPilot {__version__}[/bold] — interactive mode. Ctrl-D to exit.")
    while True:
        try:
            user_in = console.input("[cyan]optionpilot›[/cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            break
        if not user_in:
            continue
        console.print(loop.run(user_in))


if __name__ == "__main__":
    app()
