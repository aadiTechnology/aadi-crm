# CRM-S11 technical validation — original roadmap Sprint 9

Date: 20 October 2026. Commands were run on the current tree after the import and export code was in place. Earlier Sprint 8 counts are not reused here.

## Commands

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**61 passed**, 1 Starlette `httpx` deprecation warning, in 18.74 seconds.

Frontend, from `frontend`:

`npm test`

**48 passed** (8 files) in 11.50 seconds. The import file contributed 3 tests. jsdom printed `Not implemented: navigation to another Document` when the download link was clicked. The tests still passed.

`npx vite build`

Succeeded in 1.98 seconds. Assets: `dist/assets/index-XPNS2jy0.css` (15.20 kB) and `dist/assets/index-C9mEIzZT.js` (430.47 kB).

`npx tsc --noEmit`

Exited 2. This is not a pass. The errors are the existing baseline:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

Import sources are not in that list.

## Migration

`008_imports.sql` is additive. The disposable database used by pytest applies it and expects empty `import_jobs` and `import_rows`. The shared development database already contains the tables. It was not reset and no existing rows were deleted.

## Import and export checks

| Check | Result |
|---|---|
| CSV and XLSX parse, limits, and XLSX formula cells | `test_csv_and_xlsx_parse_limits_and_formula_cells`, `test_formula_limit_uses_the_configured_ceiling` |
| Dry-run creates no record and does not move the sequence | `test_preview_does_not_create_records_and_commit_reconciles` |
| Accepted, rejected, and skipped counts reconcile | Same test. Header excluded |
| Repeated commit returns the original outcome | `test_same_file_key_does_not_create_a_second_record_under_two_commits` |
| Same key with a different file returns 409 | Same test |
| Concurrent commit inserts one record | `test_concurrent_commit_inserts_one_record` |
| Cross-tenant and non-owner job access, duplicate hiding, filtered export, formula prefix | `test_authorization_duplicate_visibility_and_export_filters` |
| Malformed files create nothing | `test_malformed_files_are_rejected` |
| CSRF on a write without the header | Covered by the authorization test, 401 |
| UI preview, duplicate decision, commit, repeat, and export count | `frontend/tests/imports.test.tsx` |

Invalid rows stay invalid at commit unless they pass `validate_values` again. The preview test commits a mixed file and checks that the invalid row is rejected.

## Browser capture

`node docs/sprints/crm-s11/record-demo.mjs` exited 0. The recording is 102.44 seconds. Sampled frames, not continuous playback, are described in `explanation-script.md`.

The capture log for project Import gate IMP486934:

- Unsupported upload: `Upload a .csv or .xlsx file.`
- Error report: skip on row 2, possible email match with IMP486934-0001, missing school name, invalid email
- Export file contained `'=Fresh lane` and did not contain `Existing lane`
- `NARROW_OVERFLOW false` at 390×720
- After repeat, the project has two records: IMP486934-0001 manual and IMP486934-0002 import

The member denial sentences were waited on by the script. They are not visible in the sampled frames. The last frame is "Checking access".

## Not claimed

Exactly-once external processing is not claimed. Live email delivery is not part of this sprint. Owner acceptance is not claimed.
