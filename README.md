# BrachyD2ccEval

## Project Overview

This project aims to automate and streamline the evaluation process for HDR brachytherapy plans, specifically for cases planned using Oncentra. It processes DICOM RT Dose, RT Structure Set, and RT Plan files to calculate various dose-volume metrics, including D2cc, Biologically Effective Dose (BED), and Equivalent Dose in 2 Gy fractions (EQD2). The tool also integrates External Beam Radiation Therapy (EBRT) doses into the calculations.

## Features

- **DICOM Data Parsing:** Reads and extracts relevant data from RTDOSE, RTSTRUCT, and RTPLAN files.
- **Patient Consistency Verification:** Ensures all input DICOM files belong to the same patient.
- **D2cc Calculation:** Calculates the minimum dose to 2 cubic centimeters of the most irradiated volume of an organ, utilizing the `dicompyler-core` library for accurate Dose-Volume Histogram (DVH) analysis.
- **BED/EQD2 Calculation:** Computes Biologically Effective Dose (BED) and Equivalent Dose in 2 Gy fractions (EQD2) for various organs, incorporating user-defined alpha/beta ratios and optional EBRT doses. Includes constraint evaluation based on EMBRACE II.
- **EBRT Integration:** Allows for the inclusion of external beam radiation therapy doses in the BED/EQD2 calculations.
- **Robust File Path Handling:** Utilizes `pathlib` for reliable handling of file paths across different operating systems, including those with special characters.
- **Graphical User Interface (GUI):** A `tkinter`-based interface for easy input of DICOM data directory and EBRT dose.
- **HTML Report Generation:** Generates a comprehensive HTML report summarizing the evaluation results, including patient information, DVH data, and constraint evaluation with visual indicators.

## Core Concepts

### Coordinate System Matching

The process of matching coordinate systems between the RTDOSE and RTSTRUCT files is handled by passing the necessary geometric information to the `dicompyler-core` library, rather than by manual calculations within the parser itself.

1.  **Data Extraction (`dicom_parser.py`):**
    *   From the **RT Structure Set** file, the script extracts the `ContourData` for each anatomical structure. This data consists of a series of (x, y, z) coordinates for points that define the contour outlines. These coordinates are already in the patient's reference coordinate system.
    *   From the **RT Dose** file, the script extracts the parameters that define the 3D dose grid's position, scale, and orientation. The key DICOM tags used are:
        *   `ImagePositionPatient`: The (x, y, z) coordinates of the top-left corner of the first pixel of the dose grid.
        *   `PixelSpacing`: The physical distance between the centers of pixels in the x and y directions.
        *   `GridFrameOffsetVector`: The distance between the z-slices of the dose grid.
        *   `ImageOrientationPatient`: Direction cosines that define the orientation of the grid's rows and columns in 3D space.

2.  **Coordinate Matching (in `calculations.py` via `dicompyler-core`):**
    *   The `dicom_parser.py` script passes all this extracted information to the `get_dvh` function located in `calculations.py`.
    *   This project uses the `dicompyler-core` library for DVH calculations. This library takes the structure contours and the dose grid definition (origin, spacing, and orientation) and internally handles the complex geometric transformation required to map the structure volumes onto the dose grid.

In short, `dicom_parser.py` acts as an information gatherer, and the heavy lifting of aligning the two different coordinate systems is delegated to the specialized `dicompyler-core` library within the `calculations.py` script.

### Dosimetric Calculations

The `calculations.py` file contains the core logic for all dosimetric calculations.

*   **DVH and D2cc Calculation:**
    *   The `get_dvh` function uses the `dvhcalc.get_dvh` function from the `dicompyler-core` library.
    *   It takes the RTSTRUCT and RTDOSE file paths and the ROI number for a specific structure.
    *   `dicompyler-core` returns a DVH object which contains the volume of the structure and the D2cc (dose to 2cc) value.
    *   The D2cc is returned as a dose per fraction.
*   **BED and EQD2 Calculation:**
    *   The `calculate_bed_and_eqd2` function calculates the Biologically Effective Dose (BED) and Equivalent Dose in 2 Gy fractions (EQD2).
    *   It takes the total dose, dose per fraction, organ name, and an optional EBRT dose as input.
    *   The alpha/beta ratio for the organ is retrieved from the `config.py` file.
    *   The BED for both the brachytherapy and EBRT components are calculated and summed.
    *   The total BED is then used to calculate the final EQD2 value.
*   **Constraint Evaluation:**
    *   The `evaluate_constraints` function compares the calculated BED and EQD2 values against the constraints defined in `config.py`.
    *   It returns a dictionary indicating whether the constraints for each organ have been met.

## Getting Started

### Prerequisites

- Python 3.x
- `pip` (Python package installer)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-repo/BrachyD2ccEval.git
    cd BrachyD2ccEval
    ```

2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### Usage

To run the GUI application:

```bash
python gui.py
```

Alternatively, to run the evaluation from the command line:

```bash
python main.py --data_dir "/path/to/your/dicom/data" --ebrt_dose 0.0 --output_html "Brachytherapy_Report.html"
```

**Arguments for `main.py`:**

- `--data_dir` (required): Path to the parent directory containing the patient's DICOM RT Dose, RT Structure Set, and RT Plan subdirectories.
- `--ebrt_dose` (optional): The prescription dose of the external beam radiation therapy in Gray (Gy). Defaults to `0.0`.
- `--output_html` (optional): If provided, the results will be saved to this HTML file.

**Example:**

```bash
python main.py --data_dir "C:\Users\echorniak\GIT\BrachyD2ccEval\DOE^JANE_ANON93124_RTDOSE_2025-07-11_122839_HDR_Dose.for.30mm.Cylinder_n1__00000" --ebrt_dose 50 --output_html "MyPatientReport.html"
```

## Configuration

Alpha/beta ratios for different organs are configured in `config.py`. You can modify these values to suit your specific requirements.

## Development Notes

Refer to `GEMINI.md` for detailed development notes and `TODO.md` for upcoming tasks.
