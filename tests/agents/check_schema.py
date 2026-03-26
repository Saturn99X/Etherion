import sqlite3

conn = sqlite3.connect('etherion.db')
cursor = conn.cursor()

print("Conversation table columns:")
cursor.execute("PRAGMA table_info(conversation)")
for col in cursor.fetchall():
    print(f"  {col[1]} ({col[2]})")

print("\nProject table columns:")
cursor.execute("PRAGMA table_info(project)")
for col in cursor.fetchall():
    print(f"  {col[1]} ({col[2]})")

conn.close()