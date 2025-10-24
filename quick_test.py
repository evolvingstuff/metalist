import sqlite3
import time

conn = sqlite3.connect('notes.db')
cursor = conn.cursor()

start = time.perf_counter()
cursor.execute("BEGIN")
cursor.execute("UPDATE notes SET updated_at='test' WHERE rowid=2")
cursor.execute("COMMIT")
end = time.perf_counter()

print(f"Python SQLite: {(end - start) * 1000:.2f}ms")
