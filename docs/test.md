# Post Service

## Зоны ответственности
1. **Управление промокодами**: Создание, редактирование и удаление промокодов.
2. **Комментарии**: Управление комментариями к промокодам.
3. **Интеграция со статистикой**: Отправка событий (лайки, просмотры, комментарии) в сервис статистики через Kafka.

## Границы сервиса
- Не отвечает за аутентификацию пользователей.
- Не хранит статистику, только отправляет события для её сбора.

## ER-диаграмма

```mermaid
erDiagram
    POSTS ||--o{ COMMENTS : "has"
    POSTS {
        int id
        string title
        string description
        int business_id
        datetime created_at
    }
    COMMENTS {
        int id
        string text
        int user_id
        int post_id
        datetime created_at
    }
