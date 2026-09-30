import sqlite3
from pathlib import Path

import pandas as pd

DB = "data/mdm.db"
TXN_FILE = Path("data/raw/transaction_data.csv")


def load_transactions():
    t = pd.read_csv(TXN_FILE, dtype=str)
    t["Account_ID"] = t["Account_ID"].str.strip()
    t["Amount"] = pd.to_numeric(t["Amount"], errors="coerce")
    t["Date"] = pd.to_datetime(t["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    t["Type"] = t["Type"].str.strip().str.title()
    assert t["Txn_ID"].is_unique, "duplicate Txn_ID found"
    return t


def link(t, con):
    """Account_ID is the source-system ID (C0252, CC_870, L_505), so:
    Account_ID -> source_info.source_id -> record_uid -> golden_id."""
    ids = pd.read_sql(
        "SELECT s.source_id, s.record_uid, s.source_system, m.golden_id "
        "FROM source_info s JOIN record_golden_map m USING (record_uid)", con)
    assert ids["source_id"].is_unique, "source IDs collide across systems; need system in the join"
    out = t.merge(ids, left_on="Account_ID", right_on="source_id", how="left")
    out = out.rename(columns={"Txn_ID": "txn_id", "Account_ID": "account_id",
                              "Amount": "amount", "Date": "txn_date", "Type": "txn_type"})
    return out[["txn_id", "account_id", "source_system", "record_uid", "golden_id",
                "amount", "txn_date", "txn_type"]]


def summarize(linked):
    ok = linked.dropna(subset=["golden_id"])
    grp = ok.groupby("golden_id")
    s = grp.agg(txn_count=("txn_id", "count"),
                first_txn=("txn_date", "min"), last_txn=("txn_date", "max"),
                systems_with_txns=("source_system", "nunique")).reset_index()
    by_type = ok.pivot_table(index="golden_id", columns="txn_type", values="amount",
                             aggfunc="sum", fill_value=0).reset_index()
    by_type = by_type.rename(columns={"Credit": "total_credit", "Debit": "total_debit"})
    s = s.merge(by_type, on="golden_id", how="left")
    s["net_flow"] = (s["total_credit"] - s["total_debit"]).round(2)
    return s


def report(linked, summary, n_golden):
    unlinked = linked["golden_id"].isna().sum()
    print("transactions:", len(linked), "| linked to a golden record:", len(linked) - unlinked,
          "| UNLINKED:", unlinked)
    if unlinked:
        print(linked[linked["golden_id"].isna()]["account_id"].value_counts().head(10))
    print("\ntransactions by source system:", linked["source_system"].value_counts().to_dict())
    print(f"golden records with at least one transaction: {len(summary)} of {n_golden}")
    print("golden records whose transactions come from 2+ systems:",
          int((summary["systems_with_txns"] > 1).sum()))
    print("transactions per golden record:", summary["txn_count"].describe().round(1).to_dict())
    print("\ntop 5 by transaction count:")
    print(summary.sort_values("txn_count", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    with sqlite3.connect(DB) as con:
        linked = link(load_transactions(), con)
        summary = summarize(linked)
        n_golden = pd.read_sql("SELECT COUNT(*) n FROM golden_records", con)["n"][0]
        report(linked, summary, n_golden)
        linked.to_sql("transactions", con, if_exists="replace", index=False)
        summary.to_sql("golden_txn_summary", con, if_exists="replace", index=False)
    print("\nsaved: transactions, golden_txn_summary")