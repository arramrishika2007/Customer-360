import re
import sqlite3
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
DB = Path("data/mdm.db")

SYSTEMS = {
    "SourceA": {
        "file": "core_banking.csv",
        "id": "Customer_ID",
        "common": {"name": "Name", "email": "Email", "phone": "Phone",
                   "dob": "DOB", "address": "Address"},
        "extras": {},
    },
    "SourceB": {
        "file": "credit_card.csv",
        "id": "Cust_Ref",
        "common": {"name": "Name", "email": "Email", "phone": "Phone",
                   "address": "Address"},
        "extras": {"credit_limit": "Credit_Limit"},
    },
    "SourceC": {
        "file": "loan_system.csv",
        "id": "Loan_Cust_ID",
        "common": {"name": "Name", "phone": "Phone", "address": "Address"},
        "extras": {"loan_amount": "Loan_Amt"},
    },
}

COMMON = ["name", "email", "phone", "dob", "address"]
EXTRAS = ["credit_limit", "loan_amount"]


def squash(s):
    """Trim and collapse whitespace; empty -> None."""
    if pd.isna(s):
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def fix_case(s):
    """Title-case only when the value is ALL CAPS or all lowercase."""
    if s is None:
        return None
    return s.title() if (s.isupper() or s.islower()) else s


def clean_name(s):
    return fix_case(squash(s))


def clean_email(s):
    s = squash(s)
    return s.lower() if s else None


def clean_phone(s):
    s = squash(s)
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) > 10:
        digits = digits[-10:]
    return digits or None


def clean_dob(s):
    s = squash(s)
    if not s:
        return None
    d = pd.to_datetime(s, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def load_abbreviations():
    ref = pd.read_csv(RAW / "reference_data.csv", dtype=str)
    pairs = sorted(zip(ref["Short_Form"], ref["Long_Form"]),
                   key=lambda p: -len(p[0]))
    return [
        (re.compile(r"(?<!\w)" + re.escape(short) + r"(?=\W|$)", re.IGNORECASE), long)
        for short, long in pairs
    ]


ABBREVIATIONS = load_abbreviations()


def clean_address(s):
    s = squash(s)
    if not s:
        return None
    s = fix_case(s)                       # FIX: case first, then expand abbreviations
    for pattern, long in ABBREVIATIONS:
        s = pattern.sub(long, s)
    return s


CLEANERS = {
    "name": clean_name,
    "email": clean_email,
    "phone": clean_phone,
    "dob": clean_dob,
    "address": clean_address,
}


def load_system(system, cfg):
    raw = pd.read_csv(RAW / cfg["file"], dtype=str)
    out = pd.DataFrame(index=raw.index)
    out["source_system"] = system
    out["source_id"] = raw[cfg["id"]].map(squash)

    for field in COMMON:
        header = cfg["common"].get(field)
        if header is None:
            out[f"raw_{field}"] = None
            out[field] = None
        else:
            out[f"raw_{field}"] = raw[header]
            out[field] = raw[header].map(CLEANERS[field])

    for col in EXTRAS:
        header = cfg["extras"].get(col)
        out[col] = pd.to_numeric(raw[header], errors="coerce") if header else None

    return out


def build_source_info():
    df = pd.concat([load_system(s, c) for s, c in SYSTEMS.items()],
                   ignore_index=True)
    df.insert(0, "record_uid", df["source_system"] + "::" + df["source_id"])
    cols = (["record_uid", "source_system", "source_id"]
            + [f"raw_{f}" for f in COMMON] + COMMON + EXTRAS)
    return df[cols]


def check(df):
    assert df["record_uid"].is_unique, "record_uid must be unique"
    print("rows per system:\n", df["source_system"].value_counts(), "\n")
    print("share of empty values per column:\n", df.isna().mean().round(2), "\n")
    print("phones not 10 digits:", (df["phone"].str.len() != 10).sum())


if __name__ == "__main__":
    df = build_source_info()
    check(df)
    DB.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as con:
        df.to_sql("source_info", con, if_exists="replace", index=False)
    print("\nsaved source_info:", df.shape)