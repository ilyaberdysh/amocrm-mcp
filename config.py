"""
Config management for AmoCRM MCP server.
Tokens stored in ~/.amocrm/config.json — auto-saved on refresh.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".amocrm" / "config.json"

REQUIRED_FIELDS = ["subdomain", "client_id", "client_secret", "redirect_uri", "access_token", "refresh_token"]


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"AmoCRM config not found at {CONFIG_PATH}\n"
            "Run: python3 auth_setup.py"
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    missing = [k for k in REQUIRED_FIELDS if not config.get(k)]
    if missing:
        raise ValueError(f"Missing fields in config: {missing}")
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def save_tokens(access_token: str, refresh_token: str) -> None:
    """Called by AmoCRMClient when tokens are refreshed."""
    config = load_config()
    config["access_token"] = access_token
    config["refresh_token"] = refresh_token
    save_config(config)
