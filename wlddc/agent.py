"""Main MQTT agent for Wayland monitor control."""

import asyncio
import json
import logging
import random
import signal
from typing import Optional

import aiomqtt

from wlddc import __version__
from wlddc.backends.brightness import BrightnessController
from wlddc.backends.display import CorrelatedDisplay, DisplayManager
from wlddc.config import Settings

logger = logging.getLogger(__name__)


class Agent:
    """MQTT agent for controlling Wayland displays."""

    def __init__(self, settings: Settings):
        """Initialize the agent with settings."""
        self.settings = settings
        self.display_manager = DisplayManager(
            display_overrides=settings.display_overrides
        )
        self.brightness = BrightnessController(
            retries=settings.agent.ddcutil_retries,
            command_timeout=settings.agent.command_timeout,
        )

        # Display state tracking
        self.displays: dict[str, CorrelatedDisplay] = {}
        self.last_power_state: dict[str, bool] = {}
        self.last_brightness: dict[str, int] = {}

        # Shutdown coordination
        self._shutdown_event = asyncio.Event()
        self._client: Optional[aiomqtt.Client] = None

    async def run(self) -> None:
        """Main entry point - run the agent."""
        self._setup_signal_handlers()

        try:
            # Initial display discovery
            await self._discover_displays()

            if not self.displays:
                logger.error("No displays found. Exiting.")
                return

            # Run MQTT loop with reconnection
            await self._run_with_reconnect()
        except asyncio.CancelledError:
            logger.info("Agent cancelled")
        finally:
            logger.info("Agent shutdown complete")

    def _setup_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: self._handle_shutdown(s))

    def _handle_shutdown(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received {sig.name}, initiating graceful shutdown...")
        self._shutdown_event.set()

    async def _discover_displays(self) -> None:
        """Discover and correlate displays."""
        logger.info("Discovering displays...")
        correlated = await self.display_manager.correlate_displays()

        self.displays = {}
        for display in correlated:
            display_id = display.unique_id
            self.displays[display_id] = display
            logger.info(
                f"  {display.display_name}: id={display_id}, "
                f"brightness={'yes' if display.supports_brightness else 'no'}"
            )

        logger.info(f"Discovered {len(self.displays)} display(s)")

    async def _run_with_reconnect(self) -> None:
        """Run MQTT loop with exponential backoff reconnection."""
        reconnect_delay = self.settings.mqtt.reconnect_interval
        max_delay = self.settings.mqtt.reconnect_max_interval

        while not self._shutdown_event.is_set():
            try:
                await self._mqtt_loop()
                # Reset delay on successful connection
                reconnect_delay = self.settings.mqtt.reconnect_interval

            except aiomqtt.MqttError as e:
                if self._shutdown_event.is_set():
                    break

                logger.error(f"MQTT connection error: {e}")
                logger.info(f"Reconnecting in {reconnect_delay:.1f}s...")

                # Wait with shutdown check
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=reconnect_delay
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Timeout expired, try reconnecting

                # Exponential backoff with jitter
                reconnect_delay = min(reconnect_delay * 2, max_delay)
                reconnect_delay *= 0.5 + random.random()

            except Exception as e:
                logger.exception(f"Unexpected error: {e}")
                if not self._shutdown_event.is_set():
                    await asyncio.sleep(reconnect_delay)

    async def _mqtt_loop(self) -> None:
        """Connect to MQTT and handle messages."""
        mqtt = self.settings.mqtt

        password = mqtt.password.get_secret_value() if mqtt.password else None

        async with aiomqtt.Client(
            hostname=mqtt.broker,
            port=mqtt.port,
            username=mqtt.username,
            password=password,
            identifier=mqtt.client_id,
            keepalive=mqtt.keepalive,
        ) as client:
            self._client = client
            logger.info(f"Connected to MQTT broker {mqtt.broker}:{mqtt.port}")

            # Publish discovery and subscribe
            await self._publish_discovery(client)
            await self._subscribe_to_commands(client)

            # Initial state publish
            await self._poll_and_publish_state(client)

            # Handle messages and poll concurrently
            await asyncio.gather(
                self._message_handler(client),
                self._polling_loop(client),
            )

    async def _publish_discovery(self, client: aiomqtt.Client) -> None:
        """Publish Home Assistant MQTT discovery configs for all displays."""
        ha = self.settings.homeassistant

        # Shared device info
        device_info = {
            "identifiers": [ha.device_id],
            "name": ha.device_name,
            "model": "Wayland Monitor Controller",
            "manufacturer": "wlddc",
            "sw_version": __version__,
        }

        for display_id, display in self.displays.items():
            name_prefix = display.wayland.model or display.wayland.name

            # Power switch discovery
            power_config = {
                "name": f"{name_prefix} Power",
                "unique_id": f"{ha.device_id}_{display_id}_power",
                "device": device_info,
                "state_topic": f"{ha.discovery_prefix}/switch/{ha.device_id}/{display_id}/power/state",
                "command_topic": f"{ha.discovery_prefix}/switch/{ha.device_id}/{display_id}/power/set",
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:monitor",
            }
            await client.publish(
                f"{ha.discovery_prefix}/switch/{ha.device_id}/{display_id}_power/config",
                json.dumps(power_config),
                retain=True,
            )
            logger.debug(f"Published power discovery for {display_id}")

            # Brightness number (only if DDC supported)
            if display.supports_brightness:
                brightness_config = {
                    "name": f"{name_prefix} Brightness",
                    "unique_id": f"{ha.device_id}_{display_id}_brightness",
                    "device": device_info,
                    "state_topic": f"{ha.discovery_prefix}/number/{ha.device_id}/{display_id}/brightness/state",
                    "command_topic": f"{ha.discovery_prefix}/number/{ha.device_id}/{display_id}/brightness/set",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "mode": "slider",
                    "unit_of_measurement": "%",
                    "icon": "mdi:brightness-6",
                }
                await client.publish(
                    f"{ha.discovery_prefix}/number/{ha.device_id}/{display_id}_brightness/config",
                    json.dumps(brightness_config),
                    retain=True,
                )
                logger.debug(f"Published brightness discovery for {display_id}")

            # Resolution sensor
            resolution_config = {
                "name": f"{name_prefix} Resolution",
                "unique_id": f"{ha.device_id}_{display_id}_resolution",
                "device": device_info,
                "state_topic": f"{ha.discovery_prefix}/sensor/{ha.device_id}/{display_id}/resolution/state",
                "icon": "mdi:monitor-screenshot",
            }
            await client.publish(
                f"{ha.discovery_prefix}/sensor/{ha.device_id}/{display_id}_resolution/config",
                json.dumps(resolution_config),
                retain=True,
            )

        logger.info(f"Published MQTT discovery for {len(self.displays)} display(s)")

    async def _subscribe_to_commands(self, client: aiomqtt.Client) -> None:
        """Subscribe to command topics."""
        ha = self.settings.homeassistant

        # Subscribe to all command topics for our device
        await client.subscribe(
            f"{ha.discovery_prefix}/switch/{ha.device_id}/+/power/set"
        )
        await client.subscribe(
            f"{ha.discovery_prefix}/number/{ha.device_id}/+/brightness/set"
        )

        logger.debug("Subscribed to command topics")

    async def _message_handler(self, client: aiomqtt.Client) -> None:
        """Handle incoming MQTT messages."""
        async for message in client.messages:
            if self._shutdown_event.is_set():
                break

            try:
                await self._process_command(client, message)
            except Exception as e:
                logger.exception(f"Error processing message: {e}")

    async def _process_command(
        self, client: aiomqtt.Client, message: aiomqtt.Message
    ) -> None:
        """Process a single MQTT command."""
        topic = str(message.topic)
        payload = message.payload.decode() if message.payload else ""

        logger.debug(f"Received: {topic} = {payload}")

        # Parse topic to extract display_id and command type
        # Format: {prefix}/{type}/{device_id}/{display_id}/{entity}/set
        parts = topic.split("/")
        if len(parts) < 6 or parts[-1] != "set":
            return

        entity_type = parts[1]  # "switch" or "number"
        display_id = parts[3]
        entity = parts[4]  # "power" or "brightness"

        if display_id not in self.displays:
            logger.warning(f"Unknown display: {display_id}")
            return

        display = self.displays[display_id]

        if entity_type == "switch" and entity == "power":
            on = payload.upper() == "ON"
            success = await self.display_manager.set_display_power(
                display.wayland.name, on
            )
            if success:
                # Publish updated state
                await asyncio.sleep(0.5)  # Brief delay for state to settle
                await self._publish_display_state(client, display_id, display)

        elif entity_type == "number" and entity == "brightness":
            if not display.supports_brightness:
                logger.warning(f"Display {display_id} does not support brightness")
                return

            try:
                value = int(float(payload))
            except ValueError:
                logger.warning(f"Invalid brightness value: {payload}")
                return

            assert display.ddc is not None
            success = await self.brightness.set_brightness(display.ddc.i2c_bus, value)
            if success:
                await asyncio.sleep(0.5)
                await self._publish_display_state(client, display_id, display)

    async def _polling_loop(self, client: aiomqtt.Client) -> None:
        """Periodically poll and publish display state."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.settings.agent.poll_interval,
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Poll interval elapsed

            await self._poll_and_publish_state(client)

    async def _poll_and_publish_state(self, client: aiomqtt.Client) -> None:
        """Poll current state and publish to MQTT."""
        for display_id, display in self.displays.items():
            await self._publish_display_state(client, display_id, display)

    async def _publish_display_state(
        self, client: aiomqtt.Client, display_id: str, display: CorrelatedDisplay
    ) -> None:
        """Publish state for a single display."""
        ha = self.settings.homeassistant

        # Get power state
        enabled = await self.display_manager.get_display_enabled(display.wayland.name)
        if enabled is not None:
            if (
                display_id not in self.last_power_state
                or self.last_power_state[display_id] != enabled
            ):
                self.last_power_state[display_id] = enabled
                state = "ON" if enabled else "OFF"
                await client.publish(
                    f"{ha.discovery_prefix}/switch/{ha.device_id}/{display_id}/power/state",
                    state,
                    retain=True,
                )
                logger.debug(f"Published {display_id} power: {state}")

        # Get brightness (if supported)
        if display.supports_brightness and display.ddc:
            brightness = await self.brightness.get_brightness(display.ddc.i2c_bus)
            if brightness is not None:
                if (
                    display_id not in self.last_brightness
                    or self.last_brightness[display_id] != brightness
                ):
                    self.last_brightness[display_id] = brightness
                    await client.publish(
                        f"{ha.discovery_prefix}/number/{ha.device_id}/{display_id}/brightness/state",
                        str(brightness),
                        retain=True,
                    )
                    logger.debug(f"Published {display_id} brightness: {brightness}")

        # Publish resolution
        outputs = await self.display_manager.discover_wayland_outputs()
        for output in outputs:
            if output.name == display.wayland.name and output.current_mode:
                await client.publish(
                    f"{ha.discovery_prefix}/sensor/{ha.device_id}/{display_id}/resolution/state",
                    output.current_mode,
                    retain=True,
                )
                break
