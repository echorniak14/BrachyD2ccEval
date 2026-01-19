# BrachyD2ccEval

## Project Overview

This project provides a comprehensive suite of tools for the evaluation and quality assurance of High-Dose-Rate (HDR) brachytherapy plans. It operates on a **hybrid architecture**, leveraging both direct parsing of Treatment Planning System (TPS) text-based DVH reports and independent recalculation from raw DICOM data.

In this model:
-   **Source of Truth**: An imported DVH text file from the TPS (e.g., Oncentra) is treated as the primary source for dose-volume metrics. This ensures that the final evaluation is based on the clinically approved data.
-   **Digital Twin (QA)**: The application simultaneously re-calculates all dose metrics from the raw RTDOSE, RTSTRUCT, and RTPLAN DICOM files using `dicompyler-core`. This acts as a "digital twin" to provide an independent QA check on the TPS data.

The tool processes this data to calculate Biologically Effective Dose (BED) and Equivalent Dose in 2 Gy fractions (EQD2), integrates External Beam Radiation Therapy (EBRT) doses, and provides a user-friendly Streamlit interface for interactive analysis, validation, and report generation.

## Features

- **Hybrid DVH Analysis:**
    - **TPS as Source of Truth:** Parses DVH metrics directly from imported TPS text files for the final report.
    - **DICOM as Digital Twin:** Independently recalculates all DVH metrics from DICOM data for QA purposes.
- **Advanced DVH Metric Validation:**
    - Compares TPS-reported metrics against the recalculated "digital twin" metrics.
    - Flags critical mismatches in Patient IDs between DICOM and text files.
    - Flags dose discrepancies greater than a configurable tolerance (e.g., 5 Gy).
- **Feasibility Logger:**
    - Allows users to append the results of the TPS vs. DICOM validation to a master `feasibility_study.csv` file.
    - This creates an aggregate log for demonstrating system accuracy and tracking performance over time.
- **Comprehensive DICOM Parsing:** Reads and extracts relevant data from RTDOSE, RTSTRUCT, and RTPLAN files.
- **Patient Consistency Verification:** Ensures all input DICOM files belong to the same patient.
- **BED/EQD2 Calculation:** Computes BED and EQD2 for various organs, incorporating user-defined alpha/beta ratios and optional EBRT doses.
- **Constraint Evaluation:** Evaluates calculated doses against EMBRACE II constraints with visual feedback.
- **Streamlit Graphical User Interface (GUI):** A modern web-based interface for:
    - Easy upload of DICOM files and **DVH text export files**.
    - Input of EBRT dose and previous brachytherapy data (JSON).
    - **Validation Dashboard:** Displays a side-by-side comparison of TPS vs. recalculated metrics with color-coded highlighting for discrepancies.
    - **Consolidated Structure Mapping:** A unified interface to map structure names from both DICOM and text files to standard constraint names.
    - Customizable constraints and alpha/beta ratios.
    - **Print Plan / PDF Report:** Generates a professional HTML/PDF report with:
        - **Historical Data Integration:** Merges prior plan data (doses, fractions) with current analysis.
        - **Additive Metrics:** Correctly calculates total fractions and cumulative doses.
        - **Clean Layout:** Institutional logo, clear summary boxes, and optimized pagination for OAR/Point dose tables.
    - Downloadable JSON data for multi-fraction accumulation.
- **Automatic Prescription Point Mapping (Cylinder Plans):** Automatically identifies and maps specific prescription points (e.g., 'Tip', 'Shoulder', '3cm') in cylinder brachytherapy plans.
- **Channel Mapping Validation:** Provides warnings for unexpected channel mappings for common applicator types.
- **Dose Accumulation:** Correctly accumulates dose over multiple treatment sessions, including EBRT and previous brachytherapy fractions.

## Core Concepts

### Hybrid Dosimetric Calculation and Validation

The application's core strength lies in its hybrid approach to dosimetric analysis, ensuring both accuracy (by trusting the TPS) and safety (by independently verifying it).

1.  **Source of Truth (TPS Text File):**
    *   When a DVH text file from the TPS is uploaded, it is parsed by `src/dvh_parser.py`.
    *   This parser extracts patient metadata (Name/ID) and the DVH data points for each structure.
    *   `src/calculations.py` then uses the `get_dvh_metrics_from_text` function to calculate the final dose metrics (D2cc, D90, etc.) by interpolating the parsed DVH data.
    *   These metrics are used for all subsequent BED/EQD2 calculations and for the final report.

2.  **Digital Twin / QA (DICOM Recalculation):**
    *   In parallel, the application always processes the raw DICOM files.
    *   The `get_dvh` function in `src/calculations.py` uses the `dicompyler-core` library to construct a "digital twin"—a completely independent recalculation of the DVH from the ground up, using the RTSTRUCT contours and the RTDOSE grid.

3.  **Validation Engine (`validators.py`):**
    *   The `validate_tps_import` function receives the results from both the "Source of Truth" (text file) and the "Digital Twin" (DICOM).
    *   It performs two key checks:
        1.  **Patient ID Match:** It verifies that the Patient ID from the DICOM files matches the ID extracted from the text file header, flagging a critical error if they don't.
        2.  **Dose Discrepancy:** It compares key metrics (e.g., D2cc, D90) from both sources. If the difference exceeds a defined tolerance, a warning is generated.
    *   The `generate_validation_dataframe` function takes the data from both sources and creates a clean, side-by-side table (`validation_df`) for display in the Streamlit UI's "Validation Dashboard" and for logging.

This hybrid model provides confidence in the final results by ensuring they match the clinical TPS, while the "digital twin" acts as a crucial safety check against data corruption or unexpected TPS behavior.

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

This application uses a Client-Server architecture. You must start both the backend API and the frontend GUI.

1.  **Start the Backend Server:**
    Open a terminal in the project root and run:
    ```bash
    uvicorn backend.src.main:app --reload
    ```
    The API will start at `http://localhost:8000`.

2.  **Start the Frontend Application:**
    Open a **new** terminal window and run:
    ```bash
    streamlit run src/streamlit_gui.py
    ```

This will open the application in your web browser. From there, you can:
1.  Upload the DICOM files (RTPLAN, RTSTRUCT, RTDOSE).
2.  Optionally, upload the corresponding **DVH text export** from the TPS to use it as the source of truth and enable validation.
3.  Upload any previous brachytherapy data (JSON format).
4.  Adjust EBRT and other parameters in the sidebar.
5.  Run the analysis and view the results, including the validation dashboard.

To run from the command line:

```bash
python run_app.py --data_dir "/path/to/your/dicom/data" --dvh_text_path "/path/to/dvh.txt" --ebrt_dose 45.0 --output_html "report.html"
```

**Arguments for `run_app.py`:**

- `--data_dir` (required): Path to the parent directory containing the patient's DICOM RT Dose, RT Structure Set, and RT Plan subdirectories.
- `--dvh_text_path` (optional): Path to the DVH text file exported from the TPS. If provided, its metrics will be used as the source of truth.
- `--ebrt_dose` (optional): The prescription dose of the external beam radiation therapy in Gray (Gy). Defaults to `0.0`.
- `--output_html` (optional): If provided, the comprehensive HTML report will be saved to this file.
- `--previous_brachy_data` (optional): Path to a previous brachytherapy evaluation report (JSON format) to incorporate its EQD2 values for dose accumulation.
- `--custom_constraints` (optional): A JSON string representing custom EQD2 constraints to override the defaults.

## Configuration

Alpha/beta ratios and clinical constraints for different plan types are configured in `src/config.py`. You can modify these values to suit your specific institutional requirements.

## Development Notes

Refer to `GEMINI.md` for detailed development notes and `TODO.md` for upcoming tasks.
