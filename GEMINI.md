# Project Notes for Gemini

This file is for internal use by the Gemini CLI agent to track project progress, plans, and relevant information.

## System Information
- **Operating System:** Windows

## Current Task:
- Refine user interface and enhance report generation.

## DICOM Parsing Verification:
- **Dwell Time Extraction:**
    - Created a temporary script to extract dwell times from the RT Plan file.
    - Initially, the script failed to find dwell times due to an incorrect assumption about the `BrachyTreatmentTechnique` tag.
    - After correcting the script to handle the 'INTRACAVITARY' technique, it still failed to find the dwell times.
    - Created a script to view all DICOM tags, which revealed that the dwell times were stored in the `CumulativeTimeWeight` tag.
    - After several attempts, the correct formula to calculate the dwell times from the `CumulativeTimeWeight` was determined and verified.
    - The final script, `extract_dwell_times.py`, now correctly calculates and displays the dwell times.
- **Contour Volume Calculation:**
    - Created a temporary script (`calculate_contour_volumes.py`) to calculate volumes from RT Structure Set files.
    - Initial calculations were significantly off, leading to a debugging process.
    - Identified that the initial slice thickness assumption was too simplistic.
    - Discovered that the Sigmoid structure had multiple contours at the same Z-level, indicating disjointed volumes.
    - Implemented a more robust volume calculation method using the Shoelace formula for 2D area and a trapezoidal rule for 3D slab volumes, grouping contours by Z-position.
        - The updated script now accurately calculates volumes for all structures, including complex ones like the Sigmoid, matching the provided ground truth data.
    - Successfully verified calculated volumes against ground truth data from the Excel spreadsheet for Bladder, Bowel, Rectum, and Sigmoid, with minimal discrepancies.
- **Plan Name Extraction:**
    - Improved plan name extraction from RTPLAN files in `src/dicom_parser.py` to correctly identify names like "30mmCylinder" by prioritizing `RTPlanLabel` and `RTPlanName` tags.

## Project Context:
- **Goal:** Automate and streamline the evaluation process for HDR brachytherapy plans, specifically for cases planned using Oncentra.
- **Input:** DICOM RT Dose and RT Structure Set files.
- **Output:** BED/EQD2 calculations, EBRT integration, constraint evaluation, and a clear report similar to the current 'dose summary' spreadsheet.
- **Key Libraries:** `pydicom`, `pandas`, `numpy`, `openpyxl`, `scikit-image`, `dicompyler-core`.
- **Configuration:** `config.py` for alpha/beta ratios and EMBRACE II constraints.

## Progress Update (Current Session):
- **BED/EQD2 Calculations:**
    - Implemented initial BED/EQD2 calculation logic in `calculations.py`.
    - Created `config.py` for alpha/beta ratios.
    - Integrated EBRT dose into BED/EQD2 calculations.
- **File Path Handling:**
    - Identified and resolved issues with handling file paths containing special characters on Windows by refactoring `main.py` to use `pathlib` and accepting data directories as arguments.
- **D2cc Discrepancy Investigation:**
    - Noticed discrepancies between script-calculated BED/EQD2 values and spreadsheet values.
    - Traced discrepancy to differences in D2cc values.
    - Attempted linear interpolation for D2cc, but it did not resolve the issue.
    - Integrated `dicompyler-core` library for DVH and D2cc calculations in `calculations.py` to improve accuracy.
    - Verified that D2cc values are now much closer to spreadsheet values after `dicompyler-core` integration, suggesting the remaining small differences are likely due to rounding or subtle DICOM interpretation variations.
- **Custom Volume Calculation Integration:**
    - Integrated custom volume calculation logic into `src/calculations.py` to align with ground truth from the Excel spreadsheet.
    - Implemented a `try-except` block around `dicompyler-core` DVH calculations to gracefully handle "Dose plane not found" warnings and prevent application crashes.
- **Constraint Evaluation:**
    - Implemented constraint evaluation based on EMBRACE II.
    - Generated initial report in Excel format.

- **Robust Plan Name Extraction:**
    - Modified `src/dicom_parser.py` to ensure the extracted plan name is never an empty string, defaulting to 'N/A' if DICOM tags `RTPlanLabel`, `RTPlanName`, or `SeriesDescription` are missing or empty. This prevents `IndexError` issues in downstream processing.
- **Streamlit File Uploader Type Restriction:**
    - Modified `src/streamlit_gui.py` to restrict the `st.file_uploader` to accept only `.dcm` or `.DCM` file types, removing the empty string from the `type` parameter. This prevents `IndexError` issues caused by uploading files without extensions.
- **`NameError: current_constraints` Fix:**
    - Resolved `NameError: name 'current_constraints' is not defined` in `src/main.py` by importing `constraints` from `src/config.py` and initializing `current_constraints` with these default values.
- **PDF Report Generation:**
    - Integrated `WeasyPrint` library for converting HTML reports to PDF.
    - Added `convert_html_to_pdf` function in `src/main.py` to handle the conversion.
    - Modified `src/main.py`'s `generate_html_report` to return HTML content for PDF conversion.
    - Implemented a "Download PDF" button in `src/streamlit_gui.py` to allow users to download the generated PDF report.
- **Report Layout Reorganization (OAR DVH Results):**
    - Modified the OAR DVH results table in `src/main.py` to align the "Total Planned Dose (Gy)" column with the D2cc row, leaving D0.1cc and D1cc rows empty in that column for improved readability.
- **PDF Report Generation (Error Handling):**
    - Added a `try-except` block in `src/streamlit_gui.py` around PDF generation to catch `IOError` (e.g., if `wkhtmltopdf` is not found) and display a user-friendly error message.
- **Flame Logo Display Fix:**
    - Modified `src/templates/report_template.html` to use a placeholder `{{ logo_base64 }}` for the image source.
    - Modified `src/main.py` to read the `2020-flame-red-01.png` image, Base64 encode it, and embed it directly into the HTML report as a data URI. This ensures the logo displays correctly in the generated PDF and Streamlit report tab, as it eliminates reliance on external file paths.
- **Customizable Constraints in GUI:**
    - Imported `constraints` from `src/config.py` into `src/streamlit_gui.py`.
    - Added a "Constraints" section to the Streamlit sidebar with an expander for editing.
    - Implemented `st.number_input` widgets for EQD2 max values using `st.session_state` for persistence within the session.
    - Removed BED constraint customization as per user request.
    - Added a "Reset Constraints to Default" button.
    - Modified the `main` function in `src/main.py` to accept a `custom_constraints` argument.
    - Updated the `current_constraints` variable in `src/main.py` to use `custom_constraints` if provided, otherwise fall back to the default `constraints` from `config.py`.
- **Enhanced DVH Results Display in Streamlit:**
    - Imported `pandas` into `src/streamlit_gui.py`.
    - Changed `st.table` to `st.dataframe` for DVH results display.
    - Included "Constraint Met" status (Met/NOT Met) and "Dose to Meet Constraint (Gy)" for OARs in the displayed data.
    - Implemented conditional styling (red/green background) for OAR rows in `st.dataframe` based on constraint adherence.
- **Point Dose Results Column Reordering:**
    - Modified `src/main.py` to reorder the columns in the `point_dose_results` dictionary to `name`, `dose`, `total_dose`, `BED_this_plan`, `BED_previous_brachy`, `BED_EBRT`, `EQD2` for consistent display in the Streamlit GUI.
- **Fix KeyError in Point Dose Results:**
    - Corrected key names in `src/main.py` from `bed_this_plan`, `bed_previous_brachy`, and `bed_ebrt` to `BED_this_plan`, `BED_previous_brachy`, and `BED_EBRT` respectively, to match the updated dictionary keys.
- **OAR DVH Results Layout Adjustment:**
    - Modified `src/streamlit_gui.py` to restructure the `oar_dvh_data` to mimic the HTML report layout.
    - Organ and Volume columns now effectively span 3 rows by duplicating values in the first row and leaving subsequent rows empty.
    - D0.1cc, D1cc, and D2cc are stacked in a single "Dose Metric" column.
    - BED and EQD2 values are layered accordingly for each dose metric.
- **JSON Export of Plan Data:**
    - Imported `json` module into `src/streamlit_gui.py`.
    - Added a "Download Brachy Data (JSON)" button to the "Report" tab in Streamlit.
    - This button allows users to export the `dvh_results` and `point_dose_results` of the current plan as a JSON file.

## Next Steps:
- **Previous Brachytherapy Data Integration:**
    - Implemented functionality to incorporate previous brachytherapy EQD2 data from HTML reports, allowing for organ-specific dose accumulation.
- **Dose to Meet Constraint Calculation:**
    - Implemented functionality to calculate the highest fractional dose needed to meet any unmet constraints.
- Further investigate and resolve any remaining discrepancies in D2cc/BED/EQD2 calculations if necessary.
- **Executable Creation:**
    - Successfully packaged the application into a standalone executable using PyInstaller, handling internal module imports and data file paths.

## Git Best Practices:
- **Commit Frequently:** Aim to commit your work after completing each logical unit or phase of development (e.g., after completing DICOM parsing, after implementing a specific calculation, after fixing a bug). This creates clear checkpoints and makes it easier to track progress and revert if necessary.
- **Descriptive Commit Messages:** Write clear and concise commit messages that explain *what* was changed and *why*.
- **Use Branches:** Utilize branches for new features or experimental work to keep your main branch clean and stable.

## Agent Workflow and Documentation:
To ensure transparency and maintain high-quality documentation, the agent will follow these steps:
1.  **Understand Request:** Fully comprehend the user's request and its implications.
2.  **Plan Execution:** Formulate a clear plan of action, breaking down complex tasks into smaller, manageable steps.
3.  **Execute Task:** Perform the necessary coding, file operations, or shell commands.
4.  **Verify (Internal):** Conduct internal checks (e.g., running tests, checking output) to ensure the task was completed correctly.
5.  **Update Documentation:** Before any Git commit, update relevant documentation files (e.g., `README.md`, `TODO.md`, `GEMINI.md`) to reflect the latest changes and progress. This ensures the documentation is always in sync with the codebase.
6.  **Explain Changes:** Clearly explain the changes made and the reasoning behind them to the user.
7.  **Propose Git Commit:** Propose a Git commit, including a descriptive message, and await user approval before committing.