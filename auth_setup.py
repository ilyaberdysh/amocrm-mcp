#!/usr/bin/env python3
"""
One-time CLI script to authorize AmoCRM and save tokens to ~/.amocrm/config.json.

Usage:
    python3 auth_setup.py

What it does:
    1. Prompts for subdomain, client_id, client_secret, redirect_uri
    2. Opens the AmoCRM authorization URL in browser (or prints it)
    3. Prompts for the auth_code from the redirect
    4. Exchanges code for tokens
    5. Saves everything to ~/.amocrm/config.json
"""
from __future__ import annotations

import sys
import webbrowser
from urllib.parse import urlencode

from amocrm_client import exchange_auth_code
from config import save_config


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("=" * 60)
    print("  AmoCRM MCP Server — первичная авторизация")
    print("=" * 60)
    print()

    subdomain = prompt("Субдомен AmoCRM (например: mycompany)")
    if not subdomain:
        print("Ошибка: субдомен обязателен.")
        sys.exit(1)

    client_id = prompt("Client ID интеграции")
    if not client_id:
        print("Ошибка: client_id обязателен.")
        sys.exit(1)

    client_secret = prompt("Client Secret интеграции")
    if not client_secret:
        print("Ошибка: client_secret обязателен.")
        sys.exit(1)

    redirect_uri = prompt("Redirect URI", default="https://localhost")

    # Build auth URL
    auth_params = urlencode({
        "client_id": client_id,
        "state": "amocrm_mcp_setup",
        "mode": "post_message",
    })
    auth_url = f"https://{subdomain}.amocrm.ru/oauth?{auth_params}"

    print()
    print("─" * 60)
    print("Открываю браузер для авторизации...")
    print(f"URL: {auth_url}")
    print()
    print("Если браузер не открылся — скопируй URL выше и открой вручную.")
    print("После авторизации ты будешь перенаправлен на redirect_uri.")
    print("Скопируй параметр 'code' из URL редиректа.")
    print("─" * 60)
    print()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass  # headless environment, user will open manually

    auth_code = prompt("Вставь auth_code из URL редиректа")
    if not auth_code:
        print("Ошибка: auth_code обязателен.")
        sys.exit(1)

    print()
    print("Обмениваем код на токены...")

    try:
        tokens = exchange_auth_code(
            subdomain=subdomain,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            auth_code=auth_code,
        )
    except ValueError as e:
        print(f"\nОшибка авторизации: {e}")
        print("\nПроверь:")
        print("  • client_id и client_secret скопированы без пробелов")
        print("  • redirect_uri совпадает с настройками интеграции в AmoCRM")
        print("  • auth_code не устарел (действует ~20 секунд после редиректа)")
        sys.exit(1)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token or not refresh_token:
        print(f"Ошибка: сервер вернул неожиданный ответ: {tokens}")
        sys.exit(1)

    config = {
        "subdomain": subdomain,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }

    save_config(config)

    print()
    print("=" * 60)
    print("  Готово! Токены сохранены.")
    print("=" * 60)
    print()
    print("Следующий шаг — добавить MCP сервер в Claude Desktop.")
    print("Смотри README.md для инструкции.")
    print()


if __name__ == "__main__":
    main()
