# CRM-S9 explanation script — activity timeline and follow-ups

Recording: `docs/sprints/crm-s9/recording.webm` (6,814,400 bytes, VP9, 1280×720, 89.40 seconds).

This narration follows that recording. The capture script logged each step below and exited successfully. The page is the CRM shell at `http://localhost:5174`. The CRM API is the already running process on port 8001. The organization and sign-in come from the running Control Plane. The password stays masked. No session cookie is shown.

The first signed-in address is `playwright-recording@example.com`, a project manager on Recording gate. The second address is `playwright-member@example.com`. This recording does not change users, roles, permissions, or project memberships.

`docs/sprints/crm-s9` is the evidence folder for original roadmap Sprint 7. It is not original roadmap Sprint 9.

## What the recording is checking

The manager opens Recording gate, creates record S2-REC-0013 from the published form, adds three follow-ups on that record, edits the email due time, completes the call with an outcome, opens the Overdue, Today, and Upcoming queues, and signs in as an account that cannot open Follow-ups.

Civil dates in this capture are 19 October 2026, 20 October 2026, and 21 October 2026. Due date and due time are India Standard Time.

## Sequence

1. The shell opens on the sign-in form. `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations. Bootstrap recording 1792111368748 is opened. Records is selected. The sidebar shows Records and Follow-ups. The records page says CRM is available in this organization.
2. Before the new record is created, the script cancels open follow-ups already sitting in the Recording gate queues. Those cancels are API calls from the signed-in page. They are not clicks on Cancel. The outcome stored for each cancel is "Cleared before the follow-up demonstration."
3. New record opens on Recording gate. The form choice is Record capture · version 2. The page says published version 2 is the version that will be saved. Campus is filled with Timeline lane. Priority is Warm. Save record opens S2-REC-0013. The detail shows Campus Timeline lane, Priority Warm, source Manual, and the form version reference. Activity first shows "Loading activity." Follow-ups shows the task-type filter.
4. A Note is added for 19 October 2026 at 09:00, summary "Overdue check," owned by `playwright-recording@example.com`. The saved card shows Note, Open, and "Due 2026-10-19 09:00 India Standard Time."
5. A Call is added for 20 October 2026 at 12:00, call status Connected, summary "Call today," with the same owner. An Email is added for 21 October 2026 at 09:30, summary "Upcoming email." The form states that due date and time use India Standard Time.
6. Edit Email sets the due time to 11:15 and the discussion summary to "Rescheduled visit." Save Email is clicked. A later frame of the record shows the activity timeline, newest first: "Follow-up completed" at 20 Oct 2026, 9:43 pm, by `playwright-recording@example.com`, with "Outcome: Spoke with the family"; then "Follow-up rescheduled" with "Email follow-up was rescheduled to 2026-10-21 11:15 India Standard Time"; then "Follow-up updated."
7. The Call card shows outcome "Spoke with the family" and Complete Call. The script waits until the completed outcome is on the record.
8. Follow-ups opens the Recording gate Overdue queue. The page says queues use India Standard Time and that a follow-up is in one queue only. The manager sees an Assignee filter set to All owners. The script waits for "Overdue check."
9. Today is opened. The heading is "Follow-ups due today." While that queue is still loading, the count line can still read "Showing 1 of 1" from the previous queue, and the table stays hidden. The script waits for "No follow-ups are due today."
10. Upcoming is opened. The script waits for "Rescheduled visit" and "2026-10-21 11:15." Sampled frames of this page show the Upcoming heading, the Assignee filter, and the loading skeleton. The loaded row is on screen for a short interval before sign-out.
11. Sign out returns to the sign-in form. `playwright-member@example.com` is entered. The password stays masked. Bootstrap recording 1792111368748 is opened. The sidebar says "Follow-ups is not available for this sign-in." The direct Follow-ups address shows "You do not have permission to perform this action." The script confirms "Overdue check" is absent from that page.

## What the sampled frames show

The extracted frames clearly show the new-record form, S2-REC-0013, the Note and Call cards, the email form, the completed and rescheduled timeline entries, the queue headings, the manager assignee filter, and the member permission denial.

The loaded Overdue, Today, and Upcoming tables occupy a short interval after each skeleton. The capture script waited for the row text named above and exited 0. A reviewer watching the file should pause on those queue pages to read the rows.

## What the recording does not show

The recording does not show an assigned project member opening only their own follow-ups. `playwright-member@example.com` does not have CRM module access. Assigned-record denial, cross-project denial, cross-tenant denial, a removed member, and a missing CSRF token are in `backend/tests/test_followups.py`.

It does not show record reassignment, a status change, a duplicate warning, a reminder, or a mobile viewport. The capture is 1280×720.

Earlier capture attempts in this same session created follow-ups on S2-REC-0012. The successful recording cancels the open queue items from those attempts and uses S2-REC-0013.
