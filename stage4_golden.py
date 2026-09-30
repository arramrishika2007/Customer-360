import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

DB = "data/mdm.db"
TRUST_FILE = Path("data/raw/trust_hierarchy.json")
REVIEW_FILE = Path("data/review_decisions.csv")   # optional: record_uid_1, record_uid_2, decision
FIELDS = ["name", "email", "phone", "dob", "address"]


class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def load():
    with sqlite3.connect(DB) as con:
        src = pd.read_sql("SELECT * FROM source_info", con)
        fuzzy = pd.read_sql("SELECT * FROM fuzzy_candidates", con)
    return src, fuzzy


def load_priorities():
    text = TRUST_FILE.read_text(encoding="utf-8")
    # the provided file has a sentence of prose above the JSON, so it isn't valid JSON as-is
    cfg = json.loads(text[text.index("{"): text.rindex("}") + 1])
    return {field.lower(): order for field, order in cfg["field_priorities"].items()}


def load_review_decisions():
    if not REVIEW_FILE.exists():
        return {}
    d = pd.read_csv(REVIEW_FILE, dtype=str)
    return {(r.record_uid_1, r.record_uid_2): r.decision.strip().upper()
            for r in d.itertuples()}


def cluster(src, fuzzy, decisions):
    """Union-find over MATCH pairs plus any review pair a human approved with MERGE.
    Only trusted edges are added, so a shared email between two different people
    cannot pull them into one cluster."""
    uf = UnionFind(src["record_uid"])
    edges = 0
    for r in fuzzy.itertuples():
        d = decisions.get((r.record_uid_1, r.record_uid_2))
        if d == "KEEP_SEPARATE":
            continue
        if r.decision == "MATCH" or d == "MERGE":
            uf.union(r.record_uid_1, r.record_uid_2)
            edges += 1

    groups = defaultdict(list)
    for uid in src["record_uid"]:
        groups[uf.find(uid)].append(uid)

    # stable ids: numbered by the smallest record_uid in each cluster
    ordered = sorted(groups.values(), key=lambda g: min(g))
    golden_of = {}
    for n, members in enumerate(ordered, start=1):
        for uid in members:
            golden_of[uid] = f"G{n:05d}"
    print(f"edges used: {edges}; clusters: {len(ordered)}")
    return golden_of


def pick_value(cluster_df, field, order):
    """Trust hierarchy: first source in priority order that has a value wins.
    If that source has several different values (duplicates inside one system),
    take the value most records in the cluster agree on; ties go to the lowest record_uid."""
    for system in order:
        rows = cluster_df[(cluster_df["source_system"] == system) & cluster_df[field].notna()]
        if rows.empty:
            continue
        votes = Counter(cluster_df[field].dropna())
        best = sorted(rows.itertuples(),
                      key=lambda r: (-votes[getattr(r, field)], r.record_uid))[0]
        return getattr(best, field), system, best.record_uid
    return None, None, None


def survive(src, golden_of, priorities):
    src = src.assign(golden_id=src["record_uid"].map(golden_of))
    golden, lineage = [], []
    for gid, grp in src.groupby("golden_id"):
        rec = {"golden_id": gid}
        for field in FIELDS:
            value, system, uid = pick_value(grp, field, priorities[field])
            rec[field] = value
            lineage.append({"golden_id": gid, "field": field, "value": value,
                            "source_system": system, "record_uid": uid})
        systems = set(grp["source_system"])
        rec["n_records"] = len(grp)
        rec["in_core"] = int("SourceA" in systems)
        rec["in_card"] = int("SourceB" in systems)
        rec["in_loan"] = int("SourceC" in systems)
        rec["credit_limit"] = grp["credit_limit"].max()
        rec["loan_amount"] = grp["loan_amount"].max()
        rec["quality_score"] = round(100 * sum(rec[f] is not None for f in FIELDS) / len(FIELDS))
        golden.append(rec)
    return src, pd.DataFrame(golden), pd.DataFrame(lineage)


def build_review_queue(fuzzy, golden_of, decisions):
    q = fuzzy[fuzzy["decision"] == "REVIEW"].copy()
    q["golden_id_1"] = q["record_uid_1"].map(golden_of)
    q["golden_id_2"] = q["record_uid_2"].map(golden_of)
    same_cluster = q["golden_id_1"] == q["golden_id_2"]
    human = [decisions.get((a, b)) for a, b in zip(q.record_uid_1, q.record_uid_2)]
    q["status"] = [h if h else ("IN_SAME_CLUSTER" if s else "PENDING")
                   for h, s in zip(human, same_cluster)]
    # you said keep them apart, but other MATCH links pulled them together
    q["conflict"] = same_cluster & (q["status"] == "KEEP_SEPARATE")
    return q


def report(golden, q):
    print("\ngolden records:", len(golden))
    print("records per golden record:", golden["n_records"].value_counts().sort_index().to_dict())
    print("system coverage (core/card/loan):",
          golden.groupby(["in_core", "in_card", "in_loan"]).size().to_dict())
    print("quality score:", golden["quality_score"].value_counts().sort_index().to_dict())
    print("\nreview queue:", len(q), "by status:", q["status"].value_counts().to_dict())
    if q["conflict"].any():
        print("CONFLICTS (marked KEEP_SEPARATE but clustered together):")
        print(q[q["conflict"]][["record_uid_1", "record_uid_2", "name_1", "name_2"]].to_string(index=False))


def ground_truth_check(src, golden_of):
    import re
    from itertools import combinations
    path = Path("data/raw/ground_truth_mapping.csv")
    if not path.exists():
        return
    g = pd.read_csv(path, dtype=str)
    masters = {}
    for r in g.itertuples():
        recs = []
        for system, cell in (("SourceA", r.Core_Banking_Customer_ID),
                             ("SourceA", r.Core_Banking_Duplicate_IDs),
                             ("SourceB", r.Credit_Card_Cust_Ref),
                             ("SourceC", r.Loan_Cust_ID)):
            if isinstance(cell, str):
                recs += [f"{system}::{x}" for x in re.split(r"[;,|\s]+", cell) if x]
        masters[r.Master_ID] = recs
    true_pairs = {p for m in masters.values() for p in combinations(sorted(m), 2)}
    joined = sum(golden_of[a] == golden_of[b] for a, b in true_pairs)
    rec_master = {u: m for m, us in masters.items() for u in us}
    by_golden = defaultdict(set)
    for u, m in rec_master.items():
        by_golden[golden_of[u]].add(m)
    merged_wrong = [g for g, ms in by_golden.items() if len(ms) > 1]
    print(f"\nground truth: {joined}/{len(true_pairs)} true pairs are in the same golden record")
    print("golden records containing 2+ different true customers:", len(merged_wrong))


if __name__ == "__main__":
    src, fuzzy = load()
    decisions = load_review_decisions()
    golden_of = cluster(src, fuzzy, decisions)
    src2, golden, lineage = survive(src, golden_of, load_priorities())
    queue = build_review_queue(fuzzy, golden_of, decisions)
    report(golden, queue)
    ground_truth_check(src, golden_of)

    with sqlite3.connect(DB) as con:
        src2[["record_uid", "golden_id"]].to_sql("record_golden_map", con, if_exists="replace", index=False)
        golden.to_sql("golden_records", con, if_exists="replace", index=False)
        lineage.to_sql("golden_lineage", con, if_exists="replace", index=False)
        queue.to_sql("review_queue", con, if_exists="replace", index=False)
    print("\nsaved: record_golden_map, golden_records, golden_lineage, review_queue")