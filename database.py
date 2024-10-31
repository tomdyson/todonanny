import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional


@contextmanager
def get_db():
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS task_lists (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            description TEXT NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (list_id) REFERENCES task_lists (id)
        )
        ''')
        conn.commit()

def create_task_list(tasks: List[dict]) -> str:
    list_id = str(uuid.uuid4())
    
    with get_db() as conn:
        conn.execute('INSERT INTO task_lists (id) VALUES (?)', (list_id,))
        
        for task in tasks:
            conn.execute('''
            INSERT INTO tasks (list_id, start_time, end_time, description, completed)
            VALUES (?, ?, ?, ?, ?)
            ''', (list_id, task['start_time'], task['end_time'], task['description'], False))
        
        conn.commit()
    
    return list_id

def get_task_list(list_id: str) -> Optional[List[dict]]:
    with get_db() as conn:
        # Check if list exists
        list_exists = conn.execute('SELECT 1 FROM task_lists WHERE id = ?', (list_id,)).fetchone()
        if not list_exists:
            return None
            
        tasks = conn.execute('''
        SELECT start_time, end_time, description, completed
        FROM tasks
        WHERE list_id = ?
        ORDER BY start_time
        ''', (list_id,)).fetchall()
        
        return [dict(task) for task in tasks]

def update_task_status(list_id: str, task_index: int, completed: bool) -> bool:
    with get_db() as conn:
        task = conn.execute('''
        UPDATE tasks 
        SET completed = ?
        WHERE list_id = ? AND id IN (
            SELECT id FROM tasks WHERE list_id = ? ORDER BY start_time LIMIT 1 OFFSET ?
        )
        RETURNING *
        ''', (completed, list_id, list_id, task_index)).fetchone()
        
        conn.commit()
        return bool(task) 