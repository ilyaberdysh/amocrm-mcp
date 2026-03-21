# AmoCRM MCP Server

MCP-сервер для [AmoCRM](https://www.amocrm.ru/). Подключается к Claude Desktop и даёт Claude прямой доступ к вашей CRM через 17 инструментов.

Задавайте вопросы на русском — Claude сам вызовет нужные API и скомбинирует ответ.

## Архитектура

```
┌──────────────────┐     stdin/stdout      ┌──────────────────┐     HTTPS      ┌──────────────┐
│  Claude Desktop  │ ◄──── MCP Protocol ──► │  amocrm-mcp      │ ◄── REST ───► │  AmoCRM API  │
│  (LLM + UI)      │                        │  (локальный)      │                │  (облако)    │
└──────────────────┘                        └──────────────────┘                └──────────────┘
```

**Как это работает:**

1. Claude Desktop запускает `amocrm-mcp` как subprocess
2. MCP-сервер сообщает Claude: "у меня 17 инструментов — get_leads, get_contacts..."
3. Пользователь пишет вопрос на русском
4. Claude решает какие инструменты вызвать и в каком порядке
5. MCP-сервер передаёт запросы в AmoCRM API v4, возвращает JSON
6. Claude анализирует данные и отвечает пользователю

Внутри MCP-сервера нет ИИ — это прокси между Claude и AmoCRM.

## Установка

### Вариант A: pip (рекомендуется)

```bash
pip install amocrm-mcp
```

### Вариант B: из исходников

```bash
git clone https://github.com/ilyaberdysh/amocrm-mcp.git
cd amocrm-mcp
pip install -e .
```

## Настройка

### 1. Создать интеграцию в AmoCRM

1. AmoCRM → **Настройки** → **Интеграции** → **Создать интеграцию**
2. Тип: **Внешняя интеграция**
3. Redirect URI: `https://localhost`
4. Скопировать **Client ID** и **Client Secret**

### 2. Авторизоваться

```bash
amocrm-mcp-auth
```

Или если установлено из исходников:

```bash
python3 auth_setup.py
```

Скрипт спросит:
- **Субдомен** — часть URL вашего AmoCRM (например `mycompany` из `mycompany.amocrm.ru`)
- **Client ID** и **Client Secret** — из шага 1
- **Redirect URI** — по умолчанию `https://localhost`
- **Auth code** — откроется URL, авторизуетесь, скопируете `code` из URL редиректа

Токены сохранятся в `~/.amocrm/config.json`.

### 3. Подключить к Claude Desktop

Откройте файл конфигурации:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Добавьте:

```json
{
  "mcpServers": {
    "amocrm": {
      "command": "amocrm-mcp"
    }
  }
}
```

> Если установлено из исходников, укажите полный путь:
> ```json
> {"command": "python3", "args": ["/путь/до/amocrm-mcp/server.py"]}
> ```

### 4. Перезапустить Claude Desktop

**Cmd+Q** (Mac) / **Alt+F4** (Windows) → открыть заново.

В чате появится иконка инструментов — `amocrm` с 17 тулами.

### 5. Проверить

```
Покажи мои воронки в AmoCRM
```

## Инструменты (17)

| Инструмент | Что делает |
|------------|-----------|
| `get_pipelines` | Воронки продаж с этапами и их ID |
| `get_leads` | Сделки с фильтрами (менеджер, воронка, статус, даты, сумма) |
| `count_and_sum_leads` | Подсчёт и сумма сделок **без лимита 200** — для аналитики |
| `get_contacts` | Контакты (поиск по имени, email, телефону) |
| `get_companies` | Компании |
| `get_users` | Пользователи / менеджеры |
| `get_tasks` | Задачи (активные/выполненные, сортировка по дедлайну) |
| `get_notes` | Примечания к сделкам, контактам, компаниям |
| `get_events` | Журнал событий (смена этапов, создание сделок) |
| `get_customers` | Покупатели (повторные клиенты) |
| `get_unsorted` | Неразобранные заявки |
| `get_catalogs` | Каталоги товаров/услуг |
| `get_catalog_elements` | Элементы каталогов |
| `get_custom_fields` | Пользовательские поля сущностей |
| `get_loss_reasons` | Причины отказа |
| `get_tags` | Теги |
| `get_sources` | Источники трафика |

## Примеры запросов

```
Сколько сделок закрыто в феврале 2025?
Сравни продажи за этот и прошлый месяц
Кто из менеджеров закрыл больше всего сделок?
Покажи просроченные задачи Никиты
Сделки на этапе "Переговоры" во всех воронках
Найди сделки дороже 500 000 ₽ в работе
Сколько неразобранных заявок?
Какие кастомные поля есть у сделок?
Причины отказа по проигранным сделкам
```

## Структура проекта

```
amocrm-mcp/
├── server.py           # MCP-сервер — точка входа, 17 tool definitions
├── amocrm_client.py    # AmoCRM API v4 клиент
│                         - OAuth2 с auto-refresh токенов
│                         - Retry на 429 (rate limit) с backoff 2s/5s/10s
│                         - Пагинация до 10 000 записей
│                         - Обработка пустых ответов API
├── config.py           # Чтение/запись ~/.amocrm/config.json
├── auth_setup.py       # CLI для первичной OAuth2 авторизации
├── pyproject.toml      # Метаданные, зависимости, entry points
└── QA_TEST_PROMPT.md   # QA-промпт для тестирования (10 вопросов)
```

## Токены

- Хранятся в `~/.amocrm/config.json`
- Обновляются автоматически при каждом запросе
- Протухают если не использовать > 3 месяцев
- Если протухли — снова запустите `amocrm-mcp-auth`

## Отладка

```bash
# Проверить что сервер запускается
amocrm-mcp
# Если висит без ошибок — ждёт подключения (Ctrl+C для выхода)

# Проверить конфиг
cat ~/.amocrm/config.json

# Логи Claude Desktop
# Mac: ~/Library/Logs/Claude/
# Windows: %APPDATA%\Claude\logs\
```

## Требования

- Python 3.11+
- Claude Desktop
- Аккаунт AmoCRM с правами создания интеграций

## Технологии

- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) — Model Context Protocol
- AmoCRM API v4 (OAuth2)
- Без внешних HTTP-библиотек — `urllib` из stdlib

## Лицензия

MIT
