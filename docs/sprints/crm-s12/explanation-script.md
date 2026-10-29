# CRM-S12 explanation script — original roadmap Sprint 10

Recording: `docs/sprints/crm-s12/recording.webm` (6,704,731 bytes, VP9, 1280×720, 107.76 seconds).

This narration follows that recording and the capture log from `node docs/sprints/crm-s12/record-demo.mjs`, which exited 0. The page is the CRM shell at `http://localhost:5174`. The signed-in address is `playwright-recording@example.com`. The organization is Bootstrap recording 1792111368748. The password stays masked.

`docs/sprints/crm-s12` is the evidence folder for original roadmap Sprint 10. It is not original roadmap Sprint 12.

Frames were sampled with ffmpeg. This was not continuous playback.

The recording does not upload `CRM.xlsx`. That workbook contains personal and customer details. The import file is `synthetic-preschool.csv`: Example North, Example South, and Example West. The real workbook was reconciled in `reconciliation-report.md` on a disposable database.

## Sequence

1. Sign-in opens Bootstrap recording. At about 12 seconds and again at about 44 seconds the Overview says CRM is available. During that time the script creates three projects through the form API and publishes Preschool, Space View, and Hiring as version 1. Paneerwala is not in the catalog, so no Paneerwala form is created. The capture log prints `PUBLISHED` for the three forms with stamp `886025`.
2. The script opens each form and waits for the form heading and `Render version 1`, then scrolls the first and last field. A sampled frame at about 76 seconds shows `Loading form`. The field list itself is not in the sampled frames. The script would have stopped before the import if those waits had failed.
3. At about 82 seconds Import is open for Preschool, `notes.txt` is selected, and the button says `Uploading file`. The script then waits for `Upload a .csv or .xlsx file.` That sentence is not in the sampled frame.
4. The synthetic CSV is uploaded. At about 92 seconds the mapping table shows Discussion Summary, Followup Comments 1, and Followup Comments 2 mapped to the same labels. The preview shows:
   - Row 2, Example North, mobile `919800000099`, email `ada@example.com`, selling point `=Example note`, with a possible mobile match inside the file and Decision set to Accept as new.
   - Row 3, `Inquiry Date must use YYYY-MM-DD` and `Email must be an email address`.
   - Row 4, Example West, the same mobile, and a possible match inside the file.
5. The script sets row 4 to Skip and imports. It waits for `Partially completed. Accepted 1, rejected 1, skipped 1, awaiting review 0. Input rows 3, not counting the header.` That sentence is not in the sampled frames. The downloaded error report contains the date message and `Skipped during duplicate review.` The script logs both as true.
6. Repeat this import runs on the same job. The script waits for the same accepted, rejected, and skipped counts.
7. The record list is opened. A sampled frame at about 98 seconds is still loading. The script waits for `Records (1)` and opens the record ending in `-0001`. A frame at about 104 seconds is the record page still loading. The script then waits until Example North is visible and Example West is not.
8. The viewport is set to 390×720. The script logs `NARROW_OVERFLOW false`. That layout is not in the sampled frames.
9. At about 106 seconds the sign-in form shows `playwright-member@example.com` and a masked password. The script then waits for `Import is not available for this sign-in.` and, on the Preschool import address, `You do not have permission to perform this action.` It also checks that Example North is absent. Those sentences are not in the sampled frames. The log reaches `STEP done` only after those waits.

## What the recording does not show

It does not show the source workbook, Paneerwala, or the disposable-database reconciliation. Those are in the mapping and reconciliation documents.

It does not, in the sampled frames, show the published field lists, the partial-completion sentence, the opened record's values, the narrow layout, or the member-denial sentence. The capture log covers those waits.
