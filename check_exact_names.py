import re
import sqlite3

import pandas as pd
from rapidfuzz import fuzz

DB = "data/mdm.db"


def first_last(name):
    """Return (first, last) lower-cased, with '.' stripped from initials."""
    toks = [t.strip(".").lower() for t in re.sub(r"[^\w\s.]", "", name).split()]
    toks = [t for t in toks if t]
    if not toks:
        return "", ""
    return toks[0], toks[-1]


def first_compatible(a, b):
    if a == b:
        return True
    # one side is an initial and it matches the other's first letter
    if (len(a) <= 1 or len(b) <= 1) and a[:1] == b[:1]:
        return True
    # close spelling, e.g. jon / john
    return fuzz.ratio(a, b) >= 80


def classify(row):
    f1, l1 = first_last(row["name_1"])
    f2, l2 = first_last(row["name_2"])
    surname_ok = fuzz.ratio(l1, l2) >= 85
    first_ok = first_compatible(f1, f2)
    if surname_ok and first_ok:
        return "same_person_likely"
    if surname_ok:
        return "check_first_name"
    return "check_surname"


if __name__ == "__main__":
    with sqlite3.connect(DB) as con:
        cands = pd.read_sql("SELECT * FROM exact_candidates", con)
        total_records = pd.read_sql("SELECT COUNT(*) n FROM source_info", con)["n"][0]

    cands["verdict"] = cands.apply(classify, axis=1)

    print("verdict by matched_on:")
    print(pd.crosstab(cands["verdict"], cands["matched_on"], margins=True), "\n")

    in_pairs = pd.concat([cands["record_uid_1"], cands["record_uid_2"]]).nunique()
    print(f"records that appear in at least one exact pair: {in_pairs} of {total_records}\n")

    cols = ["record_uid_1", "record_uid_2", "name_1", "name_2", "matched_on"]

    print("ALL pairs where the surname differs:")
    print(cands[cands["verdict"] == "check_surname"][cols].to_string(index=False), "\n")

    print("pairs where only the first name differs (first 15):")
    print(cands[cands["verdict"] == "check_first_name"][cols].head(15).to_string(index=False))