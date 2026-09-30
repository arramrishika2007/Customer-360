import sqlite3

con = sqlite3.connect("data/mdm.db")
for name, sql in con.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print(sql)
    print("  rows:", con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
    print()