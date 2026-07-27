import sqlite3
import os
import time
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "brain_memory.db")

class MemoryManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                role TEXT,
                content TEXT
            )
        ''')
        # FTS5 virtual table for semantic keyword search
        self.conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content='messages',
                content_rowid='id'
            )
        ''')
        self.conn.execute('''
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END;
        ''')
        self.conn.commit()

    def add_message(self, role, content):
        if not content.strip():
            return
            
        # Clean up JSON for storage so she just remembers the conversation
        text_to_save = content
        if role == "assistant" and "{" in content:
            try:
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != 0:
                    data = json.loads(content[start:end])
                    text_to_save = data.get("response", content)
            except json.JSONDecodeError:
                pass

        self.conn.execute(
            'INSERT INTO messages (timestamp, role, content) VALUES (?, ?, ?)',
            (time.time(), role, text_to_save)
        )
        self.conn.commit()

    def retrieve_relevant_memories(self, user_query, limit=3):
        # Extract meaningful keywords from user query
        words = [w for w in user_query.replace("'", "").replace('"', "").split() if len(w) > 3]
        if not words:
            return []
            
        # Create an OR query for Full-Text Search
        fts_query = " OR ".join(words)
        
        cur = self.conn.cursor()
        try:
            cur.execute('''
                SELECT content FROM messages_fts 
                WHERE messages_fts MATCH ? 
                ORDER BY rank LIMIT ?
            ''', (fts_query, limit))
            rows = cur.fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error:
            return []
