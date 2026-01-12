"""Display management via wlr-randr with DDC correlation."""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WaylandOutput:
    """Represents a wlr-randr output."""

    name: str  # e.g., "HDMI-A-1", "DP-1"
    enabled: bool = False
    make: Optional[str] = None  # e.g., "Samsung Electric Company"
    model: Optional[str] = None  # e.g., "LU28R55"
    serial: Optional[str] = None  # e.g., "HNMNB00590"
    current_mode: Optional[str] = None  # e.g., "1920x1080@60Hz"


@dataclass
class DDCDisplay:
    """Represents a ddcutil-detected display."""

    display_number: int  # ddcutil display number (1-based)
    i2c_bus: int  # e.g., 7 for /dev/i2c-7
    mfg_id: Optional[str] = None  # 3-letter code, e.g., "SAM"
    model: Optional[str] = None
    serial: Optional[str] = None


@dataclass
class CorrelatedDisplay:
    """A display with both wlr-randr and ddcutil information."""

    wayland: WaylandOutput
    ddc: Optional[DDCDisplay] = None

    @property
    def supports_brightness(self) -> bool:
        """Check if this display supports DDC brightness control."""
        return self.ddc is not None

    @property
    def unique_id(self) -> str:
        """Generate a stable unique ID for Home Assistant."""
        # Prefer serial, fall back to model+output_name
        if self.wayland.serial:
            return self.wayland.serial.lower().replace(" ", "_").replace("-", "_")
        base = self.wayland.model or self.wayland.name
        return f"{base}_{self.wayland.name}".lower().replace(" ", "_").replace("-", "_")

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        if self.wayland.model:
            return f"{self.wayland.model} ({self.wayland.name})"
        return self.wayland.name


class DisplayManager:
    """Manages display detection and correlation."""

    def __init__(self, display_overrides: Optional[list] = None):
        """Initialize with optional manual display-to-DDC mappings."""
        self.display_overrides = {o.output_name: o for o in (display_overrides or [])}

    async def discover_wayland_outputs(self) -> list[WaylandOutput]:
        """Parse wlr-randr output to get display info."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "wlr-randr",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"wlr-randr failed: {stderr.decode()}")
                return []

            return self._parse_wlr_randr_output(stdout.decode())
        except FileNotFoundError:
            logger.error("wlr-randr not found. Is it installed?")
            return []
        except Exception as e:
            logger.exception(f"Error discovering Wayland outputs: {e}")
            return []

    def _parse_wlr_randr_output(self, output: str) -> list[WaylandOutput]:
        """Parse wlr-randr output text into WaylandOutput objects.

        Example wlr-randr output:
        HDMI-A-1 "Samsung Electric Company LU28R55 HNMNB00590 (HDMI-A-1)"
          Enabled: yes
          Make: Samsung Electric Company
          Model: LU28R55
          Serial: HNMNB00590
          Physical size: 620x340 mm
          Modes:
            3840x2160@59.997002 Hz (preferred, current)
        """
        outputs = []
        current_output: Optional[WaylandOutput] = None

        for line in output.split("\n"):
            # New output starts with non-whitespace
            if line and not line[0].isspace():
                # Save previous output
                if current_output:
                    outputs.append(current_output)

                # Parse output name (first word)
                match = re.match(r"^(\S+)", line)
                if match:
                    current_output = WaylandOutput(name=match.group(1))
            elif current_output and line.strip():
                line = line.strip()

                if line.startswith("Enabled:"):
                    current_output.enabled = "yes" in line.lower()
                elif line.startswith("Make:"):
                    current_output.make = line.split(":", 1)[1].strip()
                elif line.startswith("Model:"):
                    current_output.model = line.split(":", 1)[1].strip()
                elif line.startswith("Serial:"):
                    current_output.serial = line.split(":", 1)[1].strip()
                elif "current" in line.lower() and "x" in line:
                    # Parse mode line like "3840x2160@59.997002 Hz (preferred, current)"
                    mode_match = re.match(r"(\d+x\d+@[\d.]+)\s*Hz", line)
                    if mode_match:
                        current_output.current_mode = mode_match.group(1) + "Hz"

        # Don't forget the last output
        if current_output:
            outputs.append(current_output)

        return outputs

    async def discover_ddc_displays(self) -> list[DDCDisplay]:
        """Parse ddcutil detect output to get DDC-capable displays."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ddcutil",
                "detect",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode != 0:
                # ddcutil may return non-zero if no displays found
                logger.warning(f"ddcutil detect returned {proc.returncode}")
                return []

            return self._parse_ddcutil_output(stdout.decode())
        except FileNotFoundError:
            logger.error("ddcutil not found. Is it installed?")
            return []
        except Exception as e:
            logger.exception(f"Error discovering DDC displays: {e}")
            return []

    def _parse_ddcutil_output(self, output: str) -> list[DDCDisplay]:
        """Parse ddcutil detect output into DDCDisplay objects.

        Example ddcutil detect output:
        Display 1
           I2C bus:  /dev/i2c-7
           DRM connector:           card1-HDMI-A-1
           Mfg id:               SAM - Samsung Electric Company
           Model:                LU28R55
           Serial number:        HNMNB00590
           ...
        """
        displays = []
        current_display: Optional[DDCDisplay] = None

        for line in output.split("\n"):
            line_stripped = line.strip()

            # New display starts with "Display N"
            if line_stripped.startswith("Display "):
                if current_display and current_display.i2c_bus is not None:
                    displays.append(current_display)

                try:
                    display_num = int(line_stripped.split()[1])
                    current_display = DDCDisplay(display_number=display_num, i2c_bus=-1)
                except (IndexError, ValueError):
                    current_display = None
            elif current_display:
                if line_stripped.startswith("I2C bus:"):
                    # Parse "/dev/i2c-7" -> 7
                    bus_match = re.search(r"/dev/i2c-(\d+)", line_stripped)
                    if bus_match:
                        current_display.i2c_bus = int(bus_match.group(1))
                elif line_stripped.startswith("Mfg id:"):
                    # Parse "SAM - Samsung Electric Company" -> "SAM"
                    mfg_match = re.match(r"Mfg id:\s*(\w+)", line_stripped)
                    if mfg_match:
                        current_display.mfg_id = mfg_match.group(1)
                elif line_stripped.startswith("Model:"):
                    current_display.model = line_stripped.split(":", 1)[1].strip()
                elif line_stripped.startswith("Serial number:"):
                    current_display.serial = line_stripped.split(":", 1)[1].strip()

        # Don't forget the last display
        if current_display and current_display.i2c_bus >= 0:
            displays.append(current_display)

        return displays

    async def correlate_displays(self) -> list[CorrelatedDisplay]:
        """Match wlr-randr outputs to ddcutil displays via EDID data."""
        wayland_outputs = await self.discover_wayland_outputs()
        ddc_displays = await self.discover_ddc_displays()

        logger.info(f"Found {len(wayland_outputs)} Wayland outputs, {len(ddc_displays)} DDC displays")

        correlated = []
        used_ddc: set[int] = set()

        for output in wayland_outputs:
            matched_ddc: Optional[DDCDisplay] = None

            # Check for manual override first
            if output.name in self.display_overrides:
                override = self.display_overrides[output.name]
                if override.ddc_bus is not None:
                    for ddc in ddc_displays:
                        if ddc.i2c_bus == override.ddc_bus:
                            matched_ddc = ddc
                            used_ddc.add(ddc.display_number)
                            logger.info(f"Override: {output.name} -> i2c-{ddc.i2c_bus}")
                            break

            # Strategy 1: Exact serial number match
            if not matched_ddc and output.serial:
                for ddc in ddc_displays:
                    if (
                        ddc.serial
                        and ddc.serial == output.serial
                        and ddc.display_number not in used_ddc
                    ):
                        matched_ddc = ddc
                        used_ddc.add(ddc.display_number)
                        logger.info(f"Serial match: {output.name} -> i2c-{ddc.i2c_bus}")
                        break

            # Strategy 2: Model name match (fallback)
            if not matched_ddc and output.model:
                for ddc in ddc_displays:
                    if (
                        ddc.model
                        and ddc.model == output.model
                        and ddc.display_number not in used_ddc
                    ):
                        matched_ddc = ddc
                        used_ddc.add(ddc.display_number)
                        logger.info(f"Model match: {output.name} -> i2c-{ddc.i2c_bus}")
                        break

            correlated.append(CorrelatedDisplay(wayland=output, ddc=matched_ddc))

            if not matched_ddc:
                logger.warning(f"No DDC match for {output.name} - brightness control disabled")

        return correlated

    async def set_display_power(self, output_name: str, on: bool) -> bool:
        """Turn a display on or off via wlr-randr."""
        try:
            cmd = ["wlr-randr", "--output", output_name, "--on" if on else "--off"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"Failed to set {output_name} power: {stderr.decode()}")
                return False

            logger.info(f"Set {output_name} power: {'ON' if on else 'OFF'}")
            return True
        except Exception as e:
            logger.exception(f"Error setting display power: {e}")
            return False

    async def get_display_enabled(self, output_name: str) -> Optional[bool]:
        """Get whether a specific display is enabled."""
        outputs = await self.discover_wayland_outputs()
        for output in outputs:
            if output.name == output_name:
                return output.enabled
        return None
