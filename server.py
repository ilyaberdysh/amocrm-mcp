"""
AmoCRM MCP Server.
Exposes AmoCRM API as MCP tools for Claude Desktop / Claude Code.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from amocrm_client import AmoCRMClient
from config import load_config, save_tokens

server = Server("amocrm")


def _get_client() -> AmoCRMClient:
    """Load config and build client with auto-save on token refresh."""
    cfg = load_config()
    return AmoCRMClient(
        subdomain=cfg["subdomain"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=cfg["redirect_uri"],
        access_token=cfg["access_token"],
        refresh_token=cfg["refresh_token"],
        on_token_refresh=save_tokens,
    )


def _ok(data: object) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


def _err(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))]


# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_pipelines",
        description="Возвращает все воронки продаж с этапами и их ID. Вызывай ПЕРВЫМ когда нужен pipeline_id или status_id для этапа.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_leads",
        description=(
            "Получает сделки из CRM с фильтрами. Все даты — unix timestamp (секунды). "
            "Используй closed_at_from/closed_at_to для фильтра по дате ЗАКРЫТИЯ. "
            "date_from/date_to — только для даты СОЗДАНИЯ. "
            "Максимум 200 записей за запрос. "
            "ВНИМАНИЕ: фильтры price_from/price_to могут конфликтовать с status_ids — "
            "для фильтрации активных сделок по цене используй count_and_sum_leads с exclude_closed=true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "integer", "description": "ID воронки"},
                "status_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID этапов/статусов (получи из get_pipelines)"},
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID ответственных менеджеров"},
                "created_by": {"type": "array", "items": {"type": "integer"}, "description": "ID пользователей, создавших сделку"},
                "date_from": {"type": "integer", "description": "Начало периода по дате СОЗДАНИЯ (unix timestamp)"},
                "date_to": {"type": "integer", "description": "Конец периода по дате СОЗДАНИЯ (unix timestamp)"},
                "updated_at_from": {"type": "integer", "description": "Начало периода по дате ИЗМЕНЕНИЯ (unix timestamp)"},
                "updated_at_to": {"type": "integer", "description": "Конец периода по дате ИЗМЕНЕНИЯ (unix timestamp)"},
                "closed_at_from": {"type": "integer", "description": "Начало периода по дате ЗАКРЫТИЯ (unix timestamp). Для 'сделки закрытые в марте'."},
                "closed_at_to": {"type": "integer", "description": "Конец периода по дате ЗАКРЫТИЯ (unix timestamp)"},
                "price_from": {"type": "integer", "description": "Минимальная сумма сделки"},
                "price_to": {"type": "integer", "description": "Максимальная сумма сделки"},
                "query": {"type": "string", "description": "Поиск по названию сделки"},
                "order_by": {"type": "string", "enum": ["created_at", "updated_at", "id", "price"], "description": "Поле сортировки"},
                "order_dir": {"type": "string", "enum": ["asc", "desc"], "description": "Направление сортировки"},
                "with_contacts": {"type": "boolean", "description": "Включить связанные контакты"},
                "with_companies": {"type": "boolean", "description": "Включить связанные компании"},
                "with_loss_reason": {"type": "boolean", "description": "Включить причину отказа"},
                "with_tasks": {"type": "boolean", "description": "Включить задачи по сделке"},
                "with_catalog_elements": {"type": "boolean", "description": "Включить товары из каталога"},
                "limit": {"type": "integer", "description": "Максимум сделок (по умолчанию 200, это максимум API)"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="count_and_sum_leads",
        description=(
            "Подсчитывает количество и общую сумму сделок по фильтрам БЕЗ лимита в 200 записей. "
            "Возвращает {count, total_price, by_pipeline: [{pipeline_id, count, total_price}]}. "
            "ИСПОЛЬЗУЙ ЭТОТ ИНСТРУМЕНТ (а не get_leads) для: подсчёта количества сделок, "
            "суммы продаж, сравнения периодов, ответов на 'сколько всего сделок'. "
            "Параметр exclude_closed=true исключает закрытые сделки (выигранные 142 и проигранные 143) — "
            "используй для подсчёта АКТИВНЫХ сделок."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "integer", "description": "ID воронки"},
                "status_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID этапов/статусов"},
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID ответственных менеджеров"},
                "created_by": {"type": "array", "items": {"type": "integer"}, "description": "ID создателей сделки"},
                "date_from": {"type": "integer", "description": "Дата создания от (unix timestamp)"},
                "date_to": {"type": "integer", "description": "Дата создания до (unix timestamp)"},
                "updated_at_from": {"type": "integer", "description": "Дата изменения от (unix timestamp)"},
                "updated_at_to": {"type": "integer", "description": "Дата изменения до (unix timestamp)"},
                "closed_at_from": {"type": "integer", "description": "Дата закрытия от (unix timestamp)"},
                "closed_at_to": {"type": "integer", "description": "Дата закрытия до (unix timestamp)"},
                "price_from": {"type": "integer", "description": "Минимальная сумма"},
                "price_to": {"type": "integer", "description": "Максимальная сумма"},
                "query": {"type": "string", "description": "Поиск по названию"},
                "exclude_closed": {"type": "boolean", "description": "true = исключить закрытые (выигранные + проигранные), оставить только АКТИВНЫЕ сделки"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_contacts",
        description="Поиск и получение контактов с фильтрами.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поиск по имени, email, телефону"},
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID менеджеров"},
                "created_at_from": {"type": "integer", "description": "Дата создания от (unix timestamp)"},
                "created_at_to": {"type": "integer", "description": "Дата создания до (unix timestamp)"},
                "updated_at_from": {"type": "integer", "description": "Дата изменения от (unix timestamp)"},
                "updated_at_to": {"type": "integer", "description": "Дата изменения до (unix timestamp)"},
                "with_leads": {"type": "boolean", "description": "Включить сделки контакта"},
                "with_customers": {"type": "boolean", "description": "Включить покупателей"},
                "limit": {"type": "integer", "description": "Максимум записей"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_companies",
        description="Поиск и получение компаний.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поиск по названию компании"},
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID менеджеров"},
                "created_at_from": {"type": "integer", "description": "Дата создания от (unix timestamp)"},
                "created_at_to": {"type": "integer", "description": "Дата создания до (unix timestamp)"},
                "updated_at_from": {"type": "integer", "description": "Дата изменения от (unix timestamp)"},
                "updated_at_to": {"type": "integer", "description": "Дата изменения до (unix timestamp)"},
                "with_leads": {"type": "boolean", "description": "Включить сделки компании"},
                "with_contacts": {"type": "boolean", "description": "Включить контакты компании"},
                "limit": {"type": "integer", "description": "Максимум записей"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_notes",
        description="Заметки и комментарии к сделкам, контактам или компаниям. Содержит записи менеджеров, результаты звонков.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "enum": ["leads", "contacts", "companies", "customers"], "description": "Тип сущности (по умолчанию leads)"},
                "entity_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID конкретных сущностей"},
                "note_types": {"type": "array", "items": {"type": "string"}, "description": "Типы: common, call_in, call_out, service_message, mail_message"},
                "created_at_from": {"type": "integer", "description": "Дата создания от (unix timestamp)"},
                "created_at_to": {"type": "integer", "description": "Дата создания до (unix timestamp)"},
                "limit": {"type": "integer", "description": "Максимум записей"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_customers",
        description="Покупатели (повторные клиенты / подписки). Используй если в аккаунте включён модуль Покупатели.",
        inputSchema={
            "type": "object",
            "properties": {
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID менеджеров"},
                "created_at_from": {"type": "integer"},
                "created_at_to": {"type": "integer"},
                "updated_at_from": {"type": "integer"},
                "updated_at_to": {"type": "integer"},
                "with_contacts": {"type": "boolean"},
                "with_companies": {"type": "boolean"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_unsorted",
        description="Неразобранные заявки — входящие лиды, ещё не попавшие в воронку.",
        inputSchema={
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "integer", "description": "ID воронки"},
                "category": {"type": "string", "enum": ["sip", "mail", "chats", "forms"]},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_catalogs",
        description="Список каталогов товаров/услуг. Используй чтобы получить catalog_id для get_catalog_elements.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_catalog_elements",
        description="Товары или услуги из каталога.",
        inputSchema={
            "type": "object",
            "properties": {
                "catalog_id": {"type": "integer", "description": "ID каталога (из get_catalogs)"},
                "query": {"type": "string", "description": "Поиск по названию"},
                "limit": {"type": "integer"},
            },
            "required": ["catalog_id"],
        },
    ),
    types.Tool(
        name="get_events",
        description=(
            "История событий: смена этапов, создание и удаление сделок и контактов. "
            "Принимает entity_type как leads/contacts/companies (автоматически конвертируется в формат API)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "enum": ["leads", "contacts", "companies"], "description": "Тип сущности (leads, contacts, companies)"},
                "event_types": {"type": "array", "items": {"type": "string"}, "description": "Типы: lead_added, lead_status_changed, lead_deleted, contact_added, company_added и др."},
                "date_from": {"type": "integer", "description": "Начало периода (unix timestamp)"},
                "date_to": {"type": "integer", "description": "Конец периода (unix timestamp)"},
                "limit": {"type": "integer", "description": "Максимум записей (по умолчанию 100)"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_tasks",
        description=(
            "Задачи менеджеров. По умолчанию возвращает АКТИВНЫЕ задачи (is_completed=false). "
            "Передай is_completed=true для завершённых."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "responsible_user_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID менеджеров"},
                "is_completed": {"type": "boolean", "description": "false — активные (по умолчанию), true — завершённые"},
                "date_from": {"type": "integer", "description": "Дата создания от (unix timestamp)"},
                "date_to": {"type": "integer", "description": "Дата создания до (unix timestamp)"},
                "complete_till_from": {"type": "integer", "description": "Дедлайн от (unix timestamp)"},
                "complete_till_to": {"type": "integer", "description": "Дедлайн до (unix timestamp)"},
                "order_by": {"type": "string", "description": "Поле сортировки: complete_till (по умолчанию), created_at, updated_at, id"},
                "order_dir": {"type": "string", "enum": ["asc", "desc"], "description": "Направление сортировки (по умолчанию asc — просроченные первыми)"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_users",
        description="Список менеджеров/пользователей CRM с группами.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_custom_fields",
        description="Кастомные поля сущности — их ID и названия. Используй чтобы понять как фильтровать по ним.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {"type": "string", "enum": ["leads", "contacts", "companies", "customers"], "description": "Тип сущности"},
            },
            "required": ["entity"],
        },
    ),
    types.Tool(
        name="get_loss_reasons",
        description="Причины отказа по проигранным сделкам.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_tags",
        description="Теги для сущности.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {"type": "string", "enum": ["leads", "contacts", "companies", "customers"]},
            },
            "required": ["entity"],
        },
    ),
    types.Tool(
        name="get_sources",
        description="Источники трафика/лидов.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


# ── Handlers ───────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        client = _get_client()
        result = await asyncio.to_thread(_execute, name, arguments, client)
        return _ok(result)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")


def _execute(name: str, args: dict, client: AmoCRMClient) -> object:
    """Dispatch tool call to AmoCRM client (runs in thread)."""
    if name == "get_pipelines":
        return client.get_pipelines()

    if name == "get_leads":
        return client.get_leads(
            pipeline_id=args.get("pipeline_id"),
            status_ids=args.get("status_ids"),
            responsible_user_ids=args.get("responsible_user_ids"),
            created_by=args.get("created_by"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            closed_at_from=args.get("closed_at_from"),
            closed_at_to=args.get("closed_at_to"),
            price_from=args.get("price_from"),
            price_to=args.get("price_to"),
            query=args.get("query"),
            order_by=args.get("order_by"),
            order_dir=args.get("order_dir", "desc"),
            with_contacts=args.get("with_contacts", False),
            with_companies=args.get("with_companies", False),
            with_loss_reason=args.get("with_loss_reason", False),
            with_tasks=args.get("with_tasks", False),
            with_catalog_elements=args.get("with_catalog_elements", False),
            limit=args.get("limit", 200),
        )

    if name == "count_and_sum_leads":
        return client.count_and_sum_leads(
            pipeline_id=args.get("pipeline_id"),
            status_ids=args.get("status_ids"),
            responsible_user_ids=args.get("responsible_user_ids"),
            created_by=args.get("created_by"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            closed_at_from=args.get("closed_at_from"),
            closed_at_to=args.get("closed_at_to"),
            price_from=args.get("price_from"),
            price_to=args.get("price_to"),
            query=args.get("query"),
            exclude_closed=args.get("exclude_closed", False),
        )

    if name == "get_contacts":
        return client.get_contacts(
            query=args.get("query", ""),
            responsible_user_ids=args.get("responsible_user_ids"),
            created_at_from=args.get("created_at_from"),
            created_at_to=args.get("created_at_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            with_leads=args.get("with_leads", False),
            with_customers=args.get("with_customers", False),
            limit=args.get("limit", 200),
        )

    if name == "get_companies":
        return client.get_companies(
            query=args.get("query", ""),
            responsible_user_ids=args.get("responsible_user_ids"),
            created_at_from=args.get("created_at_from"),
            created_at_to=args.get("created_at_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            with_leads=args.get("with_leads", False),
            with_contacts=args.get("with_contacts", False),
            limit=args.get("limit", 200),
        )

    if name == "get_notes":
        return client.get_notes(
            entity_type=args.get("entity_type", "leads"),
            entity_ids=args.get("entity_ids"),
            note_types=args.get("note_types"),
            created_at_from=args.get("created_at_from"),
            created_at_to=args.get("created_at_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            limit=args.get("limit", 200),
        )

    if name == "get_customers":
        return client.get_customers(
            responsible_user_ids=args.get("responsible_user_ids"),
            created_at_from=args.get("created_at_from"),
            created_at_to=args.get("created_at_to"),
            updated_at_from=args.get("updated_at_from"),
            updated_at_to=args.get("updated_at_to"),
            with_contacts=args.get("with_contacts", False),
            with_companies=args.get("with_companies", False),
            limit=args.get("limit", 200),
        )

    if name == "get_unsorted":
        return client.get_unsorted(
            pipeline_id=args.get("pipeline_id"),
            category=args.get("category"),
            limit=args.get("limit", 200),
        )

    if name == "get_catalogs":
        return client.get_catalogs()

    if name == "get_catalog_elements":
        return client.get_catalog_elements(
            catalog_id=args["catalog_id"],
            query=args.get("query", ""),
            limit=args.get("limit", 200),
        )

    if name == "get_events":
        return client.get_events(
            entity_type=args.get("entity_type"),
            event_types=args.get("event_types"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            limit=args.get("limit", 200),
        )

    if name == "get_tasks":
        is_completed = args.get("is_completed")
        if is_completed is None:
            is_completed = False  # по умолчанию — активные задачи
        return client.get_tasks(
            responsible_user_ids=args.get("responsible_user_ids"),
            is_completed=is_completed,
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            complete_till_from=args.get("complete_till_from"),
            complete_till_to=args.get("complete_till_to"),
            order_by=args.get("order_by", "complete_till"),
            order_dir=args.get("order_dir", "asc"),
            limit=args.get("limit", 200),
        )

    if name == "get_users":
        return client.get_users()

    if name == "get_custom_fields":
        return client.get_custom_fields(entity=args.get("entity", "leads"))

    if name == "get_loss_reasons":
        return client.get_loss_reasons()

    if name == "get_tags":
        return client.get_tags(entity=args.get("entity", "leads"))

    if name == "get_sources":
        return client.get_sources()

    raise ValueError(f"Unknown tool: {name}")


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
