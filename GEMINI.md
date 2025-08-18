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
- **Report Layout Reorganization:**
            - Restructured the HTML report to display D0.1cc, D1cc, and D2cc as separate rows under each organ, improving readability and data presentation.
    - Corrected the column header from "Value (per fraction) (Gy)" to "Dose (per fraction) (Gy)" and from "D2cc (total) (Gy)" to "Total Planned Dose (Gy)" in the HTML report.
    - Aligned "Total Planned Dose (Gy)" and subsequent columns with the D2cc row in the HTML report.
- **Robust Plan Name Extraction:**
    - Modified `src/dicom_parser.py` to ensure the extracted plan name is never an empty string, defaulting to 'N/A' if DICOM tags `RTPlanLabel`, `RTPlanName`, or `SeriesDescription` are missing or empty. This prevents `IndexError` issues in downstream processing.
- **Streamlit File Uploader Type Restriction:**
    - Modified `src/streamlit_gui.py` to restrict the `st.file_uploader` to accept only `.dcm` or `.DCM` file types, removing the empty string from the `type` parameter. This prevents `IndexError` issues caused by uploading files without extensions.
- **`NameError: current_constraints` Fix:**
    - Resolved `NameError: name 'current_constraints' is not defined` in `src/main.py` by importing `constraints` from `src/config.py` and initializing `current_constraints` with these default values.

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
