# Публикация Destination Tickets

Эта конфигурация размещает приложение на отдельном Linux-сервере: Caddy (HTTPS), FastAPI/React и PostgreSQL. Компьютер менеджера после этого не нужен для работы сайта. Docker и доступ SSH должны быть настроены на сервере заранее.

## Подготовка

1. Выберите сервер и домен/поддомен. Создайте A-запись домена с публичным IPv4 сервера. Если задаёте AAAA, IPv6 тоже должен вести на сервер.
2. Разрешите входящие TCP 80/443 и SSH. Порты приложения 8000 и базы 5432 наружу не публикуются. Если сервер уже обслуживает другие сайты на 80/443, конфигурацию нужно адаптировать к его reverse proxy.
3. Клонируйте приватный репозиторий с авторизацией вашего аккаунта:

```sh
git clone https://github.com/fl3x-png/Dest-tickets.git
cd Dest-tickets
cp .env.production.example .env.production
chmod 600 .env.production
```

Заполните `.env.production`: домен без протокола, случайный POSTGRES_PASSWORD из 64 шестнадцатеричных символов. Шестнадцатеричный пароль корректно включается в URL подключения. Не публикуйте этот файл. Пустой пароль приводит к отказу запуска Compose.

## Запуск

Все команды ниже выполняются из корня проекта на сервере:

```sh
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml up -d --build
docker compose --env-file .env.production -f compose.production.yml ps
docker compose --env-file .env.production -f compose.production.yml exec app python -m backend.cli create-admin --username admin
```

Caddy автоматически запрашивает сертификат. Для этого домен должен разрешаться на сервер, а порты 80/443 быть доступны из интернета. После запуска откройте `https://ВАШ_ДОМЕН`, войдите, создайте тестовое мероприятие и проверьте выдачу/повторное скачивание трёх билетов.

База на сервере новая: локальные пользователи и билеты автоматически не переносятся. Если в локальной БД уже есть рабочие регистрации, сначала согласуйте перенос с сохранением номеров; не выдавайте новые рабочие билеты параллельно в двух независимых базах.

## Обновление

Сначала сделайте резервную копию. Затем:

```sh
git pull --ff-only
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

Миграции выполняются при старте приложения. Конфигурация рассчитана на один экземпляр app. Docker должен быть включён при старте ОС; контейнеры имеют `restart: unless-stopped`.

## Резервные копии

```sh
mkdir -p backups
chmod 700 backups
docker compose --env-file .env.production -f compose.production.yml exec -T db pg_dump -U destination -d destination -Fc > backups/destination.dump
chmod 600 backups/destination.dump
```

Каждый запуск примера перезаписывает файл: для истории используйте разные имена с датами. Храните копии отдельно от сервера и проверяйте восстановление в отдельную тестовую БД. Не выполняйте `down -v`: эта команда удаляет тома с данными. Смена POSTGRES_PASSWORD после первого запуска сама по себе не меняет пароль существующей БД.

## Диагностика

```sh
docker compose --env-file .env.production -f compose.production.yml logs --tail=100 app web
```

Готовность контейнера проверяется через `/api/health`; это проверка HTTP-процесса, не полная проверка базы и бизнес-сценариев. Финальная проверка развёртывания — успешный вход и выдача PDF на реальном домене.

Конфигурация подготовлена, но на сервере пока не запускалась. Для публикации нужны выбранный сервер, домен и авторизованный доступ. Покупка хостинга и домена не выполнялась.
