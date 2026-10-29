# CRM-S10 explanation script — original roadmap Sprint 8

Recording: `docs/sprints/crm-s10/recording.webm` (10,260,145 bytes, VP9, 1280×720, 122.12 seconds).

This narration follows that recording and the capture log from `node docs/sprints/crm-s10/record-demo.mjs`, which exited 0. The page is the CRM shell at `http://localhost:5174`. The CRM API is the running process on port 8001. The password stays masked. No session cookie is shown.

The first signed-in address is `playwright-recording@example.com`, a project manager on Recording gate. The second address is `playwright-member@example.com`. This recording does not change platform permissions.

`docs/sprints/crm-s10` is the evidence folder for original roadmap Sprint 8. It is not original roadmap Sprint 10.

## What the recording is checking

The manager opens Reminders, creates record S2-REC-0016, adds a follow-up due 2026-10-20 at 09:00 India Standard Time, delivers reminders, opens that record from a reminder, runs delivery again without adding cards, forces the test email adapter to fail and then exhaust retries, retries one stopped row, checks a 390-pixel viewport, and signs in as an account that cannot open Reminders.

Civil dates in this capture are 19 October 2026 and 20 October 2026. The capture clock is the evening of 20 October 2026, so 09:00 on that day is already due.

Earlier attempts in this same session had already delivered reminders, so the successful recording does not open on an empty inbox. The empty inbox is covered by `frontend/tests/reminders.test.tsx`.

## Sequence

1. The shell opens on the sign-in form. `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations. Bootstrap recording 1792111368748 is opened. Reminders is selected. The page says reminders use India Standard Time and that a recorded email has not been delivered. A sampled frame shows "Loading reminders" under that sentence.
2. New record opens on Recording gate. The form choice is Record capture · version 2. Campus is filled with Reminder lane. Priority is Warm. Save record opens S2-REC-0016. A Note is added for 20 October 2026 at 09:00, summary "Morning reminder", owned by `playwright-recording@example.com`.
3. Reminders is opened again. Deliver pending reminders is clicked. The page reports: "The test adapter recorded 2 email reminders. Those emails were not delivered. In-app reminders delivered: 2. Temporary failures: 0. Stopped: 0." The script waits until "Open record S2-REC-0016" is present and counts 27 reminder cards. Those cards include reminders for earlier open follow-ups on this project, not only the new note. Delivery is project-scoped for a project manager.
4. Open record S2-REC-0016 is clicked. The record detail shows Reminder lane. A later frame shows the Note actions and the follow-up form, with "Morning reminder" at the top of that view.
5. Reminders is opened again and Deliver pending reminders is clicked. The page reports that the test adapter recorded 0 email reminders. The script counts 27 cards again. The second run did not add a card.
6. Back on S2-REC-0016, an Email follow-up is added for 19 October 2026 at 09:30, summary "Failure sample". The page calls the delivery API with the test-only outcome `retryable`. The response is 2 retryable email rows and 2 in-app deliveries, and `email_provider_confirmed` is false. The failure section then shows "The email attempt failed and can be retried.", Attempts 1, a next retry time, directory address `playwright-recording@example.com`, and record S2-REC-0016. The same section still shows older stopped rows whose directory address was not stored on the first capture attempt.
7. The same test outcome is sent two more times. The third response reports 2 failed and 0 recorded. The script scrolls to an Attempts 3 card in the failure section and clicks Retry delivery on that card. A narrow frame shows the notice "The same reminder was queued again. A new reminder was not created." together with unread Follow-up assigned and Follow-up due cards for S2-REC-0016.
8. The viewport is set to 390×720 inside the 1280×720 video, so the page sits on the left of the frame. The script logs `NARROW_OVERFLOW false`. The deliver button and the reminder cards stack. The viewport is then restored to 1280×720.
9. Sign out returns to the sign-in form. `playwright-member@example.com` is entered. The password stays masked. Bootstrap recording 1792111368748 is opened. The sidebar says "Reminders is not available for this sign-in." The script then opens the direct Reminders address, waits until "You do not have permission to perform this action." is shown, and checks that "Morning reminder" and "Failure sample" are absent. The last sampled frame is the "Checking access" card during that navigation, so the permission sentence is brief.

## What the recording does not show

It does not show an empty reminder inbox. It does not show a live mailbox accepting a message. The email result on screen is the test adapter, and the page says the messages were not delivered.

It does not show record reassignment. Follow-up owner assignment is the assignment this sprint can persist. Original roadmap Sprint 6 remains unstarted.

A second CRM user with module access, reading only their own inbox, is covered by `backend/tests/test_reminders.py`, not by this recording. `playwright-member@example.com` does not have CRM module access.
