# Unified Customer 360

A master data management (MDM) project for a bank. It combines customer records from three source systems (Core Banking, Credit Card, Loan), cleans and matches them, builds one **golden record** per customer, and serves a Customer 360 dashboard with steward review tools.

## Features

- **Standardise and combine:** names, emails, phones and addresses from all systems are cleaned and stored in one `source_info` table.
- **Matching:** exact matching, then fuzzy matching with name and address rules. Strong matches merge automatically, and borderline pairs go to a review queue.
- **Golden records:** survivorship rules pick the best value per field, with lineage showing which source record each value came from.
- **Transactions:** linked to golden records through the account ID, with a per-customer summary.
- **Customer 360 dashboard (React):**
  - Summary of golden records, multi-system customers, pending reviews and transactions
  - Customer search, with a filter for records below 100% quality
  - Per-customer view: golden record, source records, match evidence, transactions, corrections
  - **Transaction filter by source system** (All / Core / Card / Loan, plus any imported system)
  - Review queue to approve a merge or keep records separate
  - Audit log of every steward change, merge and import
  - **Import tab:** upload an external CSV or JSON file, map its columns, and run it through the same cleaning, matching and merging rules. Uncertain matches go to the review queue.
- **Safety:** every import makes a database backup first, the same file cannot be imported twice, and steward corrections are kept when golden records are rebuilt.

## Project structure

```
Customer 360/
  data/
    raw/                    source CSVs (core_banking, credit_card, loan_system)
    mdm.db                  SQLite database (generated)
    backups/                automatic backups made before each import
  stage1_source_info.py     clean and standardise, build source_info
  stage2_exact_match.py     exact candidate pairs
  stage3_fuzzy_match.py     fuzzy candidate pairs and scoring
  stage4_golden.py          clustering, survivorship, golden records
  name_rules.py             name comparison rules
  stage6_api.py             FastAPI backend (customers, reviews, audit, import)
  frontend/                 React dashboard (Vite)
    src/
      api.js                backend calls
      App.jsx               tab layout
      components/           Summary, Customers, Detail, Reviews, Audit, Import
```

## Tech stack

- **Backend:** Python 3.13, pandas, RapidFuzz, SQLite, FastAPI, Uvicorn
- **Frontend:** React 18 with Vite

## Setup

### 1. Python backend

```powershell
cd "Customer 360"
python -m venv .venv
.venv\Scripts\activate
pip install pandas rapidfuzz fastapi uvicorn
```

Run the pipeline stages in order so that `data/mdm.db` is built (stage 1 through the transaction linking stage). The database is not stored in the repository.

### 2. React frontend

```powershell
cd frontend
npm install
```

## Running the app

Use two terminals.

**Terminal 1: backend** (from the project root)

```powershell
uvicorn stage6_api:app --reload
```

The API runs at http://127.0.0.1:8000 and its interactive docs are at http://127.0.0.1:8000/docs.

**Terminal 2: frontend**

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. The Vite dev server forwards `/api/...` requests to the backend, so no CORS setup is needed.

## Importing external data

1. Open the **Import** tab and choose a `.csv` or `.json` file.
2. Check the preview and confirm the column mapping (ID, name, email, phone, DOB, address, credit limit, loan amount). Likely matches are guessed automatically.
3. Choose an existing source system or name a new one, enter your steward name, and click **Import**.

The new rows are cleaned like the original data, appended to `source_info`, matched against existing records, and merged into golden records. Only affected golden records change, and earlier steward merges and corrections are kept. Borderline matches appear in the **Review queue**.

## API overview

| Endpoint | Purpose |
|---|---|
| `GET /summary` | Dashboard totals |
| `GET /customers` | Search golden records (`q`, `quality_below`, `limit`, `offset`) |
| `GET /customers/{golden_id}` | Full customer view |
| `POST /customers/{golden_id}/override` | Steward correction of a field |
| `GET /reviews`, `POST /reviews/decide` | Review queue and merge decisions |
| `GET /audit` | Steward audit log |
| `POST /import/preview`, `POST /import/commit`, `GET /import/log` | External file import |
| `GET /tables`, `GET /tables/{name}` | Raw table viewer |

## Notes

- `data/mdm.db`, `data/backups/` and raw data are excluded from Git because they may contain personal data. Use fake data when sharing.
- Always start the backend before the frontend.
