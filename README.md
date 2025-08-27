# 🤖 Telegram AI Assistant

Полнофункциональный Telegram-бот-ассистент на OpenAI с монетизацией, админ-панелью и WebApp интерфейсом.

## ✨ Возможности

- **💬 Диалоги с ChatGPT**: Стриминговые ответы, история переписки
- **💰 Монетизация**: Подписки и разовые пакеты через Telegram Stars и ЮMoney
- **🎯 Триал система**: 30 бесплатных запросов для новых пользователей
- **📊 Админ-панель**: WebApp с аналитикой и управлением
- **🎨 Современный UI**: Адаптивный интерфейс с темной темой
- **🔒 Безопасность**: Валидация платежей, анти-абуз система

## 🏗️ Архитектура

```
[User] → Telegram Bot → (WebApp UI) → Backend(FastAPI) → OpenAI API
                              ↓
                    Payments(Telegram Stars, YooKassa)
                              ↓
                    DB(Postgres) + Redis(Cache/Queue)
```

## 🚀 Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-username/telegram-ai-assistant.git
cd telegram-ai-assistant
```

### 2. Настройка окружения

Скопируйте файл конфигурации:
```bash
cp env.example .env
```

Отредактируйте `.env` файл:
```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
APP_BASE_URL=https://your.domain.com

# OpenAI
OPENAI_API_KEY=sk-your_openai_api_key_here
OPENAI_DEFAULT_MODEL=gpt-4o-mini

# Database
DB_URL=postgresql+asyncpg://user:password@localhost:5432/telegram_bot_db
REDIS_URL=redis://localhost:6379/0

# Payments
YOOMONEY_SHOP_ID=your_shop_id
YOOMONEY_SECRET_KEY=your_secret_key
YOOMONEY_RETURN_URL=https://your.domain.com/pay/thanks
YOOMONEY_WEBHOOK_SECRET=your_webhook_secret

# Admin
ADMIN_USER_IDS=123456789,987654321

# Security
SECRET_KEY=your_secret_key_for_encryption
WEBHOOK_SECRET=your_webhook_secret
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка базы данных

```bash
# Создайте базу данных PostgreSQL
createdb telegram_bot_db

# Инициализируйте таблицы (автоматически при первом запуске)
python -c "from app.database.connection import init_db; import asyncio; asyncio.run(init_db())"
```

### 5. Запуск приложения

#### Разработка
```bash
# Запуск API сервера
python main.py

# В другом терминале - запуск бота
python bot.py
```

#### Продакшн с Docker
```bash
docker-compose up -d
```

## 📋 Настройка бота

### 1. Создание бота в Telegram

1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен в `.env` файл

### 2. Настройка WebApp

1. Отправьте команду `/setmenubutton` BotFather
2. Выберите вашего бота
3. Установите URL: `https://your.domain.com/webapp/chat`

### 3. Настройка платежей

#### Telegram Stars
1. Обратитесь к [@BotFather](https://t.me/BotFather)
2. Отправьте `/payments`
3. Выберите провайдера платежей
4. Настройте цены в `.env` файле

#### ЮMoney/ЮKassa
1. Зарегистрируйтесь на [yookassa.ru](https://yookassa.ru)
2. Получите Shop ID и Secret Key
3. Настройте webhook URL: `https://your.domain.com/api/payments/yoomoney/webhook`
4. Добавьте данные в `.env` файл

## 🎯 Пользовательские сценарии

### 1. Онбординг
- Пользователь отправляет `/start`
- Получает 30 бесплатных запросов
- Видит кнопки "Открыть чат" и "Мои лимиты"

### 2. Диалог
- Пользователь открывает WebApp
- Отправляет сообщение
- Получает стриминговый ответ от AI
- Списывается 1 запрос из квоты

### 3. Исчерпание триала
- Показывается пэйволл с тарифами
- Кнопки оплаты Stars/ЮMoney
- Выбор подходящего плана

### 4. Подписка
- Оплата через выбранный способ
- Автоматическое начисление квоты
- Активация PRO преимуществ

## 🔧 Админ-команды

```bash
/admin          # Открыть админ-панель
/give <id> <n>  # Выдать n запросов пользователю
/revoke <id>    # Отозвать доступ
/find <query>   # Поиск пользователя
/stats          # Статистика
/ban <id>       # Забанить пользователя
/unban <id>     # Разбанить пользователя
```

## 📊 API Endpoints

### Чат
- `POST /api/chat/send` - Отправить сообщение
- `POST /api/chat/stream` - Стриминг ответа
- `GET /api/chat/dialogs` - Список диалогов
- `GET /api/chat/dialogs/{id}/messages` - Сообщения диалога

### Платежи
- `GET /api/payments/plans` - Доступные планы
- `POST /api/payments/create-yoomoney` - Создать платеж
- `POST /api/payments/yoomoney/webhook` - Webhook ЮMoney

### Админ
- `GET /api/admin/stats/users` - Статистика пользователей
- `GET /api/admin/stats/revenue` - Статистика выручки
- `GET /api/admin/users` - Список пользователей
- `POST /api/admin/users/{id}/ban` - Забанить пользователя

## 🏗️ Структура проекта

```
telegram-ai-assistant/
├── app/
│   ├── api/                 # FastAPI роутеры
│   ├── bot/                 # Telegram бот
│   ├── database/            # Модели и подключение БД
│   ├── services/            # Бизнес-логика
│   └── templates/           # WebApp шаблоны
├── main.py                  # Точка входа API
├── bot.py                   # Точка входа бота
├── requirements.txt         # Зависимости
├── docker-compose.yml       # Docker конфигурация
└── README.md               # Документация
```

## 🔒 Безопасность

- Все секреты хранятся в `.env` файле
- Валидация webhook подписей
- Анти-дублирование платежей
- Rate limiting и анти-абуз
- Шифрование пользовательских данных

## 📈 Мониторинг

- Структурированные логи (JSON)
- Health check endpoints
- Prometheus метрики
- Sentry интеграция

## 🚀 Деплой

### Docker Compose (рекомендуется)

```bash
# Продакшн
docker-compose -f docker-compose.yml up -d

# С nginx
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

### Ручной деплой

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка базы данных
python -c "from app.database.connection import init_db; import asyncio; asyncio.run(init_db())"

# Запуск с gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Запуск бота
python bot.py
```

## 🧪 Тестирование

```bash
# Установка тестовых зависимостей
pip install pytest pytest-asyncio

# Запуск тестов
pytest tests/

# Покрытие кода
pytest --cov=app tests/
```

## 📝 Лицензия

MIT License - см. файл [LICENSE](LICENSE)

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Добавьте тесты
5. Создайте Pull Request

## 📞 Поддержка

- Создайте [Issue](https://github.com/your-username/telegram-ai-assistant/issues)
- Напишите на email: support@your-domain.com
- Telegram: @your_support_bot

## 🔄 Обновления

Следите за [релизами](https://github.com/your-username/telegram-ai-assistant/releases) для получения обновлений.

---

**Создано с ❤️ для Telegram сообщества**
