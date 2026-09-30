# Customer 360

Master data management pipeline that merges customer records from three source systems (core banking, credit card, loan) into golden records, links transactions to them, and serves a steward dashboard.

## What it does

1. Loads and standardises records from the three source systems.
2. Finds exact-match and fuzzy-match candidate pairs.
3. Builds golden records with field-level lineage.
4. Links transactions to golden records through the source account ID.
5. Serves a FastAPI backend and a React dashboard for search, Customer 360 views, review of uncertain matches, field corrections and an audit log.

## Setup

```powershell
pip install -r requirements.txt
```

## Input data (not in this repo)

`data/raw/` and the database `data/mdm.db` are git-ignored. Before running, place these files in `data/raw/`:

- `core_banking.csv`
- `credit_card.csv`
- `loan_system.csv`
- `transaction_data.csv`
- `reference_data.csv`
- `ground_truth_mapping.csv`
- `trust_hierarchy.json`

## Run order

Run from the project folder. Each stage reads the database written by the previous one.

```powershell
python stage1_source_info.py
python stage2_exact_match.py
python stage3_fuzzy_match.py
python stage4_golden.py
python stage5_transactions.py
uvicorn stage6_api:app --reload
```

Then open:

- Dashboard: http://127.0.0.1:8000/dashboard
- API docs: http://127.0.0.1:8000/docs

## Files

| File | Purpose |
| --- | --- |
| `name_rules.py` | Name and address parsing and verdict rules shared by the matching stages |
| `stage1` to `stage5` | Pipeline stages, written to `data/mdm.db` |
| `stage6_api.py` | FastAPI backend (customers, reviews, corrections, audit, summary) |
| `dashboard.html` | React dashboard, served by the API at `/dashboard` (React loads from a CDN) |
| `check_exact_names.py`, `show_*.py` | Inspection helpers |

## Dashboard tabs

- **Summary:** counts, source-system split and quality score distribution.
- **Customers:** search, paging, a filter for quality below 100, and a Customer 360 view with sources, exact and fuzzy match evidence, transactions and field corrections.
- **Review queue:** uncertain pairs grouped into merge decisions, each approved or rejected by a steward.
- **Audit log:** every correction, merge and rejected review.

## Things to know

- Approving a review merges two golden records. It edits four tables and is not reversible through the API.
- Rerunning stages 1 to 5 rebuilds the pipeline tables and discards steward merges and corrections. The audit and review decision tables are kept.
- `quality_score` is a completeness score, 20 points for each of name, email, phone, dob and address that is filled in. It is not recomputed after a merge.
- `net_flow` adds credits and subtracts debits across core, card and loan accounts, so it is an activity indicator and not a balance.
