# BrachyD2ccEval Project - TODO

This file outlines the current tasks and future development steps for the BrachyD2ccEval project.

## Current Focus:
- Discuss the overall project plan with the user.

## Project Goals:
- Automate and streamline the evaluation process for HDR brachytherapy plans (Oncentra).
- Input: DICOM RT Dose and RT Structure Set files.
- Output: BED/EQD2 calculations, EBRT integration, constraint evaluation, and a clear report (similar to current 'dose summary' spreadsheet).

## Key Libraries:
- `pydicom`
- `pandas`
- `numpy`
- `openpyxl`

## Configuration:
- `config.py` for alpha/beta ratios and EMBRACE II constraints.

## Next Steps:
- Identify specific features to implement first.
- Outline the development process (e.g., data parsing, calculation logic, reporting).
- Implement data parsing for DICOM RT Dose and RT Structure Set files.
- Develop calculation logic for BED/EQD2.
- Integrate EBRT calculations.
- Implement constraint evaluation.
- Generate reports in a user-friendly format.