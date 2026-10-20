# CRM-S6 acceptance explanation — form versioning after the workspace redesign

Recording: `docs/sprints/crm-s6/recording-acceptance.webm` (42.32 seconds, 1280×720, 3,344,340 bytes). `ffprobe` reported the duration and size.

This narration follows that recording. The capturing script logged every step and exited 0. The page is the CRM shell at `http://localhost:5174`. Sign-in uses the running Control Plane. Form reads and publishes use the running CRM API. Passwords stay masked. No session cookie is shown.

The first address is `playwright-recording@example.com`, a project manager on Recording gate. The second is `playwright-member@example.com`. That identity does not have CRM forms access. The recording does not change users, roles, permissions, or memberships.

The form created in this recording is Closure gate on Recording gate. The description is Internal closure gate.

## Sequence

1. The shell opens on the sign-in form. `playwright-recording@example.com` is entered. The password is entered in the masked field. Sign-in opens Organizations.
2. Bootstrap recording 1792111368748 is opened. The page says CRM is available in this organization.
3. Forms is opened, then Recording gate. The heading is Recording gate forms.
4. New form is opened. The name Closure gate and the description Internal closure gate are entered. Create form opens the draft. The page says "No published version yet."
5. A required text field is added. The label is School name, the identifier is `school_name`, and the section is Contact. The page says "Field saved."
6. Preview draft opens. The page says "Draft preview. Required fields are marked. Nothing is saved." Check preview shows "School name is required."
7. School name is filled with North school. Check preview shows "No CRM record was saved."
8. Back to form. The page still says "No published version yet."
9. Publish version opens Review publication. The review says publishing creates an immutable version and that later draft edits do not change a published version. Cancel publish closes the review. The page still says "No published version yet."
10. Publish version is used again, then Confirm publish. The page shows Render version 1, "Current published version 1", and "Version published."
11. Render version 1 opens. The page says "Published version 1. This schema stays as it was published." The School name field is present.
12. Back to form. Edit School name changes the label to Campus. Save field stores that draft change. The page says "Field saved."
13. Publish version, then Confirm publish. The page shows Render version 2 and "Current published version 2".
14. Render version 1 opens again. School name is present. The Campus label is not present. The page still says the published version 1 schema stays as it was published.
15. Sign out shows the sign-in form. The address can still be the organization path. That is how this shell returns to sign-in.
16. `playwright-member@example.com` signs in. The shell opens the same organization from that address. The page says "Forms is not available for this sign-in."
17. The Closure gate address is opened directly. The page shows "You do not have permission to perform this action." Publish version is not shown.

## What the recording does not show

It does not show an active project member rendering a published version. The development database has no active project member. That path is in `backend/tests/test_form_versions.py` and `frontend/tests/form-versions.test.tsx`.

It does not click Replace draft with published version. It does not create a CRM record, upload a file, or generate an auto-number.

Earlier capture attempts in this same pass also left Closure check, Closure review, and Closure evidence on Recording gate. Those rows are not what this recording creates. This recording creates Closure gate.
