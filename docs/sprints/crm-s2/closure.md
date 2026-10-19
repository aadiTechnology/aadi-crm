# CRM-S2 closure — tenant-scoped project management

Date: 19 October 2026. Repository: `aadi-crm` only. This note closes the project-management deliverable. It does not replace the evidence already stored in this directory.

## Status

The tenant-scoped project-management deliverable is complete for the scope that was implemented. The original sprint plan calls that scope Sprint 1 / CRM-S2 (projects). The work was delivered and recorded under the CRM-S2 label. This closure does not rename that evidence and does not mark later stories done.

Preserved evidence:

- `docs/sprints/crm-s2/recording.webm`
- `docs/sprints/crm-s2/explanation-script.md`
- `docs/sprints/crm-s2/implementation-report.md`

CRM-S1 files under `docs/sprints/crm-s1/` were already in the working tree and were not rewritten for this closure.

## Verification at closure

Before membership work started, the existing suite was run again on 19 October 2026:

- Backend, from `backend` with the project virtualenv: `python -m pytest -q` → **17 passed**, 1 warning. The warning is Starlette's deprecation notice that `httpx` with `starlette.testclient` should move to `httpx2`.
- Frontend, from `frontend`: `npm test` → **17 passed** (10 shell tests and 7 project tests).

Those counts match the CRM-S2 implementation report. They are the closure baseline, not the later membership suite.

The development SQLite file `backend/data/aadi_crm.sqlite` still had migration `001_projects.sql` and three project rows for tenant `e02812a0-8717-4f5f-be19-57f263daef52`: S2-DEMO archived, S2-LIVE archived, and S2-REC active. No project row was deleted for this closure.

## Known limitations

- The implementation was delivered under the CRM-S2 label, while its scope corresponds to Sprint 1 in the original sprint plan (project create, edit, search, filter, and archive).
- At closure, authorization still allowed a user with `crm.lead_management.read` to manage all projects in the tenant. Membership in the next sprint replaces that broad rule.
- `crm.project_management.manage` is not registered in the Control Plane. This closure does not register it.
- Business type, time zone, logo, start date, clone, and reactivate were not implemented.
- Archiving does not yet block new records, because records are a later sprint.
- The PRD v1.0 file named in the decision log (`Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`, 09 October 2026) is not in this repository.

The sprint-plan workbook outside this repository was not edited. Closure tracking for this repository is this note plus the preserved CRM-S2 report.

No commit, push, merge, tag, deploy, or Control Plane source or database change was made for this closure.
