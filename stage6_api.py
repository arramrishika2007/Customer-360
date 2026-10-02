import hashlib
import io
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

DB = "data/mdm.db"
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





# ---------- Customers ----------

@app.get("/customers")
def list_customers(q: Optional[str] = None, quality_below: Optional[int] = None,
                   limit: int = Query(50, le=500), offset: int = 0):
    """Search across golden_id and every column of golden_records."""
    with db() as con:
        cols = golden_cols(con)
        sql, args = "SELECT g.*, s.txn_count, s.net_flow FROM golden_records g " \
                    "LEFT JOIN golden_txn_summary s USING (golden_id)", []
        where = []
        if q:
            where.append("(" + " OR ".join(f"CAST(g.{c} AS TEXT) LIKE ?" for c in cols) + ")")
            args += [f"%{q}%"] * len(cols)
        if quality_below is not None:
            where.append("g.quality_score < ?")
            args.append(quality_below)
        if where:
            sql += " WHERE " + " AND ".join(where)
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


# ---------- Import external files ----------

with db() as _c:
    _c.execute("""CREATE TABLE IF NOT EXISTS import_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, file_hash TEXT, source_system TEXT,
        rows_imported INTEGER, new_golden INTEGER, joined_existing INTEGER, review_pairs INTEGER,
        steward TEXT, backup TEXT, imported_at TEXT)""")

IMPORT_SYNONYMS = {
    "id": ["customerid", "custref", "loancustid", "custid", "accountid", "id"],
    "name": ["name", "fullname", "customername"],
    "email": ["email", "emailaddress", "mail"],
    "phone": ["phone", "mobile", "phonenumber"],
    "dob": ["dob", "dateofbirth", "birthdate"],
    "address": ["address", "addr"],
    "credit_limit": ["creditlimit"],
    "loan_amount": ["loanamt", "loanamount"],
}


def parse_table(filename, content):
    content = content.lstrip("\ufeff")
    try:
        if filename.lower().endswith(".json"):
            data = json.loads(content)
            if isinstance(data, dict):
                data = next((v for v in data.values() if isinstance(v, list)), [data])
            df = pd.json_normalize(data)
        else:
            df = pd.read_csv(io.StringIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"could not read {filename}: {e}")
    if df.empty:
        raise HTTPException(400, "file has no rows")
    df.columns = [str(c).strip() for c in df.columns]
    return df.astype(object).where(df.notna(), None)


class ImportFile(BaseModel):
    filename: str
    content: str


class ImportCommit(ImportFile):
    system: str
    mapping: dict
    steward: str
    reason: str = ""


@app.post("/import/preview")
def import_preview(body: ImportFile):
    df = parse_table(body.filename, body.content)
    cols = list(df.columns)
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in cols}
    guess = {f: next((norm[n] for n in names if n in norm), "") for f, names in IMPORT_SYNONYMS.items()}
    with db() as con:
        systems = [r[0] for r in con.execute("SELECT DISTINCT source_system FROM source_info ORDER BY 1")]
    return {"rows": len(df), "columns": cols, "sample": df.head(5).to_dict("records"),
            "mapping": guess, "systems": systems}


@app.get("/import/log")
def import_log():
    with db() as con:
        return rows(con, "SELECT * FROM import_log ORDER BY id DESC")


@app.post("/import/commit")
def import_commit(body: ImportCommit):
    # Reuses the real pipeline code so new data is cleaned, matched and merged by the same rules.
    from stage1_source_info import squash, CLEANERS, COMMON, EXTRAS
    from stage2_exact_match import build_candidates
    from stage3_fuzzy_match import candidate_pairs, score_pairs
    from stage4_golden import UnionFind, survive, load_priorities, FIELDS

    system = body.system.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,30}", system):
        raise HTTPException(400, "system name: letters, digits, underscore; start with a letter")
    if not body.steward.strip():
        raise HTTPException(400, "steward name is required")
    df = parse_table(body.filename, body.content)
    m = {k: v for k, v in body.mapping.items() if v}
    if "id" not in m:
        raise HTTPException(400, "map a column to the source ID")
    bad = [c for c in m.values() if c not in df.columns]
    if bad:
        raise HTTPException(400, f"mapped columns not in file: {bad}")
    file_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()

    # ---- standardise exactly like stage 1 ----
    new = pd.DataFrame(index=df.index)
    new["source_system"] = system
    new["source_id"] = df[m["id"]].map(squash)
    for f in COMMON:
        col = m.get(f)
        new[f"raw_{f}"] = df[col] if col else None
        new[f] = df[col].map(CLEANERS[f]) if col else None
    for c in EXTRAS:
        col = m.get(c)
        new[c] = pd.to_numeric(df[col], errors="coerce") if col else float("nan")
    blank = int(new["source_id"].isna().sum())
    new = new.dropna(subset=["source_id"])
    if new.empty:
        raise HTTPException(400, "no rows with a source ID")
    if new["source_id"].duplicated().any():
        raise HTTPException(400, "the source ID column has duplicate values inside the file")
    new.insert(0, "record_uid", system + "::" + new["source_id"])

    with db() as con:
        if con.execute("SELECT 1 FROM import_log WHERE file_hash=?", (file_hash,)).fetchone():
            raise HTTPException(409, "this exact file was already imported")
        src_old = pd.read_sql("SELECT * FROM source_info", con)
        clash = set(new["record_uid"]) & set(src_old["record_uid"])
        if clash:
            raise HTTPException(409, f"{len(clash)} record IDs already exist, e.g. {sorted(clash)[:3]}")

        # ---- backup before any write ----
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("data/backups").mkdir(parents=True, exist_ok=True)
        backup = f"data/backups/mdm_before_import_{stamp}.db"
        b = sqlite3.connect(backup)
        con.backup(b)
        b.close()

        # ---- stages 2 and 3 over old + new records (deterministic, no steward data involved) ----
        src = pd.concat([src_old, new[src_old.columns]], ignore_index=True)
        src[EXTRAS] = src[EXTRAS].apply(pd.to_numeric, errors="coerce")
        exact = build_candidates(src)
        pairs = candidate_pairs(src) | {(r.record_uid_1, r.record_uid_2) for r in exact.itertuples()}
        fuzzy = score_pairs(src, pairs, exact)

        # ---- stage 4, incremental: existing golden records and steward merges are left alone ----
        nu = set(new["record_uid"])
        gmap = {r[0]: r[1] for r in con.execute("SELECT record_uid, golden_id FROM record_golden_map")}
        fz = fuzzy[fuzzy["record_uid_1"].isin(nu) | fuzzy["record_uid_2"].isin(nu)]
        match = fz[fz["decision"] == "MATCH"]
        uf = UnionFind(list(nu))
        touches = defaultdict(set)
        for r in match.itertuples():
            if r.record_uid_1 in nu and r.record_uid_2 in nu:
                uf.union(r.record_uid_1, r.record_uid_2)
        for r in match.itertuples():
            a, b2 = r.record_uid_1, r.record_uid_2
            if (a in nu) != (b2 in nu):
                n, o = (a, b2) if a in nu else (b2, a)
                touches[uf.find(n)].add(gmap[o])
        comps = defaultdict(list)
        for u in sorted(nu):
            comps[uf.find(u)].append(u)
        next_n = max(int(g[1:]) for g in set(gmap.values())) + 1
        new_map, created, joined = {}, 0, 0
        for root, members in comps.items():
            existing = sorted(touches.get(root, []))
            if existing:                      # join the lowest golden id; other links go to review
                target, joined = existing[0], joined + len(members)
            else:
                target, next_n, created = f"G{next_n:05d}", next_n + 1, created + 1
            for u in members:
                new_map[u] = target
        all_map = {**gmap, **new_map}

        # review queue rows: REVIEW pairs, plus MATCH pairs that would have joined two golden records
        rq = []
        for r in fz.itertuples():
            ga, gb = all_map[r.record_uid_1], all_map[r.record_uid_2]
            if r.decision == "REVIEW" or (r.decision == "MATCH" and ga != gb):
                d = {c: getattr(r, c) for c in fuzzy.columns}
                d.update(decision="REVIEW", golden_id_1=ga, golden_id_2=gb, conflict=0,
                         status="PENDING" if ga != gb else "IN_SAME_CLUSTER")
                rq.append(d)

        # rebuild only the affected golden records, then re-apply steward corrections
        affected = sorted(set(new_map.values()))
        sub = src[src["record_uid"].map(all_map).isin(affected)]
        systems = sorted(set(src["source_system"]))
        pri = {f: o + [x for x in systems if x not in o] for f, o in load_priorities().items()}
        _, g_new, l_new = survive(sub, {u: all_map[u] for u in sub["record_uid"]}, pri)
        marks = ",".join("?" * len(FIELDS))
        for i, rec in g_new.iterrows():
            for fld, val in con.execute(
                    f"SELECT field, new_value FROM steward_audit_log WHERE golden_id=? "
                    f"AND field IN ({marks}) ORDER BY id", (rec["golden_id"], *FIELDS)).fetchall():
                g_new.at[i, fld] = val

        # ---- write ----
        ph = ",".join("?" * len(affected))
        con.execute(f"DELETE FROM golden_records WHERE golden_id IN ({ph})", affected)
        con.execute(f"DELETE FROM golden_lineage WHERE golden_id IN ({ph})", affected)
        g_new.to_sql("golden_records", con, if_exists="append", index=False)
        l_new.to_sql("golden_lineage", con, if_exists="append", index=False)
        new[["record_uid"]].assign(golden_id=new["record_uid"].map(new_map)).to_sql(
            "record_golden_map", con, if_exists="append", index=False)
        new[list(src_old.columns)].to_sql("source_info", con, if_exists="append", index=False)
        exact.to_sql("exact_candidates", con, if_exists="replace", index=False)
        fuzzy.to_sql("fuzzy_candidates", con, if_exists="replace", index=False)
        if rq:
            pd.DataFrame(rq).to_sql("review_queue", con, if_exists="append", index=False)
        now = datetime.now(timezone.utc).isoformat()
        con.execute("INSERT INTO import_log (filename, file_hash, source_system, rows_imported, "
                    "new_golden, joined_existing, review_pairs, steward, backup, imported_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (body.filename, file_hash, system, len(new), created, joined, len(rq),
                     body.steward, backup, now))
        con.execute("INSERT INTO steward_audit_log (golden_id, field, old_value, new_value, steward, "
                    "reason, changed_at) VALUES (?,?,?,?,?,?,?)",
                    ("IMPORT", "import", body.filename, f"{len(new)} records into {system}",
                     body.steward, body.reason, now))
        return {"system": system, "rows_imported": len(new), "blank_id_skipped": blank,
                "new_golden_records": created, "records_joined_to_existing": joined,
                "review_pairs_added": len(rq), "backup": backup}


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