# Responsive validation — original roadmap Sprint 12

Date: 21 October 2026. Browser: Playwright Chromium, channel Chrome, headless, against `http://localhost:5174`. The page was already being served. This review did not restart it.

The recording file is 1280×720 because that is the video canvas. When the page viewport is 390×844, the page occupies the left side of that canvas. The gray area in the video is unused canvas, not a second column of the page.

Overflow is `documentElement.scrollWidth - clientWidth` after the `h1` is visible. Zero means no page-level horizontal overflow at that moment. Several sampled frames were still on a loading line, so this does not prove every populated table fits without an inner scroll.

## Measurements

| Viewport | Route | Overflow |
|---|---|---|
| 1280×720 | projects, records, follow-ups, reminders, imports, KPIs, audit | 0 |
| 390×844 | those same seven routes | 0 |
| 768×1024 | records | 0 |
| 390×844 | forms | 0 |
| 390×844 | the first project detail link on the project list | 0 |
| 1280×720 | forms | 0 |

The forms and project-detail measurements were a second headless pass. They are not in `recording.webm`.

## What the recording shows

`docs/sprints/crm-s14/recording.webm` is VP9, 1280×720, 15.16 seconds, 1,295,429 bytes. Sampled frames show the signed-in organization, the narrow import page with "Open navigation", and the narrow records page. "Open navigation" is visible and the text block fits the left column.

## Not claimed

The first pass did not open a populated record table or the form builder. A later headless pass on the same day did. It did not create a new recording. `recording.webm` still does not show those screens.

## Settled routes on 21 October 2026

Browser: Playwright Chromium, channel Chrome, headless, against the already running `http://localhost:5174`. The dev server was not restarted. The sign-in was the existing recording user for organization Bootstrap recording 1792111368748. Overflow is `documentElement.scrollWidth - clientWidth` after the loading status had cleared. Zero is no page-level horizontal overflow.

| Viewport | Route | Overflow | What was on the page |
|---|---|---|---|
| 1280×720, 768×1024, 390×844 | projects, records, follow-ups, reminders, imports, KPIs, forms | 0 | Route heading. These are the chooser pages, not a populated table |
| 1280×720, 768×1024, 390×844 | audit | 0 | Permission denial: "You do not have permission to perform this action." |

## Populated record table and form builder

The recording user's first project link, Harbor gate, had no record table. The pass then opened project `8d0b7f84-d481-45cf-beca-3dd1af92ec97` (heading "Recording gate"), which rendered 12 body rows.

| Viewport | Screen | Page overflow | Table wrap overflow |
|---|---|---|---|
| 390×844 | Recording gate record list | 0 | 48 |
| 768×1024 | Recording gate record list | 0 | 244 |
| 1280×720 | Recording gate record list | 0 | 0 |

The extra width stayed inside `.table-wrap`. The page itself did not scroll sideways. Critical row links remained in the table.

The form builder was opened at `/forms/baea62da-890b-4599-9408-7e665a35cfa3/f334ff57-bb7d-457c-88ee-875aad6c53b0` (heading "Preschool"). The field palette and the field properties pane were both present.

| Viewport | Page overflow |
|---|---|
| 390×844 | 0 |
| 768×1024 | 0 |
| 1280×720 | 0 |

A record-edit dialog was not opened. No data was created or archived.

## Zoom observation

At 1280×720, `documentElement.style.zoom` was set to `2` after the populated screens had rendered. This is CSS zoom in headless Chrome, not the browser zoom menu and not a 320px reflow pass.

| Screen | Page overflow at CSS zoom 200% |
|---|---|
| Recording gate record list, 12 rows | 0 |
| Preschool form builder | 243 on the document and 121 on the body |

The form builder does not fit at that zoom. That finding is not fixed. It is not a WCAG conformance result.
