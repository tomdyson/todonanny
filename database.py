import os
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

# Get database path from environment variable, default to local directory
DB_PATH = os.getenv('DB_PATH', 'tasks.db')
print(f"Database path is set to: {DB_PATH}")

# Debug directory information
db_dir = os.path.dirname(DB_PATH)
print(f"Database directory: {db_dir}")

# Ensure the directory exists
try:
    if db_dir:  # Only try to create directory if path contains a directory part
        os.makedirs(db_dir, exist_ok=True)
        print(f"Directory exists or was created: {db_dir}")
    
    # Try to create an empty database file if it doesn't exist
    if not os.path.exists(DB_PATH):
        print(f"Attempting to create database file: {DB_PATH}")
        try:
            with open(DB_PATH, 'a'):
                os.utime(DB_PATH, None)
            print(f"Successfully created database file")
        except Exception as e:
            print(f"Error creating database file: {str(e)}")
    
    # Check directory permissions and ownership
    if db_dir:
        stat_info = os.stat(db_dir)
        print(f"Directory permissions: {stat.filemode(stat_info.st_mode)}")
        print(f"Directory owner: {stat_info.st_uid}")
        print(f"Directory group: {stat_info.st_gid}")
        
        if os.path.exists(DB_PATH):
            db_stat = os.stat(DB_PATH)
            print(f"Database file permissions: {stat.filemode(db_stat.st_mode)}")
            print(f"Database file owner: {db_stat.st_uid}")
            print(f"Database file group: {db_stat.st_gid}")
    
    # List directory contents
    if db_dir:
        print(f"Directory contents: {os.listdir(db_dir)}")
except Exception as e:
    print(f"Error during directory setup: {str(e)}")

@contextmanager
def get_db():
    try:
        print(f"Attempting to connect to database at: {DB_PATH}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Current user ID: {os.getuid()}")
        print(f"Current group ID: {os.getgid()}")
        
        conn = sqlite3.connect(DB_PATH)
        print("Successfully connected to database")
        conn.row_factory = sqlite3.Row
        yield conn
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
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
        # First verify the list exists
        list_exists = conn.execute('SELECT 1 FROM task_lists WHERE id = ?', (list_id,)).fetchone()
        if not list_exists:
            return False

        # Get the task ID for the given index
        task = conn.execute('''
            SELECT id FROM tasks 
            WHERE list_id = ? 
            ORDER BY start_time 
            LIMIT 1 OFFSET ?
        ''', (list_id, task_index)).fetchone()

        if not task:
            return False

        # Update the task status
        conn.execute('''
            UPDATE tasks 
            SET completed = ?
            WHERE id = ?
        ''', (completed, task['id']))
        
        conn.commit()
        return True