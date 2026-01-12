"""CLI commands for generating service files."""

import os
import socket
import sys
from pathlib import Path
from typing import Optional

import typer

generate_app = typer.Typer(help="Generate configuration and service files")


def _get_device_defaults() -> tuple[str, str]:
    """Get default device_id and device_name based on hostname."""
    hostname = socket.gethostname().split(".")[0]  # Remove domain if present
    device_id = hostname.lower().replace("-", "_")
    device_name = f"{hostname} Monitors"
    return device_id, device_name


def _get_wayland_env() -> tuple[str, str]:
    """Get current Wayland environment variables."""
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-1")
    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return wayland_display, xdg_runtime_dir


@generate_app.command("systemd")
def generate_systemd(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file to use in unit",
    ),
    wayland_display: Optional[str] = typer.Option(
        None,
        "--wayland-display",
        help="WAYLAND_DISPLAY value (defaults to current env)",
    ),
) -> None:
    """Generate a systemd user unit file.

    The generated unit is intended for use with 'systemctl --user'.

    Example usage:
        wlddc generate systemd > ~/.config/systemd/user/wlddc.service
        systemctl --user daemon-reload
        systemctl --user enable --now wlddc
    """
    python_path = sys.executable
    wayland_env, xdg_runtime = _get_wayland_env()

    if wayland_display is None:
        wayland_display = wayland_env

    config_arg = f" --config {config_path}" if config_path else ""

    unit = f"""\
[Unit]
Description=Wayland Monitor Control MQTT Agent
After=network-online.target graphical-session.target
Wants=network-online.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={python_path} -m wlddc run{config_arg}
Restart=on-failure
RestartSec=10

# Wayland environment
Environment=WAYLAND_DISPLAY={wayland_display}
Environment=XDG_RUNTIME_DIR={xdg_runtime}

# Security hardening (optional, comment out if causing issues)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=default.target
"""

    if output:
        output.write_text(unit)
        typer.echo(f"Written to {output}")
        typer.echo()
        typer.echo("To install:")
        typer.echo(f"  cp {output} ~/.config/systemd/user/")
        typer.echo("  systemctl --user daemon-reload")
        typer.echo("  systemctl --user enable --now wlddc")
    else:
        typer.echo(unit)
        typer.echo("# Save to: ~/.config/systemd/user/wlddc.service")
        typer.echo("# Then run:")
        typer.echo("#   systemctl --user daemon-reload")
        typer.echo("#   systemctl --user enable --now wlddc")


@generate_app.command("pm2")
def generate_pm2(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file to use",
    ),
    wayland_display: Optional[str] = typer.Option(
        None,
        "--wayland-display",
        help="WAYLAND_DISPLAY value (defaults to current env)",
    ),
) -> None:
    """Generate a PM2 ecosystem configuration file.

    Example usage:
        wlddc generate pm2 -o ecosystem.config.js
        pm2 start ecosystem.config.js
        pm2 save
        pm2 startup
    """
    python_path = sys.executable
    wayland_env, xdg_runtime = _get_wayland_env()

    if wayland_display is None:
        wayland_display = wayland_env

    config_arg = f" --config {config_path}" if config_path else ""

    ecosystem = f"""\
module.exports = {{
  apps: [{{
    name: 'wlddc',
    script: '{python_path}',
    args: '-m wlddc run{config_arg}',
    interpreter: 'none',
    env: {{
      WAYLAND_DISPLAY: '{wayland_display}',
      XDG_RUNTIME_DIR: '{xdg_runtime}',
    }},
    // Restart configuration
    restart_delay: 5000,
    max_restarts: 10,
    min_uptime: 10000,
    // Logging
    error_file: '~/.pm2/logs/wlddc-error.log',
    out_file: '~/.pm2/logs/wlddc-out.log',
    merge_logs: true,
    time: true,
  }}],
}};
"""

    if output:
        output.write_text(ecosystem)
        typer.echo(f"Written to {output}")
        typer.echo()
        typer.echo("To install:")
        typer.echo(f"  pm2 start {output}")
        typer.echo("  pm2 save")
        typer.echo("  pm2 startup")
    else:
        typer.echo(ecosystem)
        typer.echo("// Save to: ecosystem.config.js")
        typer.echo("// Then run:")
        typer.echo("//   pm2 start ecosystem.config.js")
        typer.echo("//   pm2 save")
        typer.echo("//   pm2 startup")


@generate_app.command("env")
def generate_env(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout",
    ),
) -> None:
    """Generate an example .env file for configuration.

    Environment variables can be used instead of or alongside a YAML config file.
    Environment variables take precedence over config file values.
    """
    device_id, device_name = _get_device_defaults()

    env_content = f"""\
# wlddc environment configuration
# Copy to .env and customize values
# Environment variables override config file values

# MQTT Settings
WLDDC_MQTT__BROKER=homeassistant.local
WLDDC_MQTT__PORT=1883
WLDDC_MQTT__USERNAME=mqtt-user
WLDDC_MQTT__PASSWORD=your-password-here
WLDDC_MQTT__CLIENT_ID=wlddc

# Home Assistant Settings
WLDDC_HOMEASSISTANT__DISCOVERY_PREFIX=homeassistant
WLDDC_HOMEASSISTANT__DEVICE_ID={device_id}
WLDDC_HOMEASSISTANT__DEVICE_NAME={device_name}

# Agent Settings
WLDDC_AGENT__POLL_INTERVAL=30
WLDDC_AGENT__LOG_LEVEL=INFO
"""

    if output:
        output.write_text(env_content)
        typer.echo(f"Written to {output}")
    else:
        typer.echo(env_content)


@generate_app.command("config")
def generate_config(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file instead of stdout",
    ),
) -> None:
    """Generate an example YAML configuration file.

    Example usage:
        wlddc generate config > ~/.config/wlddc/config.yaml
    """
    device_id, device_name = _get_device_defaults()

    config_content = f"""\
# wlddc configuration
# Save to ~/.config/wlddc/config.yaml or use --config flag

mqtt:
  broker: homeassistant.local
  port: 1883
  username: mqtt-user
  password: your-password-here
  client_id: wlddc
  keepalive: 60
  reconnect_interval: 5.0
  reconnect_max_interval: 120.0

homeassistant:
  discovery_prefix: homeassistant
  device_id: {device_id}
  device_name: "{device_name}"

agent:
  poll_interval: 30
  command_timeout: 10.0
  ddcutil_retries: 2
  log_level: INFO

# Optional: Manual display-to-DDC bus mappings
# Use this if auto-detection fails to correlate displays correctly
# Run 'wlddc detect' to see available displays and their info
#
# display_overrides:
#   - output_name: HDMI-A-1
#     ddc_bus: 7
#     brightness_enabled: true
#     power_enabled: true
"""

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(config_content)
        typer.echo(f"Written to {output}")
    else:
        typer.echo(config_content)
