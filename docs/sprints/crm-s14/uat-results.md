# UAT results — original roadmap Sprint 12

Date: 21 October 2026. Executor: release engineer, using the existing synthetic recording sign-in. This was not the product owner and not a separate pass for each role. No customer file was opened. No record was created or archived.

Automated coverage is listed so it is not mistaken for human UAT.

## Human execution

| ID | Actual result | Status | Evidence |
|---|---|---|---|
| UAT-A1 | The recording user signed in and opened Bootstrap recording 1792111368748. The shell showed "CRM is available in this organization." Other tenants were not enumerated in this pass | Partial | `recording.webm`, sampled frames |
| UAT-A2 | Projects, forms, records, follow-ups, reminders, import, KPIs, and audit routes rendered an `h1`. Member administration and branding were not exercised | Partial | Overflow log in `responsive-validation.md` |
| UAT-A3 | Not run as an administrator denial in the browser | Not executed | — |
| UAT-M1 | The first project detail link rendered at 390 pixels wide. Its fields were not edited | Partial | Second headless pass, overflow 0 |
| UAT-M2 | The forms route rendered. A builder canvas was not opened | Not executed beyond the route | Forms overflow 0 |
| UAT-M3 | Not executed. No record was created | Not executed | — |
| UAT-M4 | The follow-up route rendered. A follow-up was not created | Not executed | — |
| UAT-M5 | The reminders route rendered. Failure rows were not opened | Not executed | — |
| UAT-M6 | The import route rendered and a sampled frame showed "Loading import". A file was not uploaded | Not executed | `recording.webm` frame at 11 seconds |
| UAT-M7 | Not executed | Not executed | — |
| UAT-M8 | The KPI and audit routes rendered. Counts and the audit denial were not read from the page in this pass | Partial | Routes returned an `h1` |
| UAT-P1 | Not executed with a project-member account | Not executed | — |
| UAT-P2 | Not executed in the browser | Not executed | — |
| UAT-P3 | Not executed in the browser | Not executed | — |
| UAT-O1 | Not executed against a live job | Not executed | — |
| UAT-O2 | Not executed against a live failure | Not executed | — |
| UAT-O3 | The backup and runbook documents were written. The owner has not named an operator, RPO, or RTO | Blocked | `backup-restore-ownership.md` |

No UAT case is Pass.

## Engineering evidence that is not UAT

These tests passed on 21 October 2026 and cover the same rules. They do not replace the table above.

- Tenant, project, CSRF, and removed-member behavior: `backend/tests/test_projects.py`, `test_records.py`, `test_forms.py`, `test_followups.py`, `test_reminders.py`, `test_imports.py`, `test_shell_isolation.py`
- KPI and audit denial: `backend/tests/test_reporting.py`, `backend/tests/test_audit_view.py`, `frontend/tests/reporting.test.tsx`, `frontend/tests/audit.test.tsx`
- Import reconciliation: `backend/tests/test_imports.py` and `backend/tests/test_domain_templates.py`

## Blocker

Human UAT is blocked on owner scheduling of the four roles, and on the backup decisions in UAT-O3.

## Later engineering pass, still not UAT

On 21 October 2026 a release engineer signed in with the existing recording user and opened the running app in headless Chrome. That person is not the product owner and is not a separate tester for each role. No case below changes to Pass.

What that pass did show, as engineering evidence only:

- The audit route, after loading, showed the permission denial at 1280×720, 768×1024, and 390×844.
- A project record list with 12 rows stayed inside the page width at those three sizes. The table used its own horizontal scroll at 390 and 768 pixels.
- The Preschool form builder showed the field palette and field properties at 390 pixels without page overflow.
- CSS zoom 200% at 1280×720 overflowed the form builder. See `responsive-validation.md`.
- Numeric KPI cards were not read from the page.

No customer file was opened. No record was created or archived. The four role accounts were not identified in the repository, so they were not used.
