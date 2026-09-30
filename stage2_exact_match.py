import sqlite3
from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

DB = "data/mdm.db"
EXACT_FIELDS = ["email", "phone"]


def load_source_info():
    with sqlite3.connect(DB) as con:
        return pd.read_sql("SELECT * FROM source_info", con)


def pairs_for_field(df, field):
    """Every pair of records that share the same non-empty value in `field`."""
    rows = []
    sub = df.dropna(subset=[field])
    for value, grp in sub.groupby(field):
        if len(grp) < 2:
            continue
        recs = sorted(grp.to_dict("records"), key=lambda r: r["record_uid"])
        for a, b in combinations(recs, 2):
            rows.append({
                "record_uid_1": a["record_uid"],
                "record_uid_2": b["record_uid"],
                "source_1": a["source_system"],
                "source_2": b["source_system"],
                "name_1": a["name"],
                "name_2": b["name"],
                "matched_on": field,
                "matched_value": value,
                "group_size": len(grp),
            })
    return pd.DataFrame(rows)


def build_candidates(df):
    frames = [pairs_for_field(df, f) for f in EXACT_FIELDS]
    pairs = pd.concat(frames, ignore_index=True)

    # one row per pair, even if both email and phone matched
    key = ["record_uid_1", "record_uid_2"]
    combined = (
        pairs.groupby(key)
        .agg(
            source_1=("source_1", "first"),
            source_2=("source_2", "first"),
            name_1=("name_1", "first"),
            name_2=("name_2", "first"),
            matched_on=("matched_on", lambda s: "+".join(sorted(set(s)))),
            max_group_size=("group_size", "max"),
        )
        .reset_index()
    )

    combined["name_sort_score"] = combined.apply(
        lambda r: fuzz.token_sort_ratio(r["name_1"], r["name_2"]) / 100, axis=1)
    combined["name_set_score"] = combined.apply(
        lambda r: fuzz.token_set_ratio(r["name_1"], r["name_2"]) / 100, axis=1)
    combined["same_source"] = combined["source_1"] == combined["source_2"]
    return combined


def report(df, cands):
    print("=== groups sharing a value ===")
    for f in EXACT_FIELDS:
        sizes = df.dropna(subset=[f]).groupby(f).size()
        print(f"{f}: {(sizes > 1).sum()} shared values; "
              f"group size distribution:\n{sizes[sizes > 1].value_counts().sort_index().to_dict()}")

    print("\n=== candidate pairs:", len(cands), "===")
    print("by matched_on:\n", cands["matched_on"].value_counts(), "\n")

    combo = cands["source_1"] + " - " + cands["source_2"]
    print("by source combination:\n", combo.value_counts(), "\n")

    print("pairs within the same source (duplicates inside one system):",
          cands["same_source"].sum(), "\n")

    print("name score buckets (token_sort):")
    buckets = pd.cut(cands["name_sort_score"], [0, 0.5, 0.7, 0.85, 0.999, 1.0],
                     include_lowest=True)
    print(pd.crosstab(buckets, cands["matched_on"]), "\n")

    print("10 lowest name scores (check these by eye):")
    cols = ["record_uid_1", "record_uid_2", "name_1", "name_2",
            "matched_on", "name_sort_score"]
    print(cands.sort_values("name_sort_score").head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    source_info = load_source_info()
    candidates = build_candidates(source_info)
    report(source_info, candidates)

    with sqlite3.connect(DB) as con:
        candidates.to_sql("exact_candidates", con, if_exists="replace", index=False)
    print("\nsaved exact_candidates:", candidates.shape)