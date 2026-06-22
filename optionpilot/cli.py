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
from optionpilot.agent.approval import auto_spend, interactive_spend
from optionpilot.agent.loop import ExperimentLoop
from optionpilot.agent.profiles import PROFILES, build_loop
from optionpilot.config import Config

app = typer.Typer(add_completion=False, help="OptionPilot — options-strategy research agent.")
console = Console()


def _build_loop(config: Config, auto: bool, profile_key: str = "options") -> ExperimentLoop:
    # Approval is consulted only at the point of a paid download (estimates / cache hits are
    # free and never prompt). --auto-approve allows; otherwise the user confirms each purchase.
    approve_spend = auto_spend if auto else interactive_spend
    return build_loop(config, PROFILES[profile_key], approve_spend=approve_spend)


@app.command()
def main(
    task: str = typer.Argument(None, help="Task to run. Omit for interactive mode."),
    auto_approve_flag: bool = typer.Option(
        False, "--auto-approve", help="Auto-approve all tool calls (headless automation)."
    ),
    profile: str = typer.Option(
        "options", "--profile", help="Research desk: 'options' (stock options) or 'crypto' "
        "(Binance USDⓈ-M perps)."
    ),
    model: str = typer.Option(None, "--model", help="Override the LiteLLM model string."),
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
):
    if version:
        console.print(f"OptionPilot {__version__}")
        raise typer.Exit()

    if profile not in PROFILES:
        console.print(f"[red]unknown profile '{profile}'; choose from {list(PROFILES)}[/red]")
        raise typer.Exit(code=1)

    config = Config.load()
    if model:
        config = Config.load().__class__(**{**config.__dict__, "model": model})
    config.ensure_dirs()

    # Money-spending tools always require approval unless --auto-approve is explicitly set
    # (headless included). Interactive approval is no-tty-safe (denies) so nothing spends silently.
    loop = _build_loop(config, auto=auto_approve_flag, profile_key=profile)

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
