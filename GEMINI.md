# Project Notes for Gemini

This file is for internal use by the Gemini CLI agent to track project progress, plans, and relevant information.

## System Information
- **Operating System:** Windows

## Current Task:
- Debug and fix PDF generator path issues.

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
- **Architectural Refactoring (Backend Separation):**
    - Initiated architectural refactoring to separate core backend logic from the user interface.
    - Created the new `backend/` directory structure: `backend/src/api`, `backend/src/core`, `backend/src/services`.
    - Moved `src/calculations.py` to `backend/src/core/calculations.py`.
    - Moved `src/validators.py` to `backend/src/core/validators.py`.
    - Created placeholder files: `backend/src/main.py`, `backend/src/api/routes.py`, `backend/src/services/parser_service.py`, and `backend/src/services/optimization_service.py`.
- **Committed architectural refactoring:** Successfully transitioned to a client-server architecture with a FastAPI backend and Streamlit frontend. This involved moving core logic, implementing an API layer, creating dedicated services, and updating the frontend to communicate via API requests.

## Next Steps:
- **Fix PDF Generator:** Debug the path issues for `WKHTMLTOPDF` to enable report downloads.
