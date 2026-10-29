# CRM-UI-S2 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, Control Plane change, or database migration.

## Summary

The Records list is a compact filter panel and a paginated table inside the existing CRM shell. Search, form, source, created dates, sort, page size, and server pagination behave as before. The shell applies the tenant configuration document that the Control Plane already stores. No new configuration field was added.

## Tenant configuration contract

An organization in this product is a tenant. The Control Plane does not store a separate organization theme. Tenant configuration is one document per `tenant_id` at `GET /api/v1/tenants/{tenant_id}/configuration`, schema version 1. Product access returns the registry `tenant_name`. That name is not a color or typography source.

The CRM already called that route from `readBranding`. This pass reads the same document and maps it with the Control Plane precedence:

- `profile.display_name` is the shell title when it is present. Otherwise the shell keeps the registry `tenant_name`.
- `branding.primary` wins over `brand_tokens.primary_color`. `branding.secondary` wins over `brand_tokens.secondary_color`.
- Background, surface, text, muted text, and border come only from `brand_tokens`. Text and background are applied together only when their contrast is at least 4.5:1. Surface and muted text use the same readability check the Control Plane uses before painting those tokens.
- `logo` and `favicon` are applied only when the URL is HTTP or HTTPS.
- A 403 or 404 from configuration leaves the platform palette and the letter mark. The shell stays usable.

Switching the path tenant reloads product access, permissions, and this configuration document through the existing shell effect.

## Configuration gaps

- `GET /api/v1/tenants/{tenant_id}/presentation` is not called. The only approved typography value is `platform`, the only navigation appearance is `platform`, the module hide list has no approved keys, and no widget key is approved. The CRM font stack in `--font` is already the platform stack.
- `--color-secondary` is set when a secondary color is present. Existing CRM actions use the primary color, which is also how the Control Plane shell treats secondary.
- Success, warning, and error colors are product tokens. They are not in the tenant configuration document.
- There is no tenant-configurable label for Records, forms, or columns.
- Export is not implemented, so the results header has no Export action.
- The record list has no Priority field. The Details column shows the server `summary` values. Record ID is the public number.

## Records layout

Desktop uses three filter columns: search, form, and source; created from, created to, and sort; page size with Search and Clear. Tablet uses two columns and keeps the two date fields side by side. Narrow screens use one column. The results are a table: Record ID, Name, Form, Source, Created, Updated, Details, and Open. Below 640 pixels, Form, Source, Updated, and Details are hidden and the table frame can scroll. The page itself does not grow sideways.

There is one Clear button, next to Search. It clears search text, form, source, and both dates, and returns to the first page. Sort and page size stay. There is no filter-chip row. Page size in the filter row and Rows per page in the footer write the same limit. The count, range, and page buttons use the list response `total`, `offset`, `limit`, and the returned rows. Sort remains the existing allowlist: created date, updated date, and record number.

## Files

Modified: `frontend/src/services/platform.ts`, `frontend/src/features/shell/CrmShellPage.tsx`, `frontend/src/styles.css`, `frontend/src/features/records/RecordsPanel.tsx`, `frontend/tests/records.test.tsx`, `frontend/tests/shell.test.tsx` (6).

New: `docs/sprints/crm-ui-s2/implementation-report.md` (1).

The limit used by the previous sprints is 10 modified and 20 new.

## Tests and build

`npm test` from `frontend`: **35 passed** (12 shell, 11 project, 4 form, 4 form-version, 4 records).

`npx vite build` from `frontend` completed. Output is under `frontend/dist`, which is gitignored.

The frontend has no lint script and no ESLint config. `npx tsc --noEmit` still exits 2 on the existing errors in `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. The records and shell files changed here are not in that error list.

Backend tests were not run. No backend file was changed.

## Browser check

Signed in at `http://localhost:5174` as the existing CRM lead reader and opened Recording gate. The list showed `Records (8)` and, at page size 5, `Showing 1–5 of 8 records`, then page 2 as `Showing 6–8 of 8 records`. Search for `S2-REC-0001` returned one row on page 1. Clear restored eight records and kept page size 5. Record-number sort returned `S2-REC-0001` through `S2-REC-0008` on the first page. Open reached the existing detail view, including Edit and Archive.

At 1280 pixels the filter grid was three columns and the table fit the content width. At 741 pixels the grid was two columns with the date fields together. At 390 pixels the filters were one column, the extra table columns were hidden, and the document did not scroll sideways. Records stayed the selected navigation item.

That sign-in does not have `configuration.read`, so configuration returned the existing handled 403 and the shell kept the platform palette. Color precedence is covered by the shell tests.

## Known limitations

- Presentation, secondary button styling, export, and a Priority column are the gaps above.
- Clear does not reset sort or page size.
- `npx tsc --noEmit` is still not clean.
- No commit, push, merge, or deployment was performed.
