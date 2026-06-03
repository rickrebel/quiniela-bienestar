import json
import sqlite3

with open("../jsons/teams.json", "r", encoding="utf-8") as f:
    teams = json.load(f)

conn = sqlite3.connect("../app.db")
cursor = conn.cursor()

cursor.executemany("""
    INSERT INTO teams (
        name,
        flag,
        group_name
    )
    VALUES (?, ?, ?)
    """, [
    (
        team["team_name"],
        team["flag"],
        team["group_name"]
    )
    for team in teams
])

conn.commit()
conn.close()

print("Equipos insertados correctamente.")
