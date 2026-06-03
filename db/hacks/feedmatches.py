import json
import sqlite3

with open("../jsons/matches.json", "r", encoding="utf-8") as f:
    matches = json.load(f)

conn = sqlite3.connect("../app.db")
cursor = conn.cursor()

def get_team_map(cursor):
    rows = cursor.execute("""
        SELECT id, name
        FROM teams
    """).fetchall()

    return {
        name: team_id
        for team_id, name in rows
    }

team_map = get_team_map(cursor)

cursor.executemany("""
    INSERT INTO matches (
        date,
        phase,
        group_name,
        stadium,
        team_a_id,
        team_b_id
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, [
    (
        match["date"],
        "groups",
        match["group"],
        match["stadium"],
        team_map[match["team_a"]],
        team_map[match["team_b"]]
    )
    for match in matches
])

conn.commit()
conn.close()

print("Partidos insertados correctamente.")