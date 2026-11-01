"""
Configuration loader for YouTube Auto Video Comment Bot.

Loads settings from YAML configuration files with validation
and default fallbacks.
"""

import os
import yaml


# Default configuration values
DEFAULTS = {
    "youtube_api": {
        "api_key": "",
        "client_secrets_file": "config/client_secrets.json",
        "token_file": "config/token.json",
        "scopes": ["https://www.googleapis.com/auth/youtube.force-ssl"],
    },
    "rate_limits": {
        "min_delay_between_comments": 30,
        "max_comments_per_session": 50,
    },
    "logging": {
        "log_file": "logs/activity.log",
        "log_level": "INFO",
    },
    "output": {
        "posted_comments_file": "output/posted_comments.json",
        "report_file": "output/report.csv",
    },
}


class ConfigLoader:
    """Loads and provides access to bot configuration."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        """
        Initialize the config loader.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config_path = config_path
        self.config = dict(DEFAULTS)
        self._load()

    def _load(self):
        """Load configuration from YAML file, merging with defaults."""
        if not os.path.exists(self.config_path):
            print(f"[WARNING] Config file not found: {self.config_path}")
            print("[WARNING] Using default configuration.")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"[ERROR] Failed to parse config file: {e}")
            print("[WARNING] Using default configuration.")
            return

        # Deep merge user config into defaults
        self.config = self._deep_merge(DEFAULTS, user_config)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override dict into base dict."""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, *keys, default=None):
        """
        Get a nested configuration value using dot-style key traversal.

        Args:
            *keys: Sequence of keys to traverse.
            default: Default value if key path not found.

        Returns:
            The configuration value, or default.

        Example:
            config.get("youtube_api", "api_key")
        """
        current = self.config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def validate(self) -> list[str]:
        """
        Validate the configuration and return a list of issues.

        Returns:
            List of validation error messages (empty if all valid).
        """
        issues = []

        api_key = self.get("youtube_api", "api_key", default="")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            issues.append(
                "YouTube API key is not configured. "
                "Set 'youtube_api.api_key' in config/settings.yaml"
            )

        client_secrets = self.get("youtube_api", "client_secrets_file", default="")
        if not os.path.exists(client_secrets):
            issues.append(
                f"OAuth client secrets file not found: {client_secrets}. "
                "Download it from Google Cloud Console."
            )

        return issues
