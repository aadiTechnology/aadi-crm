# CRM-S3 project membership explanation

Recording: `docs/sprints/crm-s3/recording.webm` (32.64 seconds, 1280×720).

This narration follows that recording in order. The page is the CRM shell at `http://localhost:5174`. The CRM API is the local Aadi CRM process. The organization and sign-in come from the local Control Plane. The first signed-in address is the existing local test identity `playwright-recording@example.com`. The second is the existing local test identity `playwright-member@example.com`. Both password fields stay masked. No session cookie or password is shown.

## Purpose

The recording checks project membership against the running Control Plane and the CRM API. The first identity has CRM product access and `crm.lead_management.read`. That opens the project module. It does not open every project by itself, and it does not include Control Plane `users.read`, so the page cannot offer other organization members. The second identity is the tenant administrator. CRM is available for the organization, and that sign-in still cannot open Projects.

## Sequence

1. The shell opens on the sign-in form, titled CRM, with Email, Password, and Sign in. The email `playwright-recording@example.com` is entered. The password is entered in the masked field. The characters appear as dots.
2. Sign-in opens the organization Bootstrap recording 1792111368748. The page says "CRM is available in this organization." Leads and Projects are shown. The signed-in address is shown.
3. Projects opens in the same shell. Recording gate is opened from that list.
4. Recording gate shows code S2-REC, status Active, role Project manager, and record scope "All project records." The stored description and the created and updated times are shown.
5. Members shows one row: `playwright-recording@example.com`, role Project manager, status Active, record scope "All project records." The role control, Save role, and Remove are shown because this sign-in is the project manager.
6. Remove is clicked. The page says "This project needs an active project manager." The member stays Active. A second message says "You cannot look up organization members with this sign-in." No other person is offered in an add-member list.
7. An unknown project address inside the same organization replaces the detail with the heading Project and the message "The requested resource was not found." Recording gate is not shown.
8. An address for a different tenant shows the same not-found message. The signed-in address is still `playwright-recording@example.com`. No project name is shown.
9. Sign out returns to the empty sign-in form.
10. `playwright-member@example.com` is entered. The password is entered in the masked field.
11. The same organization opens. CRM is available. The page says "Leads is not available for this sign-in." and "Projects is not available for this sign-in." There is no Projects link.
12. The Recording gate address is opened directly. The project name is not shown. The page still says Projects is not available, and it adds "You do not have permission to perform this action."

## What the recording does not show

The recording does not add a second member or change a role. The CRM test identity cannot look up organization members, because that Control Plane directory requires `users.read` and this sign-in does not have it. The only manager cannot be removed, so the recording does not show a member losing access after removal. Those paths are covered by the automated tests in the implementation report, using an in-process platform double and a temporary database. The browser does not use that double.

## Result

`playwright-recording@example.com` opens Recording gate as its project manager and cannot select another organization member. Removing that only manager is refused, and the project remains. An unknown project id and another tenant id are not found. `playwright-member@example.com` has CRM available in the organization and still cannot open the project.
