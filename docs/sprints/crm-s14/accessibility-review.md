# Accessibility review — original roadmap Sprint 12

Date: 21 October 2026. An automated axe scan was not run. The review used the existing component tests, one new keyboard test, a calculated contrast check, and a browser check of the menu button.

## What was checked

Sign-in errors, the shell navigation, project and form screens as implemented, records, follow-ups, reminders, import, KPIs, and audit. The screens already use `h1`/`h2`, table captions or `aria-labelledby` on the main tables, `role="alert"` and `role="status"`, and visible focus outlines. Form controls in the journeys that were read have a label or `aria-label`. Error text is not conveyed by color alone: the alert includes a sentence.

## Contrast

Calculated ratios, not a browser contrast probe of every state:

| Pair | Ratio | AA normal text 4.5:1 |
|---|---|---|
| `#64748b` on `#f8fafc` | 4.55 | Pass, small margin |
| `#64748b` on `#ffffff` | 4.76 | Pass |
| `#ffffff` on `#2563eb` | 5.17 | Pass |
| `#b45309` on `#fffbeb` | 4.84 | Pass |
| `#b91c1c` on `#fef2f2` | 5.91 | Pass |
| `#15803d` on `#f0fdf4` | 4.79 | Pass |

Zoom and text scaling were not exercised in a browser.

## Fix

The mobile menu button is named "Open navigation" / "Close navigation" and uses `aria-expanded` and `aria-controls`. It did not respond to Escape. It now closes and moves focus back to that button.

Evidence: `frontend/tests/shell.test.tsx` ("closes the navigation with Escape and returns focus to the menu button"). In the browser, on a 390×844 viewport, the same button's `aria-expanded` was `false` after Escape. The log line is `ESCAPE expanded=false`.

## Deferred

| Severity | Item | Reason |
|---|---|---|
| Medium | The open mobile menu has no focus trap and no backdrop. Content behind it can still be reached | See the later decision below. The control is not a modal dialog |
| Low | Full keyboard tour of the form builder, import mapping, and record editor was not repeated by hand in this review | Existing tests cover labels and validation text. They are not a substitute for a complete keyboard pass |
| Moderate | CSS zoom 200% on the form builder overflows the page | Measured later. Not fixed |

## Later pass: axe, keyboard, and zoom

Date: 21 October 2026. Tool: axe-core 4.10.3 injected into headless Chrome through Playwright. Tags: `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`. The page was the already running app on port 5174. This is not a WCAG conformance claim.

| Screen | When axe ran | Violations |
|---|---|---|
| Projects, records chooser, KPIs chooser, imports, reminders | After the loading status cleared, 1280×720 | none |
| Audit | After the denial was visible | none |
| Recording gate record list, 12 rows | After the table rendered | none |
| Preschool form builder, palette and properties open | After those panes rendered | none |
| Project KPI detail | While "Loading project KPIs" was still present | none |

An axe result of none does not prove the loading KPI detail, the import wizard, or a dialog.

Keyboard, 390×844, projects route:

- Open navigation was activated.
- The next Tab moved focus to "Sign out", which is outside `#workspace-nav`.
- Escape set `aria-expanded` to `false` and returned focus to "Open navigation".

The sidebar is an `<aside>` controlled with `aria-expanded` and `aria-controls`. It has no dialog role, no `aria-modal`, and no backdrop. On a narrow viewport it is `position: fixed` and covers part of the page, but the rest of the page stays in the tab order. A focus trap was not added. A trap would present a non-modal disclosure as a dialog and would block the Sign out control that remains reachable. The residual gap is that a keyboard user can tab into content the drawer covers.

CSS zoom 200% at 1280×720 kept the 12-row record list inside the page. The form builder overflowed by 243 pixels. See `responsive-validation.md`. Zoom was not tested at 400% or at a 320px CSS width.
