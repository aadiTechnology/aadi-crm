# MVP acceptance matrix — original roadmap Sprint 12

Date: 21 October 2026. Status is PASS, FAIL, BLOCKED, OWNER DECISION REQUIRED, or NOT TESTED. PASS means the technical evidence holds. It does not mean the owner accepted the release.

The PRD file used by the sprint plans is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. It is not in this repository. Role names found there include Platform Super Admin, Tenant Admin, and Project Manager. The CRM code uses `project_manager` and `project_member`. No separate account for each role was found, so human execution of the UAT plan was not possible.

| Criterion | Status | Evidence | Gap |
|---|---|---|---|
| Tenant and project isolation | PASS | Backend suite, including cross-tenant and membership tests | None at high severity |
| Record authorization through `authorize_record` | PASS | Record routes call it. Removed members lose record identifiers on reminders | Reminder metadata after removal is an owner decision |
| CSRF on state-changing requests | PASS | Existing tests. The check was not weakened | None |
| Forms and published versions | PASS | Frontend form-version tests. Builder opened in the browser | Human UAT not run |
| Record list, search, and a populated table | PASS for engineering checks | 12-row list at 390, 768, and 1280. Page overflow 0 | Human UAT not run. Record edit not opened |
| Follow-ups and reminders | PASS for automated rules | Follow-up and reminder tests | Human UAT not run |
| Import, export, and Sprint 10 reconciliation | PASS for the stored Preschool, Space View, and Hiring results | `crosswalk.json` mismatch sum 0. Paneerwala deferred | Owner has not accepted Sprint 10. This pass did not re-import |
| Dashboard KPIs | PASS in automated tests | Reporting tests match lists and queues | Numeric cards were not read from the browser in this pass |
| Audit visibility and denial | PASS for the implemented rule | 403 without `audit.read`, shown in the browser. Metadata stripped | Tenant-wide scope is an owner decision |
| Sensitive fields hidden from unauthorized callers | PASS for the tested cases | Cross-tenant responses omit foreign names. Audit metadata is dropped | None newly found |
| Accessibility | NOT TESTED as conformance | Axe found no violations on the settled screens that were scanned | Form builder overflows at CSS zoom 200%. Not a WCAG claim |
| Responsive layout | PASS for the opened screens | `responsive-validation.md` | Record-edit dialog not opened |
| Performance | PASS as a small-database measurement | 1,000 rows, 4 readers, p95 under 80 ms | 50,000-record PRD target not tested. SLO not approved |
| Request logging | PASS on a disposable process | `observability.md` | Port 8001 was not restarted. No alerts |
| Backup policy and ownership | OWNER DECISION REQUIRED | PRD text describes daily backups and 30-day retention | Not confirmed or implemented for this environment |
| Restore | BLOCKED | Live file integrity is `ok` | No backup artifact was restored |
| Human UAT | FAIL | `uat-results.md`. No case passed | Four roles were not executed |
| TypeScript | FAIL | `tsc --noEmit` exit 2 | No approved waiver |
| Deployment and support ownership | OWNER DECISION REQUIRED | `support-ownership.md` | No primary or backup owner named |
| Production deployment | NOT TESTED | No deploy was authorized or performed | Separate authorization required |

## Release gate

**NOT READY.** Mandatory blockers that remain: backup policy and ownership, restore not verified, human UAT not passed, TypeScript not passed and not waived, monitoring not configured, and deployment and support owners not named. Sprint 10 does not show an unexplained key-field mismatch. Paneerwala stays deferred by the earlier owner decision.
