# CRM-UI-S1 explanation script — workspace and form builder

Recording: `docs/sprints/crm-ui-s1/recording.webm` (36.12 seconds, 1280×720). The file is a WebM of the running CRM at `http://localhost:5174`. Sign-in uses the existing local identity `playwright-recording@example.com`. The password stays masked. No session cookie is shown.

The organization is Bootstrap recording 1792111368748. The project is Recording gate. The form is the existing Enquiry draft. The recording changes the Priority field help text to `UI check note`, saves it, and then restores the previous help text. It does not create a project, archive a project, publish a form, or leave that help text changed.

## Sequence

1. The shell opens on the sign-in form.
2. Sign-in opens Organizations.
3. The organization link Bootstrap recording 1792111368748 is opened.
4. The workspace shows the left navigation, the organization name in the top bar, the signed-in address, Sign out, and the message that CRM is available.
5. Collapse sidebar hides the navigation labels and leaves the icons. Expand sidebar is then used.
6. Projects opens. The page title is Projects, with search, a status filter, and New project.
7. Search for `gate` shows Recording gate.
8. Search for `missing-ui-s1` shows "No projects match this search." The search is then cleared.
9. New project is opened and Create project is used with empty fields. The page shows "Project code is required." No project is created. Back to projects returns to the list.
10. Recording gate is opened.
11. Forms is opened and Recording gate is selected. Enquiry draft is opened.
12. The form builder shows the field palette, the form canvas, and the field properties. Enquiry draft is still a draft, and no version has been published.
13. Email in the palette selects the Email field type on the add-field form.
14. Edit Priority opens that field in the properties panel. The help text is changed to `UI check note` and Save field is used. The canvas shows the new help text and "Field saved."
15. The previous help text is saved back, and `UI check note` leaves the canvas.
16. The viewport is narrowed to 390 pixels. Open navigation is available, and the field palette stacks under the form details.
17. The viewport returns to 1280 pixels and Overview opens. CRM is still available in this organization.
18. One Tab from that page moves keyboard focus to the Leads link.

## What the recording does not show

It does not publish a version, preview a form, or save a CRM record. It does not grant a permission or change a membership. File upload and auto-number generation are not exercised. A second sign-in without project access is not shown; the existing frontend tests cover that denial. Archive stays a single action and is not clicked in this recording.
