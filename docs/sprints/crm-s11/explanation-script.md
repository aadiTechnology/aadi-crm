# CRM-S11 explanation script — original roadmap Sprint 9

Recording: `docs/sprints/crm-s11/recording.webm` (8,660,995 bytes, VP9, 1280×720, 102.44 seconds).

This narration follows that recording and the capture log from `node docs/sprints/crm-s11/record-demo.mjs`, which exited 0. The page is the CRM shell at `http://localhost:5174`. The CRM API is the running process on port 8001. The password stays masked.

The signed-in address for the import is `playwright-recording@example.com`. The second address is `playwright-member@example.com`. The organization is Bootstrap recording 1792111368748.

`docs/sprints/crm-s11` is the evidence folder for original roadmap Sprint 9. It is not original roadmap Sprint 11.

Frames were sampled with ffmpeg. This was not continuous playback. Times below are offsets in that file.

## What the recording is checking

The manager creates project Import gate IMP486934, publishes form Import capture, saves one existing record, rejects a non-workbook upload, maps a three-row CSV, previews it, skips the duplicate, imports the valid row, repeats that import, exports the `=Fresh` search, checks a 390-pixel viewport, and signs in as an account that cannot open Import.

## Sequence

1. Sign-in opens the organization. At about 8 seconds the Forms list is loading for `playwright-recording@example.com`.
2. At about 22 seconds the form builder is saving a field. The script creates School name as a required text field and Email as an optional email field, then publishes version 1.
3. At about 36 seconds the record list for the new project is loading. At about 48 seconds New record shows Import capture · version 1, School name "Existing lane", and Email `demo.import@example.com`, with the button reading "Saving record". The script logs `SEEDED IMP486934-0001`.
4. Import opens. At about 62 seconds the page says "Loading import". The script uploads `notes.txt` and logs the alert "Upload a .csv or .xlsx file." That alert is not in the sampled frames.
5. At about 68 seconds the published form is Import capture and the selected file is `leads.csv`, with "Uploading file" on the button. At about 70 seconds the mapping is School name to School name (required), Email to Email, and Notes to Unmapped. At about 72 seconds the page says "Unmapped columns kept on this import: Notes."
6. At about 74 seconds the dry-run banner reads: "Dry-run only. No CRM records were created. Ready 1, rejected 1, skipped 0, awaiting review 1. Input rows 3, not counting the header."
7. At about 78 seconds the preview table shows row 2, `=Existing lane` and `demo.import@example.com`, with "Possible match on Email with IMP486934-0001" and Decision for row 2 set to Skip. Row 3 shows "School name is required." and "Email must be an email address." Row 4 is `=Fresh lane` and `fresh.import@example.com`. Notes stays unmapped on each row.
8. At about 80 seconds, after Import records, row 2 is skipped and row 4 is accepted. Row 3 still shows the two field errors. The script waits for "Partially completed. Accepted 1, rejected 1, skipped 1, awaiting review 0. Input rows 3, not counting the header." That sentence sits above the sampled view. The script downloads the error report and logs `row_number,field,message` with the skip, the possible email match, the required school name, and the invalid email. The file contents are not opened on screen.
9. Repeat this import runs before the page leaves Import. The script waits for the same accepted, rejected, and skipped counts. A second banner is not in the sampled frames. The database afterwards has one imported record, IMP486934-0002, not a second copy.
10. At about 98 seconds the record list for Import gate IMP486934 is filtered by `=Fresh`. The heading is Records (1). The row is IMP486934-0002, source Import, name `=Fresh lane`. The status line visible in that frame is "Preparing the export". The script then waits for "Exported 1 data rows. The list reports 1 matching records." and logs that the CSV contains `'=Fresh lane` and does not contain "Existing lane". That finished sentence is not in a sampled frame.
11. At about 99 seconds the viewport is 390×720 inside the 1280×720 video, so the record filters sit on the left and the rest of the frame is empty. The search still shows `=Fresh`. The script logs `NARROW_OVERFLOW false`.
12. At about 100 seconds the sign-in form shows `playwright-member@example.com` and a masked password. At about 102 seconds the page says "Checking access". The script then waits for "Import is not available for this sign-in." and, on the direct Import address, "You do not have permission to perform this action." It also checks that `=Fresh lane` and `demo.import@example.com` are absent. Those two sentences are not in the sampled frames. The video ends on "Checking access".

## What the recording does not show

It does not show an XLSX file being chosen. CSV and XLSX parsing are both in `backend/tests/test_imports.py`.

It does not show the error-report file open on screen, the partial-completion sentence, or the finished export-count sentence. The row outcomes, the Records (1) result, and the capture log cover those checks.

It does not show the member denial sentence. The last sampled frame is "Checking access".

It does not show a cross-tenant import job. That check is in the API tests.
