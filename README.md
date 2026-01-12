# Wayland Display Control Service

CLI and MQTT agent for controlling Wayland displays via Home Assistant. Runs on Linux with Wayland and exposes monitor power and brightness controls through MQTT discovery.

## Features

- **Auto-discovery**: Automatically detects displays via `wlr-randr` and correlates with DDC buses
- **Per-display control**: Independent power and brightness for each monitor
- **Home Assistant integration**: MQTT discovery creates entities automatically
- **Multiple process managers**: Works with systemd, PM2, or runs standalone
- **Flexible configuration**: Environment variables, YAML config, or CLI flags

## Requirements

- Linux with Wayland compositor
- Python 3.11+
- `wlr-randr` - for display power control
- `ddcutil` - for brightness control (optional, only needed for brightness)
- MQTT broker (e.g., Mosquitto, Home Assistant's built-in broker)

### Installing dependencies on Raspberry Pi OS

```bash
sudo apt update
sudo apt install wlr-randr ddcutil mosquitto-clients

# Add user to i2c group for ddcutil access
sudo usermod -aG i2c $USER
# Log out and back in for group change to take effect
```

## Installation

### Using pipx (recommended)

```bash
sudo apt install pipx
pipx install git+https://github.com/dennispg/wlddc
pipx ensurepath  # Adds ~/.local/bin to PATH
```

### Using uv tool

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install wlddc
```

## Development

### Using uv (recommended)

```bash
# Clone the repository
git clone https://github.com/dennispg/wlddc.git
cd wlddc

# Install with uv
uv sync
```

### Using pip

```bash
git clone https://github.com/dennispg/wlddc.git
cd wlddc
pip install .
```

## Configuration

Configuration can be provided via environment variables, a YAML config file, or CLI arguments.

### Option 1: YAML config file

Create `~/.config/wlddc/config.yaml`:

```yaml
mqtt:
  broker: homeassistant.local
  port: 1883
  username: mqtt-user
  password: your-password-here

homeassistant:
  device_id: rpi_monitors
  device_name: "Raspberry Pi Monitors"

agent:
  poll_interval: 30
  log_level: INFO
```

Or generate an example:

```bash
wlddc generate config > ~/.config/wlddc/config.yaml
```

### Option 2: Environment variables

```bash
export WLDDC_MQTT__BROKER=homeassistant.local
export WLDDC_MQTT__USERNAME=mqtt-user
export WLDDC_MQTT__PASSWORD=your-password
export WLDDC_HOMEASSISTANT__DEVICE_ID=rpi_monitors
```

Generate a `.env` template:

```bash
wlddc generate env > .env
```

### Configuration reference

| Setting                          | Env Variable                            | Default                      | Description                      |
| -------------------------------- | --------------------------------------- | ---------------------------- | -------------------------------- |
| `mqtt.broker`                    | `WLDDC_MQTT__BROKER`                    | `localhost`                  | MQTT broker hostname             |
| `mqtt.port`                      | `WLDDC_MQTT__PORT`                      | `1883`                       | MQTT broker port                 |
| `mqtt.username`                  | `WLDDC_MQTT__USERNAME`                  | -                            | MQTT username                    |
| `mqtt.password`                  | `WLDDC_MQTT__PASSWORD`                  | -                            | MQTT password                    |
| `mqtt.client_id`                 | `WLDDC_MQTT__CLIENT_ID`                 | `wlddc`                      | MQTT client identifier           |
| `homeassistant.discovery_prefix` | `WLDDC_HOMEASSISTANT__DISCOVERY_PREFIX` | `homeassistant`              | HA discovery prefix              |
| `homeassistant.device_id`        | `WLDDC_HOMEASSISTANT__DEVICE_ID`        | `wlddc`                      | Device identifier                |
| `homeassistant.device_name`      | `WLDDC_HOMEASSISTANT__DEVICE_NAME`      | `Wayland Monitor Controller` | Display name in HA               |
| `agent.poll_interval`            | `WLDDC_AGENT__POLL_INTERVAL`            | `30`                         | State polling interval (seconds) |
| `agent.log_level`                | `WLDDC_AGENT__LOG_LEVEL`                | `INFO`                       | Log level                        |

## Usage

### Detect displays

Before running the agent, verify your displays are detected:

```bash
wlddc detect
```

Example output:

```
Found 1 display(s):

HDMI-A-1:
  Make:    Samsung Electric Company
  Model:   LU28R55
  Serial:  HNMNB00590
  Enabled: True
  Mode:    3840x2160@60Hz
  DDC Bus: /dev/i2c-7
  Brightness: supported
  Unique ID: hnmnb00590
```

### Run directly

```bash
# With config file
wlddc run

# With specific config
wlddc run --config /path/to/config.yaml

# Override broker
wlddc run --broker 192.168.1.100

# Verbose logging
wlddc run --verbose
```

### Run with systemd (recommended for production)

Generate and install the systemd user unit:

```bash
# Generate the unit file
wlddc generate systemd > ~/.config/systemd/user/wlddc.service

# If using a specific config file
wlddc generate systemd --config ~/.config/wlddc/config.yaml > ~/.config/systemd/user/wlddc.service

# Reload systemd and enable
systemctl --user daemon-reload
systemctl --user enable --now wlddc

# Check status
systemctl --user status wlddc

# View logs
journalctl --user -u wlddc -f
```

**Note**: The service must run as a user service (`systemctl --user`) to have access to the Wayland display.

### Run with PM2

Generate and install the PM2 ecosystem file:

```bash
# Generate ecosystem file
wlddc generate pm2 -o ecosystem.config.js

# If using a specific config file
wlddc generate pm2 --config ~/.config/wlddc/config.yaml -o ecosystem.config.js

# Start with PM2
pm2 start ecosystem.config.js

# Save for auto-restart on boot
pm2 save
pm2 startup
```

## Home Assistant

Once the agent is running and connected to your MQTT broker, Home Assistant will automatically discover the devices if you have MQTT discovery enabled.

You'll see entities like:

- `switch.lu28r55_power` - Turn the display on/off
- `number.lu28r55_brightness` - Adjust brightness (0-100%)
- `sensor.lu28r55_resolution` - Current display resolution

### Example automation

```yaml
automation:
  - alias: "Turn off monitors at night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.lu28r55_power

  - alias: "Dim monitors in evening"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: number.set_value
        target:
          entity_id: number.lu28r55_brightness
        data:
          value: 30
```

## Troubleshooting

### "No displays found"

1. Ensure you're running under a Wayland compositor:

   ```bash
   echo $WAYLAND_DISPLAY  # Should output something like "wayland-1"
   ```

2. Verify wlr-randr works:

   ```bash
   wlr-randr
   ```

3. For systemd/PM2, ensure the `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR` environment variables are set correctly in the service file.

### Brightness not working

1. Verify ddcutil can communicate with your monitor:

   ```bash
   ddcutil detect
   ddcutil getvcp 10  # Get brightness
   ```

2. Ensure your user is in the `i2c` group:

   ```bash
   groups  # Should include 'i2c'
   ```

3. Some monitors don't support DDC/CI. Check your monitor's OSD settings for a DDC/CI option.

### MQTT connection issues

1. Test MQTT connectivity:

   ```bash
   # Install mosquitto-clients
   sudo apt install mosquitto-clients

   # Test connection
   mosquitto_sub -h homeassistant.local -u mqtt-user -P mqtt-pass -t '#' -v
   ```

2. Check logs:
   ```bash
   wlddc run --verbose
   ```

## CLI Reference

```
wlddc --help           # Show help
wlddc --version        # Show version
wlddc run              # Run the agent
wlddc detect           # Detect and show displays
wlddc on               # Turn display(s) on
wlddc off              # Turn display(s) off.
wlddc set <amount>     # Set display brightness
wlddc generate config  # Print example config
wlddc generate systemd # Generate systemd unit
wlddc generate pm2     # Generate PM2 ecosystem file
wlddc generate env     # Generate .env template
```

## License

MIT
