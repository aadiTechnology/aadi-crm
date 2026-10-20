# CRM-S5 explanation script — form definitions and fields

Recording: `docs/sprints/crm-s5/recording.webm` (47 seconds, 1280×720).

This narration follows that recording. The page is the CRM shell at `http://localhost:5174`. The organization and sign-in come from the running Control Plane. The CRM API is the running Aadi CRM process. The password stays masked. No session cookie is shown.

The signed-in address is the existing local test identity `playwright-recording@example.com`. It is a project manager on Recording gate. This recording does not change users, roles, permissions, or project memberships.

## What the recording is checking

Original Sprint 3 stores a draft form definition and its fields on a project. A project manager can create the form, add a text field and a dropdown, reorder the fields, and see the same order after leaving the form and opening it again. A repeated field identifier is rejected by the API. An unknown project id is not found and does not show a form name.

## Sequence

1. The shell opens on the sign-in form. The email `playwright-recording@example.com` is entered. The password is entered in the masked field.
2. Sign-in opens Organizations. The only organization link is Bootstrap recording 1792111368748.
3. The organization shell says CRM is available. Leads, Projects, and Forms are shown. The signed-in address is shown.
4. Forms lists the projects for this sign-in. The recording opens Recording gate.
5. Recording gate already lists Enquiry draft. That draft was left by an incomplete recording pass in this same session. It is not created again in this recording. New form is available because this sign-in can administer forms on this project.
6. New form is opened. The name Site enquiry and the description Internal enquiry are entered. Create form opens the draft. The status is Draft.
7. A text field is added. The label is School name, the identifier is `school_name`, Required is checked, the section is Contact, the help text is Legal name, and the maximum length is 120.
8. A dropdown is added. The label is Priority, the identifier is `priority`, the section is Qualification, and the options are Hot, Warm, and Cold. The default value is warm. The field is optional.
9. Move Priority up runs. Priority is then first, in section Qualification, and School name is second, in section Contact. Move Priority up is disabled because Priority is already first.
10. The add-field form is used again with the identifier `school_name`. The page shows "Field identifier is already used on this form." The existing School name field remains.
11. Back to forms, then Site enquiry, reloads the definition. The name, the description Internal enquiry, the Draft status, and the field order are still there. Priority is still first.
12. An address for a project id that does not exist shows "The requested resource was not found." The organization shell remains. Site enquiry and Enquiry draft are not shown on that page.

## What the recording does not show

The recording does not publish a form, preview a record form, or save a CRM record. It does not change a membership or grant a permission. File upload and auto-number are definition types in the API and are not exercised on screen. The automated tests, not this recording, cover a project member being refused form administration, another project, and another tenant. Those tests use an in-process platform double and a temporary database.

## Result

`playwright-recording@example.com` creates Site enquiry on Recording gate, stores a required text field and an optional dropdown, reorders them, and sees that order after reload. A duplicate identifier is rejected. An unknown project is not found.
