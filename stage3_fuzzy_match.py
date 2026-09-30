import sqlite3
from collections import defaultdict
from itertools import combinations

import pandas as pd

from name_rules import name_parts, name_verdict, address_parts, address_verdict

DB = "data/mdm.db"


def load():
    with sqlite3.connect(DB) as con:
        src = pd.read_sql("SELECT * FROM source_info", con)
        exact = pd.read_sql("SELECT * FROM exact_candidates", con)
    return src, exact


def candidate_pairs(src):
    """Blocking: compare two records only if they share a house number OR a surname.
    Comparing all 3,115 x 3,115 pairs would be ~4.8 million comparisons."""
    blocks = defaultdict(set)
    for r in src.itertuples():
        street, _ = address_parts(r.address)
        if street:
            blocks[("house", street.split()[0])].add(r.record_uid)
        _, last = name_parts(r.name)
        if last:
            blocks[("surname", last)].add(r.record_uid)
    pairs = set()
    for uids in blocks.values():
        pairs.update(combinations(sorted(uids), 2))
    return pairs


def decide(nv, av, exact_evidence):
    """Decision table. The order of these rules is the heart of the matching policy."""
    if nv == "match" and av == "same":
        return "MATCH"
    if nv == "match" and av == "unknown":
        return "REVIEW" if exact_evidence else None
    if nv == "match" and av == "different":
        return "REVIEW" if exact_evidence else None    # same name, other address: moved?
    if nv == "first_differs" and av == "same":
        return "REVIEW"                                # likely a household, not one person
    return None


def score_pairs(src, pairs, exact):
    rec = src.set_index("record_uid")[["source_system", "name", "address"]].to_dict("index")
    evidence = {(r.record_uid_1, r.record_uid_2): r.matched_on for r in exact.itertuples()}

    rows = []
    for u1, u2 in pairs:
        a, b = rec[u1], rec[u2]
        nv = name_verdict(a["name"], b["name"])
        ev = evidence.get((u1, u2))
        if nv == "surname_differs" and not ev:
            continue
        av, street_score = address_verdict(a["address"], b["address"])
        decision = decide(nv, av, ev)
        if decision is None and ev:
            decision = "REVIEW"                        # exact evidence but names/address disagree
        if decision:
            rows.append({
                "record_uid_1": u1, "record_uid_2": u2,
                "source_1": a["source_system"], "source_2": b["source_system"],
                "name_1": a["name"], "name_2": b["name"],
                "address_1": a["address"], "address_2": b["address"],
                "name_verdict": nv, "address_verdict": av,
                "street_score": round(street_score, 1),
                "exact_evidence": ev, "decision": decision,
            })
    return pd.DataFrame(rows)


def report(fz):
    print("pairs by decision and evidence:")
    fz = fz.assign(has_exact=fz["exact_evidence"].notna())
    print(pd.crosstab(fz["decision"], fz["has_exact"],
                      rownames=["decision"], colnames=["also an exact pair"]), "\n")

    new = fz[(fz["decision"] == "MATCH") & (~fz["has_exact"])]
    print("NEW MATCH pairs found only by fuzzy (exact matching missed these):", len(new))
    cols = ["record_uid_1", "record_uid_2", "name_1", "name_2", "address_1", "address_2"]
    print(new[cols].head(10).to_string(index=False), "\n")

    print("ALL REVIEW pairs:")
    rev = fz[fz["decision"] == "REVIEW"]
    print(rev[cols + ["name_verdict", "address_verdict", "exact_evidence"]]
          .to_string(index=False))


if __name__ == "__main__":
    src, exact = load()
    pairs = candidate_pairs(src)
    # exact pairs are always evaluated, even if blocking would never have compared them
    pairs |= {(r.record_uid_1, r.record_uid_2) for r in exact.itertuples()}
    print("pairs compared (blocking + exact pairs):", len(pairs), "\n")
    fuzzy = score_pairs(src, pairs, exact)
    report(fuzzy)
    with sqlite3.connect(DB) as con:
        fuzzy.to_sql("fuzzy_candidates", con, if_exists="replace", index=False)
    print("\nsaved fuzzy_candidates:", fuzzy.shape)