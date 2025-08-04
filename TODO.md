# BrachyD2ccEval Project - TODO

This file outlines the current tasks and future development steps for the BrachyD2ccEval project.

**Last Updated: 2025-08-04**

## Current Focus:
- **Implement logic to incorporate previous brachytherapy data.**

## Progress Update:
- **Phase 1: Core Functionality - COMPLETED**
    - [x] DICOM Data Parsing: Successfully parsed RTDOSE, RTSTRUCT, and RTPLAN files.
    - [x] Patient Verification: Implemented checks to ensure all files belong to the same patient.
    - [x] D2cc Calculation: Implemented the core logic to calculate organ volumes and D2cc values.
    - [x] Corrected D2cc Calculation: Implemented full affine transformation for accurate contour mapping and calculated total D2cc over all fractions.
    - [x] Verified D2cc Calculation: Successfully verified dwell time extraction and contour volume calculations against ground truth data.
- **Phase 2: Visual Interpretation of Results - IN PROGRESS**
    - [x] Implement BED/EQD2 calculations.
    - [x] Create `config.py` for alpha/beta ratios.
    - [x] Integrate EBRT calculations.
    - [x] Resolved file path handling issues.
    - [x] Integrated `dicompyler-core` for D2cc calculations.
    - [x] Implemented constraint evaluation based on EMBRACE II.
    - [x] Generated initial report in Excel format.
    - [x] Simplified EBRT input in `gui.py`.
    - [x] Made `main.py` return structured data (JSON).
    - [x] Enhanced GUI (`gui.py`) to parse structured data and display it with visual (red/green) constraint indicators.
    - [x] Fixed JSON serialization error in `main.py` (corrected approach).
    - [x] Refined GUI display: Removed BED constraint column and added organ names.
    - [x] Integrated HTML report generation and automatic opening in `gui.py`.
    - [x] Refined report generation: Provided an option to print to PDF from the HTML report.
    - [x] Enhanced report content: Extracted patient MRN and brachytherapy prescription details from DICOM and included in HTML report.

## Next Steps (Phase 2):
- [ ] Add functionality to calculate the highest fractional dose needed to meet any unmet constraints.
- [ ] Further investigate and resolve any remaining discrepancies in D2cc/BED/EQD2 calculations if necessary.

## Phase 3: BED/EQD2 calculations incorporating previous brachy doses
- [ ] Implement logic to incorporate previous brachytherapy data (either from DICOM files or provided EQD2 reports).