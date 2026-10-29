# Explanation script — original roadmap Sprint 12

Date: 21 October 2026. This script matches `docs/sprints/crm-s14/recording.webm`.

The recording is VP9, 1280×720, 15.16 seconds, 1,295,429 bytes. It was captured headlessly with Playwright against the CRM page already running at `http://localhost:5174`. No project, form, record, or follow-up was created. The video canvas stays 1280×720. When the viewport is 390×844, the page is the left portion of the frame and the rest of the frame is empty canvas.

## What the recording shows

1. The recording user signs in and opens Bootstrap recording 1792111368748.
2. The desktop viewport visits projects, records, follow-ups, reminders, import, KPIs, and audit. After each `h1` appeared, page overflow was 0.
3. The viewport changes to 390×844 and visits the same seven routes. Overflow stays 0. A sampled frame shows Import with "Open navigation" and "Loading import". Another shows Records with "Open navigation".
4. On the project list at 390 pixels, Escape is pressed. The capture log is `ESCAPE expanded=false`.
5. The viewport changes to 768×1024 on the records route. Overflow is 0.

## Not shown

The recording does not show a completed data table, the form builder, a record editor, a backup, a restore, a metrics dashboard, a load test, or a person executing the UAT script. Forms and project detail were measured in a second pass that was not recorded. Both had overflow 0.
