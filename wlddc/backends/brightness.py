"""Brightness control via ddcutil."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# DDC/CI VCP code for brightness (decimal 10, aka 0x0A)
VCP_BRIGHTNESS = 10


class BrightnessController:
    """Control monitor brightness via ddcutil."""

    def __init__(self, retries: int = 2, command_timeout: float = 10.0):
        """Initialize brightness controller.

        Args:
            retries: Number of retries for ddcutil commands
            command_timeout: Timeout for ddcutil commands in seconds
        """
        self.retries = retries
        self.command_timeout = command_timeout

    async def get_brightness(self, i2c_bus: int) -> Optional[int]:
        """Get current brightness for a display via its I2C bus.

        Args:
            i2c_bus: The I2C bus number (e.g., 7 for /dev/i2c-7)

        Returns:
            Brightness value 0-100, or None on failure
        """
        for attempt in range(self.retries + 1):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ddcutil",
                    "getvcp",
                    str(VCP_BRIGHTNESS),
                    "--bus",
                    str(i2c_bus),
                    "--brief",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self.command_timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.warning(f"ddcutil getvcp timed out on bus {i2c_bus}")
                    continue

                if proc.returncode != 0:
                    if attempt < self.retries:
                        logger.debug(f"ddcutil getvcp failed on bus {i2c_bus}, retrying...")
                        await asyncio.sleep(0.5)
                        continue
                    logger.warning(f"ddcutil getvcp failed on bus {i2c_bus}: {stderr.decode()}")
                    return None

                # Brief format: "VCP 10 C 60 100" (code, type, current, max)
                # or "VCP 10 C 60" for some monitors
                output = stdout.decode().strip()
                parts = output.split()

                if len(parts) >= 4 and parts[0] == "VCP":
                    return int(parts[3])
                elif len(parts) >= 3:
                    # Some formats may differ
                    for i, part in enumerate(parts):
                        if part == "C" and i + 1 < len(parts):
                            return int(parts[i + 1])

                logger.warning(f"Unexpected ddcutil output: {output}")
                return None

            except FileNotFoundError:
                logger.error("ddcutil not found. Is it installed?")
                return None
            except ValueError as e:
                logger.warning(f"Failed to parse brightness value: {e}")
                return None
            except Exception as e:
                logger.exception(f"Error getting brightness: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(0.5)
                    continue
                return None

        return None

    async def set_brightness(self, i2c_bus: int, value: int) -> bool:
        """Set brightness for a display via its I2C bus.

        Args:
            i2c_bus: The I2C bus number
            value: Brightness value 0-100

        Returns:
            True on success, False on failure
        """
        # Clamp value to valid range
        value = max(0, min(100, value))

        for attempt in range(self.retries + 1):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ddcutil",
                    "setvcp",
                    str(VCP_BRIGHTNESS),
                    str(value),
                    "--bus",
                    str(i2c_bus),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    _, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self.command_timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.warning(f"ddcutil setvcp timed out on bus {i2c_bus}")
                    continue

                if proc.returncode != 0:
                    if attempt < self.retries:
                        logger.debug(f"ddcutil setvcp failed on bus {i2c_bus}, retrying...")
                        await asyncio.sleep(0.5)
                        continue
                    logger.error(f"ddcutil setvcp failed on bus {i2c_bus}: {stderr.decode()}")
                    return False

                logger.info(f"Set brightness on bus {i2c_bus} to {value}")
                return True

            except FileNotFoundError:
                logger.error("ddcutil not found. Is it installed?")
                return False
            except Exception as e:
                logger.exception(f"Error setting brightness: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(0.5)
                    continue
                return False

        return False

    async def get_brightness_range(self, i2c_bus: int) -> tuple[int, int]:
        """Get the brightness range for a display.

        Most monitors support 0-100, but some may differ.

        Returns:
            Tuple of (min, max) brightness values, defaults to (0, 100)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ddcutil",
                "getvcp",
                str(VCP_BRIGHTNESS),
                "--bus",
                str(i2c_bus),
                "--brief",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=self.command_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return (0, 100)

            if proc.returncode != 0:
                return (0, 100)

            # Brief format: "VCP 10 C 60 100" - last value is max
            output = stdout.decode().strip()
            parts = output.split()

            if len(parts) >= 5 and parts[0] == "VCP":
                max_val = int(parts[4])
                return (0, max_val)

            return (0, 100)
        except Exception:
            return (0, 100)
