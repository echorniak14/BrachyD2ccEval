# Project Notes for Gemini

This file is for internal use by the Gemini CLI agent to track project progress, plans, and relevant information.

## System Information
- **Operating System:** Windows

## Current Task:
- Verify D2cc calculations and continue with Phase 2: BED/EQD2 calculations.

## Project Context:
- **Goal:** Automate and streamline the evaluation process for HDR brachytherapy plans, specifically for cases planned using Oncentra.
- **Input:** DICOM RT Dose and RT Structure Set files.
- **Output:** BED/EQD2 calculations, EBRT integration, constraint evaluation, and a clear report similar to the current 'dose summary' spreadsheet.
- **Key Libraries:** `pydicom`, `pandas`, `numpy`, `openpyxl`, `scikit-image`.
- **Configuration:** `config.py` for alpha/beta ratios and EMBRACE II constraints.

## Next Steps:
- Discuss the overall project plan with the user.
- Identify specific features to implement first.
- Outline the development process (e.g., data parsing, calculation logic, reporting).