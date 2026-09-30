import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

DB = "data/mdm.db"
DASHBOARD = Path(__file__).parent / "dashboard.html"
app = FastAPI(title="Customer 360 API")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def golden_cols(con):
    return [r["name"] for r in con.execute("PRAGMA table_info(golden_records)")]


with db() as _c:
    _c.execute("""CREATE TABLE IF NOT EXISTS steward_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, golden_id TEXT, field TEXT,
        old_value TEXT, new_value TEXT, steward TEXT, reason TEXT, changed_at TEXT)""")
    _c.execute("""CREATE TABLE IF NOT EXISTS review_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, record_uid_1 TEXT, record_uid_2 TEXT,
        decision TEXT, steward TEXT, reason TEXT, decided_at TEXT)""")


# ---------- Dashboard ----------

@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD)


# ---------- Customers ----------

@app.get("/customers")
def list_customers(q: Optional[str] = None, limit: int = Query(50, le=500), offset: int = 0):
    """Search across golden_id and every column of golden_records."""
    with db() as con:
        cols = golden_cols(con)
        sql, args = "SELECT g.*, s.txn_count, s.net_flow FROM golden_records g " \
                    "LEFT JOIN golden_txn_summary s USING (golden_id)", []
        if q:
            sql += " WHERE " + " OR ".join(f"CAST(g.{c} AS TEXT) LIKE ?" for c in cols)
            args += [f"%{q}%"] * len(cols)
        sql += " ORDER BY g.golden_id LIMIT ? OFFSET ?"
        return rows(con, sql, args + [limit, offset])


@app.get("/customers/{golden_id}")
def customer_360(golden_id: str):
    with db() as con:
        golden = rows(con, "SELECT * FROM golden_records WHERE golden_id=?", (golden_id,))
        if not golden:
            raise HTTPException(404, "golden record not found")
        sources = rows(con, "SELECT s.* FROM source_info s JOIN record_golden_map m "
                            "USING (record_uid) WHERE m.golden_id=?", (golden_id,))
        txns = rows(con, "SELECT * FROM transactions WHERE golden_id=? ORDER BY txn_date",
                    (golden_id,))
        summary = rows(con, "SELECT * FROM golden_txn_summary WHERE golden_id=?", (golden_id,))
        audit = rows(con, "SELECT * FROM steward_audit_log WHERE golden_id=? ORDER BY id DESC",
                     (golden_id,))
        lineage = rows(con, "SELECT field, value, source_system, record_uid "
                            "FROM golden_lineage WHERE golden_id=?", (golden_id,))
        # exact / fuzzy candidate pairs that involve any of this golden record's source records
        uids = [x["record_uid"] for x in sources]
        matches = []
        if uids:
            ph = ",".join("?" * len(uids))
            gmap = {r["record_uid"]: r["golden_id"]
                    for r in con.execute("SELECT record_uid, golden_id FROM record_golden_map")}
            found = rows(con, "SELECT 'exact' AS method, record_uid_1, record_uid_2, name_1, name_2, "
                              "matched_on AS detail FROM exact_candidates "
                              f"WHERE record_uid_1 IN ({ph}) OR record_uid_2 IN ({ph})", uids + uids)
            found += rows(con, "SELECT 'fuzzy' AS method, record_uid_1, record_uid_2, name_1, name_2, "
                               "decision || ' (name ' || name_verdict || ', address ' || address_verdict "
                               "|| ', street ' || street_score || ')' AS detail FROM fuzzy_candidates "
                               f"WHERE record_uid_1 IN ({ph}) OR record_uid_2 IN ({ph})", uids + uids)
            for m in found:
                first = m["record_uid_1"] in uids
                mine, other = ((m["record_uid_1"], m["record_uid_2"]) if first
                               else (m["record_uid_2"], m["record_uid_1"]))
                matches.append({"method": m["method"], "this_record": mine, "matched_with": other,
                                "matched_name": m["name_2"] if first else m["name_1"],
                                "detail": m["detail"], "other_golden_id": gmap.get(other),
                                "joined": gmap.get(other) == golden_id})
        return {"golden": golden[0], "source_records": sources,
                "transactions": txns, "summary": summary[0] if summary else None,
                "audit_log": audit, "lineage": lineage, "matches": matches}


class Override(BaseModel):
    field: str
    new_value: str
    steward: str
    reason: str = ""


@app.post("/customers/{golden_id}/override")
def override(golden_id: str, body: Override):
    with db() as con:
        cols = golden_cols(con)
        if body.field not in cols or body.field == "golden_id":
            raise HTTPException(400, f"field must be one of {[c for c in cols if c != 'golden_id']}")
        cur = con.execute(f"SELECT {body.field} FROM golden_records WHERE golden_id=?", (golden_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "golden record not found")
        con.execute(f"UPDATE golden_records SET {body.field}=? WHERE golden_id=?",
                    (body.new_value, golden_id))
        con.execute("INSERT INTO steward_audit_log (golden_id, field, old_value, new_value, "
                    "steward, reason, changed_at) VALUES (?,?,?,?,?,?,?)",
                    (golden_id, body.field, str(row[0]), body.new_value, body.steward,
                     body.reason, datetime.now(timezone.utc).isoformat()))
        return {"status": "updated", "golden_id": golden_id, "field": body.field}


@app.get("/audit")
def audit_log(limit: int = 100):
    with db() as con:
        return rows(con, "SELECT * FROM steward_audit_log ORDER BY id DESC LIMIT ?", (limit,))


# ---------- Summary ----------

@app.get("/summary")
def summary():
    with db() as con:
        one = lambda sql: con.execute(sql).fetchone()[0]
        pend = ("FROM review_queue q LEFT JOIN review_decisions d ON d.record_uid_1=q.record_uid_1 "
                "AND d.record_uid_2=q.record_uid_2 WHERE d.id IS NULL AND q.golden_id_1<>q.golden_id_2")
        return {
            "golden_records": one("SELECT COUNT(*) FROM golden_records"),
            "source_records": one("SELECT COUNT(*) FROM source_info"),
            "multi_system": one("SELECT COUNT(*) FROM golden_records WHERE in_core+in_card+in_loan>=2"),
            "transactions": one("SELECT COUNT(*) FROM transactions"),
            "steward_changes": one("SELECT COUNT(*) FROM steward_audit_log"),
            "pending_pairs": one("SELECT COUNT(*) " + pend),
            "pending_groups": one("SELECT COUNT(DISTINCT MIN(q.golden_id_1,q.golden_id_2)||'|'||"
                                  "MAX(q.golden_id_1,q.golden_id_2)) " + pend),
            "decided_pairs": one("SELECT COUNT(*) FROM review_decisions"),
            "by_system": rows(con, "SELECT source_system, COUNT(*) n FROM source_info "
                                   "GROUP BY source_system ORDER BY source_system"),
            "quality": rows(con, "SELECT (quality_score/10)*10 AS bucket, COUNT(*) n "
                                 "FROM golden_records GROUP BY bucket ORDER BY bucket"),
        }


# ---------- Table viewer ----------

def _table_names(con):
    return [r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


@app.get("/tables")
def list_tables():
    with db() as con:
        return [{"name": n, "rows": con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]}
                for n in _table_names(con)]


@app.get("/tables/{name}")
def table_rows(name: str, limit: int = Query(100, le=1000), offset: int = 0):
    with db() as con:
        if name not in _table_names(con):
            raise HTTPException(404, "table not found")
        order = "DESC" if name in ("steward_audit_log", "review_decisions") else "ASC"
        total = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        data = rows(con, f'SELECT * FROM "{name}" ORDER BY rowid {order} LIMIT ? OFFSET ?',
                    (limit, offset))
        return {"name": name, "total": total, "rows": data}


# ---------- Review queue ----------

@app.get("/reviews")
def list_reviews(include_resolved: bool = False):
    """Pending = golden IDs differ and no steward decision yet."""
    with db() as con:
        sql = """SELECT q.*, d.decision AS steward_decision, d.steward, d.decided_at
                 FROM review_queue q
                 LEFT JOIN review_decisions d
                   ON d.record_uid_1 = q.record_uid_1 AND d.record_uid_2 = q.record_uid_2"""
        if not include_resolved:
            sql += " WHERE d.id IS NULL AND q.golden_id_1 <> q.golden_id_2"
        return rows(con, sql)


class Decision(BaseModel):
    record_uid_1: str
    record_uid_2: str
    decision: str  # "approve" or "reject"
    steward: str
    reason: str = ""


def _merge(con, keep, drop, steward, reason, now):
    con.execute("UPDATE record_golden_map SET golden_id=? WHERE golden_id=?", (keep, drop))
    con.execute("UPDATE transactions SET golden_id=? WHERE golden_id=?", (keep, drop))
    con.execute("DELETE FROM golden_lineage WHERE golden_id=?", (drop,))
    con.execute("UPDATE review_queue SET golden_id_1=? WHERE golden_id_1=?", (keep, drop))
    con.execute("UPDATE review_queue SET golden_id_2=? WHERE golden_id_2=?", (keep, drop))
    # fill gaps in the surviving record from the absorbed one, then delete it
    con.execute("""UPDATE golden_records SET
        credit_limit = COALESCE(credit_limit, (SELECT credit_limit FROM golden_records WHERE golden_id=?)),
        loan_amount  = COALESCE(loan_amount,  (SELECT loan_amount  FROM golden_records WHERE golden_id=?))
        WHERE golden_id=?""", (drop, drop, keep))
    con.execute("DELETE FROM golden_records WHERE golden_id=?", (drop,))
    # recompute counts from the source records now mapped to the survivor
    con.execute("""UPDATE golden_records SET
        n_records = (SELECT COUNT(*) FROM record_golden_map WHERE golden_id=?),
        in_core = (SELECT COUNT(*) > 0 FROM source_info s JOIN record_golden_map m USING (record_uid)
                   WHERE m.golden_id=? AND s.source_system='SourceA'),
        in_card = (SELECT COUNT(*) > 0 FROM source_info s JOIN record_golden_map m USING (record_uid)
                   WHERE m.golden_id=? AND s.source_system='SourceB'),
        in_loan = (SELECT COUNT(*) > 0 FROM source_info s JOIN record_golden_map m USING (record_uid)
                   WHERE m.golden_id=? AND s.source_system='SourceC')
        WHERE golden_id=?""", (keep, keep, keep, keep, keep))
    # recompute transaction summary
    con.execute("DELETE FROM golden_txn_summary WHERE golden_id IN (?,?)", (keep, drop))
    con.execute("""INSERT INTO golden_txn_summary
        SELECT golden_id, COUNT(*), MIN(txn_date), MAX(txn_date), COUNT(DISTINCT source_system),
               SUM(CASE WHEN txn_type='Credit' THEN amount ELSE 0 END),
               SUM(CASE WHEN txn_type='Debit' THEN amount ELSE 0 END),
               ROUND(SUM(CASE WHEN txn_type='Credit' THEN amount ELSE 0 END)
                   - SUM(CASE WHEN txn_type='Debit' THEN amount ELSE 0 END), 2)
        FROM transactions WHERE golden_id=? GROUP BY golden_id""", (keep,))
    con.execute("INSERT INTO steward_audit_log (golden_id, field, old_value, new_value, steward, "
                "reason, changed_at) VALUES (?,?,?,?,?,?,?)",
                (keep, "merge", drop, keep, steward, reason, now))


@app.post("/reviews/decide")
def decide(body: Decision):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    with db() as con:
        pair = con.execute("SELECT * FROM review_queue WHERE record_uid_1=? AND record_uid_2=?",
                           (body.record_uid_1, body.record_uid_2)).fetchone()
        if pair is None:
            raise HTTPException(404, "review pair not found")
        if con.execute("SELECT 1 FROM review_decisions WHERE record_uid_1=? AND record_uid_2=?",
                       (body.record_uid_1, body.record_uid_2)).fetchone():
            raise HTTPException(409, "pair already decided")
        now = datetime.now(timezone.utc).isoformat()
        result = {"decision": body.decision}
        g1, g2 = pair["golden_id_1"], pair["golden_id_2"]
        if body.decision == "approve" and g1 != g2:
            _merge(con, g1, g2, body.steward, body.reason, now)
            result["merged"] = {"kept": g1, "absorbed": g2}
        elif body.decision == "reject" and g1 == g2:
            result["warning"] = "these records were already clustered together; reject does not split them"
        con.execute("INSERT INTO review_decisions (record_uid_1, record_uid_2, decision, steward, "
                    "reason, decided_at) VALUES (?,?,?,?,?,?)",
                    (body.record_uid_1, body.record_uid_2, body.decision, body.steward,
                     body.reason, now))
        if body.decision == "reject":
            con.execute("INSERT INTO steward_audit_log (golden_id, field, old_value, new_value, "
                        "steward, reason, changed_at) VALUES (?,?,?,?,?,?,?)",
                        (g1, "review_reject", g2, "kept separate", body.steward,
                         body.reason, now))
        return result