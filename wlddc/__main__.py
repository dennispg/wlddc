"""CLI entry point for wlddc."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from wlddc import __version__
from wlddc.cli.generate import generate_app

app = typer.Typer(
    name="wlddc",
    help="Wayland monitor control MQTT agent for Home Assistant",
    add_completion=True,
)

app.add_typer(generate_app, name="generate")


def setup_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"wlddc {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Wayland monitor control MQTT agent for Home Assistant."""
    pass


@app.command()
def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to YAML config file",
        exists=True,
        dir_okay=False,
    ),
    broker: Optional[str] = typer.Option(
        None,
        "--broker",
        "-b",
        help="MQTT broker hostname (overrides config)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug logging",
    ),
) -> None:
    """Run the MQTT agent."""
    from wlddc.agent import Agent
    from wlddc.config import Settings

    settings = Settings.load(config)

    # CLI overrides
    if broker:
        settings.mqtt.broker = broker

    if verbose:
        settings.agent.log_level = "DEBUG"

    setup_logging(settings.agent.log_level)

    agent = Agent(settings)

    try:
        asyncio.run(agent.run())

    except KeyboardInterrupt:
        pass


@app.command("set")
def set_brightness(
    value: str = typer.Argument(
        ...,
        help="Brightness value (0-100 or 0%-100%)",
    ),
    display: Optional[str] = typer.Option(
        None,
        "--display",
        "-d",
        help="Target specific display (output name or unique ID)",
    ),
) -> None:
    """Set display brightness.

    Examples:
        wlddc set 50
        wlddc set 75%
        wlddc set 30 --display HDMI-A-1
    """
    from wlddc.backends.brightness import BrightnessController
    from wlddc.backends.display import DisplayManager

    # Parse value (strip % if present)
    try:
        brightness = int(value.rstrip("%"))
        if not 0 <= brightness <= 100:
            typer.echo("Error: Brightness must be between 0 and 100", err=True)
            raise typer.Exit(1)
    except ValueError:
        typer.echo(f"Error: Invalid brightness value: {value}", err=True)
        raise typer.Exit(1)

    async def _set_brightness() -> None:
        manager = DisplayManager()
        controller = BrightnessController()
        displays = await manager.correlate_displays()

        if not displays:
            typer.echo("No displays found.", err=True)
            raise typer.Exit(1)

        targets = []
        for d in displays:
            if display is None:
                # Target all displays with DDC support
                if d.supports_brightness:
                    targets.append(d)
            elif d.wayland.name == display or d.unique_id == display:
                targets.append(d)
                break

        if not targets:
            if display:
                typer.echo(f"Display not found: {display}", err=True)
            else:
                typer.echo("No displays with brightness control found.", err=True)
            raise typer.Exit(1)

        for d in targets:
            if not d.supports_brightness or not d.ddc:
                typer.echo(f"{d.wayland.name}: No DDC support, skipping")
                continue

            success = await controller.set_brightness(d.ddc.i2c_bus, brightness)
            if success:
                typer.echo(f"{d.wayland.name}: Set brightness to {brightness}%")
            else:
                typer.echo(f"{d.wayland.name}: Failed to set brightness", err=True)

    asyncio.run(_set_brightness())


@app.command()
def on(
    display: Optional[str] = typer.Option(
        None,
        "--display",
        "-d",
        help="Target specific display (output name or unique ID)",
    ),
) -> None:
    """Turn display(s) on.

    Examples:
        wlddc on
        wlddc on --display HDMI-A-1
    """
    from wlddc.backends.display import DisplayManager

    async def _on() -> None:
        manager = DisplayManager()
        displays = await manager.correlate_displays()

        if not displays:
            typer.echo("No displays found.", err=True)
            raise typer.Exit(1)

        targets = []
        for d in displays:
            if display is None:
                targets.append(d)
            elif d.wayland.name == display or d.unique_id == display:
                targets.append(d)
                break

        if not targets:
            typer.echo(f"Display not found: {display}", err=True)
            raise typer.Exit(1)

        for d in targets:
            success = await manager.set_display_power(d.wayland.name, on=True)
            if success:
                typer.echo(f"{d.wayland.name}: Turned on")
            else:
                typer.echo(f"{d.wayland.name}: Failed to turn on", err=True)

    asyncio.run(_on())


@app.command()
def off(
    display: Optional[str] = typer.Option(
        None,
        "--display",
        "-d",
        help="Target specific display (output name or unique ID)",
    ),
) -> None:
    """Turn display(s) off.

    Examples:
        wlddc off
        wlddc off --display HDMI-A-1
    """
    from wlddc.backends.display import DisplayManager

    async def _off() -> None:
        manager = DisplayManager()
        displays = await manager.correlate_displays()

        if not displays:
            typer.echo("No displays found.", err=True)
            raise typer.Exit(1)

        targets = []
        for d in displays:
            if display is None:
                targets.append(d)
            elif d.wayland.name == display or d.unique_id == display:
                targets.append(d)
                break

        if not targets:
            typer.echo(f"Display not found: {display}", err=True)
            raise typer.Exit(1)

        for d in targets:
            success = await manager.set_display_power(d.wayland.name, on=False)
            if success:
                typer.echo(f"{d.wayland.name}: Turned off")
            else:
                typer.echo(f"{d.wayland.name}: Failed to turn off", err=True)

    asyncio.run(_off())


@app.command("list")
def list_displays() -> None:
    """List connected displays."""
    from wlddc.backends.display import DisplayManager

    async def _list() -> None:
        manager = DisplayManager()
        displays = await manager.correlate_displays()

        if not displays:
            typer.echo("No displays found.", err=True)
            raise typer.Exit(1)

        for d in displays:
            status = "on" if d.wayland.enabled else "off"
            brightness = "ddc" if d.supports_brightness else "no-ddc"
            name = d.wayland.model or d.wayland.name
            typer.echo(f"{d.wayland.name}  {status}  {brightness}  {name}")

    asyncio.run(_list())


@app.command()
def detect() -> None:
    """Detect displays and show detailed correlation info."""
    from wlddc.backends.display import DisplayManager

    async def _detect() -> None:
        manager = DisplayManager()
        displays = await manager.correlate_displays()

        if not displays:
            typer.echo("No displays found.")
            typer.echo("\nTroubleshooting:")
            typer.echo("  - Ensure wlr-randr is installed")
            typer.echo("  - Ensure you're running under a Wayland compositor")
            typer.echo("  - Check WAYLAND_DISPLAY environment variable")
            raise typer.Exit(1)

        typer.echo(f"\nFound {len(displays)} display(s):\n")

        for d in displays:
            typer.echo(f"{d.wayland.name}:")
            typer.echo(f"  Make:    {d.wayland.make or 'Unknown'}")
            typer.echo(f"  Model:   {d.wayland.model or 'Unknown'}")
            typer.echo(f"  Serial:  {d.wayland.serial or 'Unknown'}")
            typer.echo(f"  Enabled: {d.wayland.enabled}")
            typer.echo(f"  Mode:    {d.wayland.current_mode or 'Unknown'}")

            if d.ddc:
                typer.echo(f"  DDC Bus: /dev/i2c-{d.ddc.i2c_bus}")
                typer.echo("  Brightness: supported")
            else:
                typer.echo("  DDC Bus: Not found")
                typer.echo("  Brightness: NOT supported (no DDC)")

            typer.echo(f"  Unique ID: {d.unique_id}")
            typer.echo()

        typer.echo("Use these unique IDs in your Home Assistant configuration.")

    asyncio.run(_detect())


@app.command(hidden=True)
def help(ctx: typer.Context) -> None:
    """Show help message."""
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())


if __name__ == "__main__":
    app()
