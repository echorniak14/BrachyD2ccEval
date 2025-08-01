# BrachyD2ccEval Project - TODO

This file outlines the current tasks and future development steps for the BrachyD2ccEval project.

**Last Updated: 2025-07-31**

## Current Focus:
- **Proceed with Phase 2: BED/EQD2 calculations.**

## Progress Update:
- **Phase 1: Core Functionality - COMPLETED**
    - [x] DICOM Data Parsing: Successfully parsed RTDOSE, RTSTRUCT, and RTPLAN files.
    - [x] Patient Verification: Implemented checks to ensure all files belong to the same patient.
    - [x] D2cc Calculation: Implemented the core logic to calculate organ volumes and D2cc values.
    - [x] Corrected D2cc Calculation: Implemented full affine transformation for accurate contour mapping and calculated total D2cc over all fractions.
    - [x] Verified D2cc Calculation: Successfully verified dwell time extraction and contour volume calculations against ground truth data.

## Next Steps (Phase 2):
- [ ] Implement BED/EQD2 calculations.
- [ ] Create `config.py` for alpha/beta ratios.
- [ ] Integrate EBRT calculations.
- [ ] Implement constraint evaluation based on EMBRACE II.
- [ ] Generate reports in a user-friendly format (Excel).
