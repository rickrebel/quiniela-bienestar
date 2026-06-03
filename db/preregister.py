import sqlite3

conn = sqlite3.connect("app.db")
cur = conn.cursor()

cur.execute("""
    INSERT INTO users (
        email,
        name,
        did_pay
    )
    VALUES (?, ?, ?)
""", (
    "otrocorreo@mail.com",
    "Probando",
    0
))

conn.commit()
conn.close()
