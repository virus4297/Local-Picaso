import sqlite3
import os

path = os.path.join('data', 'localvision.db')
print('db exists', os.path.exists(path))
if not os.path.exists(path):
    raise SystemExit('DB not found: ' + path)
conn = sqlite3.connect(path)
cur = conn.cursor()
print('tables:')
for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(' ', row[0])
print('persons:')
for row in cur.execute('SELECT id, name FROM person'):
    print(' ', row)
print('faces:')
for row in cur.execute('SELECT id, photo_id, person_id FROM face ORDER BY id LIMIT 20'):
    print(' ', row)
print('groups:')
for row in cur.execute('SELECT person_id, COUNT(*) FROM face GROUP BY person_id'):
    print(' ', row)
conn.close()
