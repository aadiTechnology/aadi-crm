# Explanation script — original roadmap Sprint 11

Date: 21 October 2026. This script matches `docs/sprints/crm-s13/recording.webm`.

The recording is VP9, 1280×720, 86.20 seconds, 7,561,501 bytes. It was captured headlessly with Playwright after the CRM API on port 8001 was restarted so the new routes were loaded. The shared development database was not reset. The script created synthetic projects in that database.

Stamp `830912`. Project `fe1a8bfb-149d-42d6-ba10-8d6e8f2323a9`, named `KPI yard 830912`.

## What the recording shows

1. The recording user signs in and opens Bootstrap recording 1792111368748.
2. The project KPI page for `KPI yard 830912` shows Active records 2, Records created 2, Overdue 1, Due today 1, Upcoming 1, and Completed follow-ups 1. The two records and four follow-ups are synthetic test data created for this capture. One follow-up was completed through the existing complete action.
3. The workload table and the due-date table are scrolled into view. Due-date counts are not links. The queue cards are.
4. The created-date period is changed to 1 January 2020 through 2 January 2020. Records created becomes 0. Active records stays 2. The drill-down shows Records (0) and "No matching records", then returns to the KPI page.
5. The period is set back to 21 October 2026. Records created is 2. View active records shows Records (2), `KPI North 830912` and `KPI South 830912`.
6. View overdue follow-ups shows Overdue follow-ups and "Showing 1 of 1" for `KPI North 830912`. `KPI South 830912` is not in that list. Upcoming also shows "Showing 1 of 1".
7. View completed follow-ups shows "The list has 1 completed follow-ups. The KPI count is 1." Back to KPI overview closes that list.
8. `KPI empty 830912` shows Active records 0, Overdue 0, "No active records.", and "No open follow-ups in these queues."
9. The Audit page for the recording user shows the permission denial. The capture log is `AUDIT_STATE denied` and `AUDIT_ROWS 0`. No audit table and no credential text are shown. The platform did not return events to this user.
10. At 390 pixels wide, the KPI page does not overflow horizontally. The capture log is `NARROW_OVERFLOW false`.
11. After sign-out, the existing member account opens the same project KPI URL and the audit URL. Both show "You do not have permission to perform this action." The synthetic record name is not shown. This member does not have the CRM project module. The assigned-record case is in `backend/tests/test_reporting.py`, not in this recording.

## Not shown

The recording does not show a populated audit table, an audit filter, or the audit service being unavailable. Those behaviors are in `backend/tests/test_audit_view.py`. No synthetic audit event was inserted. CRM actions in this sprint do not append platform audit events.
