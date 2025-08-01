# BrachyD2ccEval: Automated Brachytherapy Dose Evaluation

This project automates the evaluation of HDR brachytherapy plans, providing quick and accurate dose metrics from DICOM files.

## Current Status

The project is currently in **Phase 2 of development**. The core functionality of parsing DICOM files and calculating D2cc values is complete and verified. The next steps involve implementing BED/EQD2 calculations and integrating configurable constraints.

## Features

- **DICOM Parsing:** Reads RTDOSE, RTSTRUCT, and RTPLAN files.
- **Patient Verification:** Ensures data consistency across all files.
- **D2cc Calculation:** Automatically calculates the D2cc (per fraction and total) for all contoured organs at risk with accurate affine transformations.

## Getting Started

1.  **Installation:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Usage:**
    Place your DICOM files in the project directory and run:
    ```bash
    python dicom_parser.py
    ```

## Calculation Workflow

Here is a step-by-step breakdown of how the D2cc is calculated from the raw DICOM data:

1.  **DICOM File Identification:**
    - The script first identifies the RTDOSE, RTPLAN, and RTSTRUCT files by reading the `Modality` tag in each file.
    - It also performs a crucial safety check by verifying that the `PatientID` is the same across all files.

2.  **Coordinate System Mapping (with Affine Transformation):**
    - The foundation of the calculation is the 3D dose grid from the RTDOSE file. This grid has its own coordinate system.
    - The organ contours from the RTSTRUCT file are defined in a separate patient-based coordinate system.
    - To accurately align these, the script extracts the following tags from the RTDOSE file:
        - `ImagePositionPatient`: The x, y, z coordinates of the top-left corner of the dose grid.
        - `PixelSpacing`: The distance between the centers of adjacent voxels in the x and y directions.
        - `GridFrameOffsetVector`: The z-coordinate for each 2D slice of the dose grid.
        - `ImageOrientationPatient`: The direction cosines of the first row and first column of the image, crucial for handling rotations.

3.  **Contour Transformation:**
    - The script iterates through each organ's contour data from the RTSTRUCT file.
    - For each contour, it performs a full affine transformation using the `ImagePositionPatient`, `PixelSpacing`, and `ImageOrientationPatient` to accurately map the contour points from the patient coordinate system to the dose grid's voxel-based coordinate system.

4.  **3D Organ Mask Creation:**
    - A 3D boolean array (a "mask") is created with the same dimensions as the dose grid.
    - For each transformed contour, the script determines the corresponding 2D slice in the dose grid by finding the closest z-value in the `GridFrameOffsetVector`.
    - The `scikit-image` library is then used to "draw" and fill the 2D contour on that slice of the 3D mask. This effectively turns the 2D organ outlines into a solid 3D representation of the organ within the dose grid.

5.  **Dose-Volume Histogram (DVH) Calculation:**
    - The volume of a single voxel is calculated using the `PixelSpacing` and the slice thickness (derived from the `GridFrameOffsetVector`).
    - The 3D organ mask is used to select all the dose voxels from the RTDOSE grid that fall inside the organ.
    - The raw dose values are multiplied by the `DoseGridScaling` factor to convert them to Gray (Gy).

6.  **D2cc Calculation:**
    - The volume of a single voxel is used to determine how many of the organ's voxels make up 2cc.
    - The dose values for all voxels within the organ are sorted in descending order.
    - The D2cc is the dose value of the Nth voxel in the sorted list, where N corresponds to a volume of 2cc. This gives a precise value without the need for histogram binning.
    - Both per-fraction and total D2cc (multiplied by the number of fractions from the RTPLAN) are reported.


## Additional Scripts

- **`extract_dwell_times.py`**: A utility script to extract and display the dwell times from a DICOM RT Plan file. This script calculates dwell times by interpreting the `CumulativeTimeWeight` and `ChannelTotalTime` tags within the DICOM RT Plan, providing a crucial verification step for brachytherapy plans.

## Temporary and Debugging Scripts

This folder (`temp_scripts`) contains scripts used for debugging, testing, and verifying DICOM parsing and calculations during development. They are not part of the main application workflow but are kept for reference and further testing.

- **`calculate_contour_volumes.py`**: This script calculates the volumes of contoured structures (ROIs) from a DICOM RT Structure Set file. It uses the Shoelace formula for accurate 2D area calculation of each contour slice and then applies a trapezoidal rule-based method to sum these areas across slices, accounting for varying Z-coordinates and disjointed contours. This script was instrumental in verifying the accuracy of our DICOM parsing for geometric data.
