import sqlite3
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

con = sqlite3.connect("data/mdm.db")
print("steward_audit_log")
print(pd.read_sql("SELECT * FROM steward_audit_log ORDER BY id DESC", con))
print()
print("review_decisions")
print(pd.read_sql("SELECT * FROM review_decisions ORDER BY id DESC", con))