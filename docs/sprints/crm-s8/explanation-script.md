# CRM-S8 explanation script — reused record list, filters, pages, and archive

Recording: `docs/sprints/crm-s8/recording.webm` (6,618,082 bytes, VP9, 1280×720, 102.20 seconds).

This narration follows that recording. The capture script logged each step below and exited successfully. The page is the CRM shell at `http://localhost:5174`. The CRM API is the already running process on port 8001. The organization and sign-in come from the running Control Plane. The password stays masked. No session cookie is shown.

The first signed-in address is `playwright-recording@example.com`, a project manager on Recording gate. The second address is `playwright-member@example.com`. This recording does not change users, roles, permissions, or project memberships.

## What the recording is checking

Original roadmap Sprint 5 already created, listed, edited, numbered, filtered, sorted, paged, and archived records. This pass reuses that behavior. The recording shows the historical form version, a new project record number, server filters and sort, a page size of 5 with a second page, archive, and a sign-in that cannot open Records.

## Sequence

1. The shell opens on the sign-in form. `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations. Bootstrap recording 1792111368748 is opened. Records is opened. Recording gate is opened.
2. S2-REC-0002 is opened. Edit record shows "Published version 1. Saving uses this version, not the current draft." The field label is School name. The value is set to West campus. The current published label for that form is Campus. The Campus label is not the field label on this edit.
3. New record is opened. The form choice is Record capture · version 2. Source is Phone Call. The published field label is Campus. Campus is filled with East campus. Priority is Hot.
4. Save record opens the detail. The capture script read the heading `S2-REC-0009`. A sampled frame of that detail was still the loading skeleton, so this review does not claim the heading was seen on screen. The later search box contains `S2-REC-0009`.
5. The signed-in page creates three more records through the CRM API so the list has more than five active rows. They are Page lane, Page row, and Page seat, source Website. The script logged `S2-REC-0010`, `S2-REC-0011`, and `S2-REC-0012`. Those three creates are API calls, not clicks on New record.
6. The Recording gate list is opened. Source is set to Phone Call. Sort is set to Record number. Search is clicked. A sampled frame shows those two controls. The matching row is below the filter form in that frame.
7. Search records is filled with `zzzz-no-match` and Search is clicked. The script waited for "No matching records." That sentence sits under the filter form and was not in the sampled frame.
8. The search is cleared, Source is set back to All sources, and Page size is set to 5. The list shows "Showing 1–5 of 9", sorted by record number, with S2-REC-0001 on the first page. Next is clicked. The next page shows S2-REC-0011 and S2-REC-0012, with Previous available. Previous returns toward the first page.
9. Search records is filled with `S2-REC-0009`. That record is opened and Archive record is clicked. The list is opened again and the same number is searched. The script waited until the number was not a link and "No matching records." was present. The sampled frame shows the number in the search box. The empty-result sentence is under the filter form and was not in that frame.
10. The direct address of the archived record is opened. The file ends on "Checking access" for that address. The capture script then waited for "The requested resource was not found." This review did not see that sentence in the extracted frames.
11. Sign out returns to the sign-in form. `playwright-member@example.com` signs in, opens Bootstrap recording 1792111368748, and the sidebar says "Records is not available for this sign-in." The same note is shown for Leads, Projects, and Forms.
12. The Recording gate records address is opened directly. The saved file ends while that page still says "Checking access." The capture script waited for "You do not have permission to perform this action." and then paused. That sentence was not visible in the extracted frames, including the last frame.

## What the recording does not show

The recording does not show an assigned project member opening only their own records. `playwright-member@example.com` does not have CRM module access. Assigned-record denial is in `backend/tests/test_records.py`.

It does not show a status filter, an assignee filter, a saved view, a duplicate warning, or a restore action. Those are not this scope.

An earlier capture attempt in this same session created S2-REC-0005 through S2-REC-0008 before the member step timed out. S2-REC-0005 is archived. S2-REC-0006, S2-REC-0007, and S2-REC-0008 remain listed. The successful recording is the file named above and uses S2-REC-0009.

## Result

`playwright-recording@example.com` edits S2-REC-0002 on published version 1 while the field label stays School name, creates S2-REC-0009 from Record capture version 2, filters and sorts on the server, moves from page 1 to the next page at page size 5, and archives S2-REC-0009. `playwright-member@example.com` is shown the Records note for that sign-in. The direct-address denial sentence was reached by the script and was not visible in the extracted frames.
