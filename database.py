"""Database module for conversations, settings, and users"""
import sqlite3
from datetime import datetime
import json

DB_PATH = "agent.db"


def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     username
                     TEXT
                     UNIQUE
                     NOT
                     NULL,
                     api_key
                     TEXT,
                     created_at
                     TIMESTAMP
                     DEFAULT
                     CURRENT_TIMESTAMP
                 )''')

    # Таблица диалогов
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        user_id
        INTEGER,
        session_id
        TEXT
        UNIQUE
        NOT
        NULL,
        title
        TEXT
        DEFAULT
        'New Conversation',
        model
        TEXT
        DEFAULT
        'claude-opus-4-1',
        created_at
        TIMESTAMP
        DEFAULT
        CURRENT_TIMESTAMP,
        updated_at
        TIMESTAMP
        DEFAULT
        CURRENT_TIMESTAMP,
        FOREIGN
        KEY
                 (
        user_id
                 ) REFERENCES users
                 (
                     id
                 )
        )''')

    # Таблица сообщений
    c.execute('''CREATE TABLE IF NOT EXISTS messages
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        conversation_id
        INTEGER,
        role
        TEXT
        NOT
        NULL,
        content
        TEXT
        NOT
        NULL,
        tool_calls
        TEXT,
        tokens
        INTEGER
        DEFAULT
        0,
        created_at
        TIMESTAMP
        DEFAULT
        CURRENT_TIMESTAMP,
        FOREIGN
        KEY
                 (
        conversation_id
                 ) REFERENCES conversations
                 (
                     id
                 )
        )''')

    # Таблица настроек
    c.execute('''CREATE TABLE IF NOT EXISTS settings
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        user_id
        INTEGER,
        key
        TEXT
        NOT
        NULL,
        value
        TEXT,
        UNIQUE
                 (
        user_id,
        key
                 ),
        FOREIGN KEY
                 (
                     user_id
                 ) REFERENCES users
                 (
                     id
                 )
        )''')

    # Создать дефолтного пользователя
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (1, 'default')")

    conn.commit()
    conn.close()
    print("[DB] ✅ Database initialized")


def save_message(session_id, role, content, tool_calls=None):
    """Сохранить сообщение"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Получить или создать conversation
    c.execute("SELECT id FROM conversations WHERE session_id = ?", (session_id,))
    result = c.fetchone()

    if not result:
        c.execute(
            "INSERT INTO conversations (user_id, session_id) VALUES (1, ?)",
            (session_id,)
        )
        conv_id = c.lastrowid
    else:
        conv_id = result[0]

    # Сохранить сообщение
    c.execute(
        "INSERT INTO messages (conversation_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, json.dumps(tool_calls) if tool_calls else None)
    )

    # Обновить updated_at
    c.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conv_id,)
    )

    conn.commit()
    conn.close()


def get_conversation_history(session_id):
    """Получить историю диалога"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
              SELECT m.role, m.content, m.tool_calls
              FROM messages m
                       JOIN conversations c ON m.conversation_id = c.id
              WHERE c.session_id = ?
              ORDER BY m.created_at
              """, (session_id,))

    messages = []
    for role, content, tool_calls in c.fetchall():
        msg = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = json.loads(tool_calls)
        messages.append(msg)

    conn.close()
    return messages


def get_all_conversations(user_id=1):
    """Получить все диалоги пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
              SELECT c.session_id,
                     c.title,
                     c.created_at,
                     c.updated_at,
                     COUNT(m.id) as message_count
              FROM conversations c
                       LEFT JOIN messages m ON c.id = m.conversation_id
              WHERE c.user_id = ?
              GROUP BY c.id
              ORDER BY c.updated_at DESC LIMIT 50
              """, (user_id,))

    conversations = []
    for row in c.fetchall():
        conversations.append({
            "session_id": row[0],
            "title": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "message_count": row[4]
        })

    conn.close()
    return conversations


def update_conversation_title(session_id, title):
    """Обновить заголовок диалога"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE conversations SET title = ? WHERE session_id = ?",
        (title, session_id)
    )
    conn.commit()
    conn.close()


def delete_conversation(session_id):
    """Удалить диалог"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def get_setting(user_id, key, default=None):
    """Получить настройку"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
    result = c.fetchone()
    conn.close()
    return result[0] if result else default


def set_setting(user_id, key, value):
    """Установить настройку"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, value)
    )
    conn.commit()
    conn.close()


# Инициализация при импорте
init_db()
