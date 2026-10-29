# CRM-S7 explanation script — records, list, search, and detail

Recording: `docs/sprints/crm-s7/recording.webm` (8,065,302 bytes, VP9, 1280×720, 118.76 seconds).

This narration follows that recording. The capturing script logged each step below and exited successfully. The page is the CRM shell at `http://localhost:5174`. The organization and sign-in come from the running Control Plane. The CRM API is the running Aadi CRM process. The password stays masked. No session cookie is shown.

The first signed-in address is the existing local test identity `playwright-recording@example.com`. It is a project manager on Recording gate. The second address is `playwright-member@example.com`. That identity does not have CRM records access. This recording does not change users, roles, permissions, or project memberships.

## What the recording is checking

Original Sprint 5 lets a project manager create a record from a published form version, see that record keep version 1 after version 2 is published, edit it against that same version, search it on the server, archive it, and keep a sign-in without CRM access out of the record list.

## Sequence

1. The shell opens on the sign-in form. The email `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations.
2. Bootstrap recording 1792111368748 is opened. Records is opened. Recording gate is opened. The heading is Recording gate. Earlier records from this session are already in the list.
3. Forms is opened, then Recording gate. New form is opened. The name Record capture and the description Internal record capture are entered. Create form opens the draft.
4. A required text field is added. The label is School name, the identifier is `school_name`, and the section is Contact.
5. A dropdown is added. The label is Priority, the identifier is `priority`, the section is Qualification, and the options are Hot, Warm, and Cold.
6. Publish version opens the review. Confirm publish runs. The page shows Render version 1.
7. Records is opened, then Recording gate, then New record. The form choice is Record capture · version 1. The page shows the published School name field.
8. Save record with the field empty shows "School name is required."
9. School name is filled with North school. Priority is set to Hot. Save record opens the detail. The heading is S2-REC-0004. The field label is School name. The value is North school. The page shows version 1.
10. Forms is opened, then Recording gate, then Record capture. Edit School name changes the label to Campus. Save field stores that draft change. The button becomes Edit Campus.
11. Publish version runs again. Confirm publish runs. The page shows Render version 2.
12. The Recording gate record list is opened and S2-REC-0004 is opened. The field label is still School name. The Campus label is absent. The value is still North school. The page still shows version 1.
13. Edit record opens. The page says "Saving uses this version, not the current draft." School name is changed to North campus. Save record returns to the detail. The value is North campus. The field label is still School name.
14. Recording gate is opened. Search records is filled with North campus and Search is clicked. S2-REC-0004 is in the result.
15. Search records is filled with zzzz-no-match and Search is clicked. The page says "No matching records."
16. The search box is cleared and Search is clicked. S2-REC-0004 is opened. Archive record returns to the Recording gate list. S2-REC-0004 is no longer a link in that list. Earlier records from this session can still be there.
17. Sign out returns to the sign-in form. The address can still be the organization path.
18. `playwright-member@example.com` signs in. The shell opens that organization. The page says "Records is not available for this sign-in."
19. The Recording gate records address is opened directly. The page shows "You do not have permission to perform this action."

## What the recording does not show

The recording does not show an active project member opening only the records assigned to them. The development database has no active project member, and the second sign-in does not have the CRM module permission. Assigned-record access, a removed member, another project, another tenant, a permission that is only `users.read`, and a missing CSRF token are covered by `backend/tests/test_records.py`.

The recording changes the School name label to Campus. The field identifier stays `school_name`, so the detail does not show the sentence about a field that is missing from the current draft. That sentence is covered by `frontend/tests/records.test.tsx`.

The recording does not show status filters, assignee filters, saved views, duplicate warnings, attachments, or reassignment. Those depend on later sprint work. It does not show a file upload or an auto-number field.

Record gate, Record check, and Record proof were left on Recording gate by earlier capture attempts in this session. This recording creates Record capture and uses S2-REC-0004.

## Result

`playwright-recording@example.com` publishes Record capture version 1, creates S2-REC-0004 from that version, publishes version 2 with the Campus label, and still sees School name on the stored version 1 record. The same record is edited, found by server search, and archived. `playwright-member@example.com` cannot open Records and is denied on the Recording gate records address.
