# CRM-S12 technical validation — original roadmap Sprint 10

Date: 21 October 2026. Commands were run on the current tree after the template catalog and the Sprint 9 closure documents were in place.

## Commands

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**65 passed**, 1 Starlette `httpx` deprecation warning, in 22.64 seconds. The new file contributed 4 tests. The previous Sprint 9 review on the same day, before these tests existed, was 61 passed.

Frontend, from `frontend`, earlier on 21 October 2026 before any Sprint 10 file was added. No frontend file was modified after that run.

`npm test`

**48 passed** (8 files) in 12.57 seconds.

`npx vite build`

Succeeded in 2.13 seconds. Assets: `dist/assets/index-XPNS2jy0.css` (15.20 kB) and `dist/assets/index-C9mEIzZT.js` (430.47 kB).

`npx tsc --noEmit`

Exited 2. This is not a pass. The errors are the existing baseline:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

No Sprint 10 frontend source was added, so those errors are unchanged.

## Database

The domain-template test applies the existing migrations, including `008_imports.sql`, to a temporary SQLite file. It does not open `backend/data/aadi_crm.sqlite`. The test compares that file's size and modification time before and after and they were unchanged. No schema migration was added for Sprint 10.

## Template and migration checks

| Check | Result |
|---|---|
| Four-sheet workbook rejected | `test_four_sheet_workbook_is_rejected_and_paneerwala_is_not_prepared` |
| Paneerwala not prepared | Same test. 24 timestamp values in column A, 0 numeric lead ids, 24 non-date text values in column D, 24 numbers in column E |
| Decimal Excel serial is normalized before import | `test_excel_serial_with_a_decimal_is_not_a_date_until_normalized`. `46362` becomes `2026-12-06`. `46362.0` does not, until the CSV is prepared |
| Published field order, type, and required flag | `test_templates_reconcile_on_a_disposable_database` |
| Preview creates no records | Same test, record total stays 0 |
| Counts reconcile | Preschool 4/4/0. Space View 12 submitted, 11 accepted, 1 rejected. Hiring 13/13/0. Equation holds |
| Key fields | Same test. No mismatches and no missing values for non-blank cells |
| Repeated commit and same idempotency key | Record total unchanged |
| Cross-tenant job read | 404 |
| Member error report | 404, and the version id is not in the body |
| CSRF | Commit without the header returns 401 |
| Synthetic duplicate review, invalid row, formula export | `test_synthetic_duplicate_review_and_formula_export`. Accepted 1, rejected 1, skipped 1. Export contains `'=Example note` and does not contain Example West |

## Browser

`node docs/sprints/crm-s12/record-demo.mjs` exited 0. The recording is 107.76 seconds. Sampled frames are described in `explanation-script.md`. The capture log for stamp `886025` published the three forms, rejected `notes.txt`, imported the synthetic file, logged the error-report checks, logged `NARROW_OVERFLOW false`, and reached the member-denial waits.

An earlier run with stamp `707601` also created the three synthetic projects and one imported record, then failed while looking for a link named Example North. That run's projects were left in place. The successful recording replaced `recording.webm`.

## Not claimed

Paneerwala was not migrated. Exactly-once behavior is not claimed for a second idempotency key. Owner acceptance is not claimed.
