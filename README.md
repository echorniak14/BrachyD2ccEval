# BrachyD2ccEval

## Project Overview

This project aims to automate and streamline the evaluation process for HDR brachytherapy plans, specifically for cases planned using Oncentra. It processes DICOM RT Dose, RT Structure Set, and RT Plan files to calculate various dose-volume metrics, including D0.1cc, D1cc, D2cc, Biologically Effective Dose (BED), and Equivalent Dose in 2 Gy fractions (EQD2). The tool also integrates External Beam Radiation Therapy (EBRT) doses into the calculations and provides a user-friendly Streamlit graphical interface for interactive analysis and report generation.

## Features

## Features

- **DICOM Data Parsing:** Reads and extracts relevant data from RTDOSE, RTSTRUCT, and RTPLAN files.
- **Patient Consistency Verification:** Ensures all input DICOM files belong to the same patient.
- **Dose Metric Calculation (D0.1cc, D1cc, D2cc):** Calculates the minimum dose to 0.1, 1, and 2 cubic centimeters of the most irradiated volume of an organ, utilizing the `dicompyler-core` library for accurate Dose-Volume Histogram (DVH) analysis.
- **BED/EQD2 Calculation:** Computes Biologically Effective Dose (BED) and Equivalent Dose in 2 Gy fractions (EQD2) for various organs, incorporating user-defined alpha/beta ratios and optional EBRT doses.
- **Constraint Evaluation:** Evaluates calculated doses against EMBRACE II constraints, with visual indicators (red/green) in the GUI and reports.
- **Plan Type-Based Constraint Management:** Dynamically manages and applies constraints based on predefined plan types, allowing for flexible and accurate evaluation across different treatment scenarios.

- **Dose to Meet Constraint Calculation:** For unmet constraints, calculates the highest fractional brachytherapy dose needed to meet the constraint, providing actionable feedback.
- **EBRT Integration:** Allows for the inclusion of external beam radiation therapy doses in the BED/EQD2 calculations.
- **Robust File Path Handling:** Utilizes `pathlib` for reliable handling of file paths across different operating systems, including those with special characters.
- **Streamlit Graphical User Interface (GUI):** A modern web-based interface for:
    - Easy upload of DICOM files.
    - Input of EBRT dose and previous brachytherapy data (HTML or JSON).
    - Customizable alpha/beta ratios and EQD2 constraints.
    - Interactive display of DVH and Point Dose results with visual constraint indicators.
    - Downloadable HTML and PDF reports.
    - Export of current plan's brachytherapy data to JSON for multi-fraction dose accumulation.
- **HTML Report Generation:** Generates a comprehensive HTML report summarizing the evaluation results, including patient information, DVH data, and constraint evaluation with visual indicators.
- **PDF Report Generation:** Converts the HTML report to a downloadable PDF.
- **JSON Data Export/Import:**
    - Export current plan's DVH and point dose data to a JSON file, specifically designed for re-importing as "previous brachytherapy data" for multi-fraction dose accumulation.
    - Import previous brachytherapy data from either HTML reports or the newly defined JSON format.
- **Interactive Dose Point Mapping:** Provides a user-friendly interface to manually map DICOM RT Plan points to clinical constraints using dropdown menus, offering greater control and flexibility over the evaluation process.


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

*   **DVH and Dose-Volume Metric Calculation (D0.1cc, D1cc, D2cc, D90, D98, Max, Mean, Min):**
    *   The `get_dvh` function uses the `dvhcalc.get_dvh` function from the `dicompyler-core` library to compute Dose-Volume Histograms.
    *   It takes the RTSTRUCT and RTDOSE file paths and the ROI number for a specific structure.
    *   For each structure, it extracts key dose-volume metrics such as D0.1cc, D1cc, D2cc (minimum dose to 0.1, 1, and 2 cubic centimeters of the most irradiated volume), D90, D98 (dose covering 90% and 98% of the volume), and Max, Mean, Min doses. These are returned as dose per fraction.
*   **BED and EQD2 Calculation:**
    *   The `calculate_bed_and_eqd2` function computes the Biologically Effective Dose (BED) and Equivalent Dose in 2 Gy fractions (EQD2).
    *   It takes the total dose, dose per fraction, organ name, and optional EBRT dose and previous brachytherapy EQD2 as input.
    *   The alpha/beta ratio for the organ is retrieved from the `config.py` file.
    *   The BED for the current brachytherapy plan, EBRT, and any previous brachytherapy fractions are calculated and summed to determine the total accumulated BED.
    *   The total BED is then used to calculate the final accumulated EQD2 value.
*   **Constraint Evaluation:**
    *   The `evaluate_constraints` function compares the calculated EQD2 values against the constraints defined in `config.py` (or user-defined constraints from the GUI).
    *   It returns a dictionary indicating whether the constraints for each organ have been met.
*   **Dose to Meet Constraint Calculation:**
    *   For any organ that fails to meet its EQD2 constraint, the `calculate_dose_to_meet_constraint` function determines the highest fractional brachytherapy dose required to meet that constraint exactly.
    *   This calculation involves converting the EQD2 constraint back to a total BED target, accounting for any EBRT dose and previous brachytherapy fractions, and then solving a quadratic equation to find the necessary brachytherapy dose per fraction.
    *   This provides actionable feedback for plan optimization, indicating what dose adjustment might be needed to satisfy the constraint.

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

### Usage

To run the Streamlit GUI application (recommended):

```bash
streamlit run src/streamlit_gui.py
```

This will open the application in your web browser, providing an interactive interface for uploading DICOM files, setting parameters, and viewing results.

Alternatively, to run the evaluation from the command line (for scripting or batch processing):

```bash
python main.py --data_dir "/path/to/your/dicom/data" --ebrt_dose 0.0 --output_html "Brachytherapy_Report.html" --previous_brachy_data "/path/to/previous_report.html_or_json" --custom_constraints '{"Bladder": {"EQD2": {"max": 80}}}'
```

**Arguments for `main.py`:**

- `--data_dir` (required): Path to the parent directory containing the patient's DICOM RT Dose, RT Structure Set, and RT Plan subdirectories.
- `--ebrt_dose` (optional): The prescription dose of the external beam radiation therapy in Gray (Gy). Defaults to `0.0`.
- `--output_html` (optional): If provided, the comprehensive HTML report will be saved to this file.
- `--previous_brachy_data` (optional): Path to a previous brachytherapy evaluation report (HTML or JSON format) to incorporate its EQD2 values for dose accumulation. If a JSON file is provided, it should be the output from the GUI's "Download Brachy Data (JSON)" button.
- `--custom_constraints` (optional): A JSON string representing custom EQD2 constraints. This will override the default constraints defined in `config.py` for the selected plan type. Example: `'{"Bladder": {"EQD2": {"max": 80}}}'`

**Example (Command Line):**

```bash
python main.py --data_dir "C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\Jane Doe" --ebrt_dose 50 --output_html "MyPatientReport.html" --previous_brachy_data "C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\previous_brachy_plan.json" --custom_constraints '{"Rectum": {"EQD2": {"max": 75}}}'
```


## Configuration

Alpha/beta ratios, plan types, and their associated point dose constraints are configured in `config.py`. You can modify these values to suit your specific requirements.


## Development Notes

Refer to `GEMINI.md` for detailed development notes and `TODO.md` for upcoming tasks.
