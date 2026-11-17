import sqlite3, hashlib
db = sqlite3.connect('nexa.db')
h = hashlib.sha256('12345'.encode()).hexdigest()
db.execute("UPDATE users SET password=?, role='admin', status='ACTIVE' WHERE email='admin@nexa.ai'")
db.execute("DELETE FROM attempts WHERE email='admin@nexa.ai'")
db.commit()
print('Admin Reset Done')