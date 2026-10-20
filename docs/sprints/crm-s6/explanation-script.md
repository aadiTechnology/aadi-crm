# CRM-S6 explanation script — form versioning, preview, and internal renderer

Recording: `docs/sprints/crm-s6/recording.webm` (2,737,483 bytes, 1280×720). Duration was not measured with a media probe.

This narration follows that recording. The capturing script logged each step below and exited successfully. The page is the CRM shell at `http://localhost:5174`. The organization and sign-in come from the running Control Plane. The CRM API is the running Aadi CRM process. The password stays masked. No session cookie is shown.

The first signed-in address is the existing local test identity `playwright-recording@example.com`. It is a project manager on Recording gate. The second address is `playwright-member@example.com`. That identity does not have CRM forms access. This recording does not change users, roles, permissions, or project memberships.

## What the recording is checking

Original Sprint 4 lets a project manager preview a draft, publish it as version 1, change the draft, publish version 2, and open version 1 again with the original schema. Preview does not save a CRM record. A sign-in without CRM forms access cannot open Forms and cannot publish.

## Sequence

1. The shell opens on the sign-in form. The email `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations.
2. Bootstrap recording 1792111368748 is opened. The organization shell says CRM is available.
3. Forms is opened, then Recording gate. The heading is Recording gate forms.
4. New form is opened. The name Version check and the description Internal version check are entered. Create form opens the draft. The page says "No published version yet."
5. A required text field is added. The label is School name, the identifier is `school_name`, and the section is Contact.
6. A dropdown is added. The label is Priority, the identifier is `priority`, the section is Qualification, and the options are Hot, Warm, and Cold.
7. Preview draft opens. The page says "Draft preview. Required fields are marked. Nothing is saved." Check preview shows "School name is required."
8. School name is filled with North school. Check preview shows "Preview checked these fields. No CRM record was saved."
9. Back to form, then Publish version. The page shows Render version 1 and "Current published version 1".
10. Edit School name changes the label to Campus. Save field stores that draft change.
11. Publish version runs again. The page shows Render version 2 and "Current published version 2".
12. Render version 1 opens. The page says "Published version 1. This schema stays as it was published." The School name field is present. The Campus label is not present.
13. Sign out returns to the email field.
14. `playwright-member@example.com` signs in and opens the same organization. The page says "Forms is not available for this sign-in."
15. The existing Site enquiry form address is opened directly. The page shows "You do not have permission to perform this action." Publish version is not shown.

## What the recording does not show

The recording does not show an active project member rendering a published version. The development database has no active project member, and the second sign-in does not have the CRM module permission. Member rendering, a removed member, another project, and another tenant are covered by the automated tests.

The recording does not click Replace draft with published version. That action is covered by the API test. It does not create a CRM record, upload a file, or generate an auto-number.

Site enquiry was already on Recording gate before this recording, including versions left by an earlier incomplete browser pass in the same session. This recording creates Version check and uses Site enquiry only for the unauthorized address at the end.

## Result

`playwright-recording@example.com` previews Version check, publishes version 1, changes the draft label to Campus, publishes version 2, and still sees School name on version 1. `playwright-member@example.com` cannot open Forms and is denied on the Site enquiry address.
