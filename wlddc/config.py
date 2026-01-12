"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MQTTSettings(BaseModel):
    """MQTT broker connection settings."""

    broker: str = Field(default="localhost", description="MQTT broker hostname")
    port: int = Field(default=1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[SecretStr] = None
    client_id: str = Field(default="wlddc")
    keepalive: int = Field(default=60, ge=10, le=3600)
    reconnect_interval: float = Field(default=5.0, ge=1.0, le=300.0)
    reconnect_max_interval: float = Field(default=120.0, ge=5.0, le=600.0)


class HomeAssistantSettings(BaseModel):
    """Home Assistant integration settings."""

    discovery_prefix: str = Field(default="homeassistant")
    device_id: str = Field(default="wlddc")
    device_name: str = Field(default="Wayland Monitor Controller")


class AgentSettings(BaseModel):
    """Agent behavior settings."""

    poll_interval: float = Field(default=30.0, ge=5.0, le=300.0)
    command_timeout: float = Field(default=10.0, ge=1.0, le=60.0)
    ddcutil_retries: int = Field(default=2, ge=0, le=5)
    log_level: str = Field(default="INFO")


class DisplayOverride(BaseModel):
    """Manual display-to-DDC mapping override."""

    output_name: str  # e.g., "HDMI-A-1"
    ddc_bus: Optional[int] = None  # e.g., 7 for /dev/i2c-7
    brightness_enabled: bool = True
    power_enabled: bool = True


class Settings(BaseSettings):
    """Root configuration combining all settings."""

    model_config = SettingsConfigDict(
        env_prefix="WLDDC_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    homeassistant: HomeAssistantSettings = Field(default_factory=HomeAssistantSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    display_overrides: list[DisplayOverride] = Field(default_factory=list)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from env vars and optional YAML file.

        Priority: Environment variables override YAML file values.
        """
        yaml_data: dict = {}

        # Try to load from YAML file
        if config_path and config_path.exists():
            with open(config_path) as f:
                yaml_data = yaml.safe_load(f) or {}
        else:
            # Check default locations
            default_paths = [
                Path.home() / ".config" / "wlddc" / "config.yaml",
                Path.home() / ".config" / "wlddc" / "config.yml",
                Path("config.yaml"),
                Path("config.yml"),
            ]
            for path in default_paths:
                if path.exists():
                    with open(path) as f:
                        yaml_data = yaml.safe_load(f) or {}
                    break

        # Build nested settings from YAML
        mqtt_data = yaml_data.get("mqtt", {})
        ha_data = yaml_data.get("homeassistant", {})
        agent_data = yaml_data.get("agent", {})
        overrides_data = yaml_data.get("display_overrides", [])

        # Create settings - pydantic-settings will overlay env vars automatically
        return cls(
            mqtt=MQTTSettings(**mqtt_data),
            homeassistant=HomeAssistantSettings(**ha_data),
            agent=AgentSettings(**agent_data),
            display_overrides=[DisplayOverride(**o) for o in overrides_data],
        )
