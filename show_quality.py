import sqlite3
import pandas as pd

con = sqlite3.connect("data/mdm.db")
g = pd.read_sql("SELECT * FROM golden_records", con)

print("score distribution")
print(g["quality_score"].value_counts().sort_index(ascending=False).head(15))

fields = ["name", "email", "phone", "dob", "address"]
g["fields_filled"] = g[fields].apply(
    lambda r: sum(x is not None and str(x).strip() not in ("", "nan", "None") for x in r), axis=1)
print("\nscore by number of filled fields")
print(g.groupby("fields_filled")["quality_score"].agg(["count", "min", "max", "mean"]).round(1))
print("\nscore by number of source records")
print(g.groupby("n_records")["quality_score"].agg(["count", "min", "max", "mean"]).round(1))