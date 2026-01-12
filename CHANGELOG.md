# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2025-01-12

Initial public release.

### Features

**Display Control**

- Power on/off via `wlr-randr` for Wayland-native display control
- Brightness adjustment via DDC/CI using `ddcutil`
- Per-display independent control for multi-monitor setups
- Real-time resolution reporting

**Home Assistant Integration**

- MQTT Discovery for automatic entity creation
- Creates switch, number, and sensor entities per display
- Configurable device naming and grouping

**Auto-Discovery**

- Automatic detection of Wayland outputs and DDC buses
- Smart correlation using serial numbers or model names
- Manual override support for edge cases

**Flexible Deployment**

- Runs standalone, with systemd (user service), or PM2
- Built-in generators for service configurations
- YAML config, environment variables, or CLI flags

**Reliability**

- Exponential backoff with jitter for MQTT reconnection
- Configurable command timeouts and DDC retries
- Graceful handling of flaky DDC hardware

### CLI Commands

```
wlddc run              # Start the MQTT agent
wlddc detect           # Show detected displays
wlddc on/off           # Direct power control
wlddc set <value>      # Direct brightness control
wlddc generate         # Generate config/service files
```

### Requirements

- Linux with Wayland compositor
- Python 3.11+
- `wlr-randr` (required)
- `ddcutil` (optional, for brightness)
- MQTT broker

### Installation

`pipx install git+https://github.com/dennispg/wlddc`
