# CRM-S4 membership closure explanation

Recording: `docs/sprints/crm-s4/recording.webm` (31.16 seconds, 1280×720).

This narration follows that recording. The page is the CRM shell at `http://localhost:5174`, using the running Control Plane and the running CRM API. Passwords stay masked. No session cookie is shown.

## Sequence

1. `playwright-recording@example.com` is signed in. Organizations lists Bootstrap recording 1792111368748.
2. That organization opens. The page says CRM is available. Leads and Projects are shown.
3. Projects opens Recording gate. The edit form shows the name Recording gate. Members then shows one person: `playwright-recording@example.com`, role Project manager, status Active, record scope "All project records."
4. There is no Add member control. The page says "You cannot look up organization members with this sign-in."
5. Remove is clicked. The page adds "This project needs an active project manager." The same member stays Active, still a project manager.
6. An unknown project address in the same organization shows the heading Project and "The requested resource was not found." Recording gate is not shown.
7. An address for a different tenant shows "The requested resource was not found." The organization shell and the project name are not shown. The signed-in address is still `playwright-recording@example.com`.
8. Sign out returns to the empty sign-in form.
9. `playwright-member@example.com` signs in. The password field is masked.
10. The same organization opens. CRM is available. Leads is not available. Projects is not available. Opening the Recording gate address directly adds "You do not have permission to perform this action." The project name is not shown.

## What was not done on screen

No second member was added, no role was changed, and no member was removed. The directory message is the live failure. The automated tests, not this recording, cover a successful add, role change, and removal.
