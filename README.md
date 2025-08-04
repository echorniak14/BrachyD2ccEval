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