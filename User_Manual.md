# BrachyD2ccEval User Manual

## 1. Introduction

The BrachyD2ccEval tool is a software application designed to streamline the evaluation and quality assurance (QA) of HDR brachytherapy plans. It operates on a **hybrid architecture**, where it uses an imported Treatment Planning System (TPS) DVH report as the **source of truth** and simultaneously recalculates dose from raw DICOM files to serve as a **"digital twin" for QA**.

This approach ensures that the final clinical evaluation is based on the official TPS data, while the independent DICOM recalculation provides a crucial safety and accuracy check.

### Key Features:

-   **Hybrid DVH Analysis**: Uses a TPS DVH text export as the primary source for metrics while independently recalculating from DICOM for validation.
-   **Advanced DVH Metric Validation**:
    -   Compares TPS-reported metrics against the recalculated "digital twin" metrics.
    -   Flags critical mismatches in Patient IDs between DICOM and text files.
    -   Flags dose discrepancies greater than a configurable tolerance.
-   **Feasibility Logger**: A feature that allows users to append the results of the TPS vs. DICOM validation to a master `feasibility_study.csv` file, creating a log for demonstrating system accuracy over time.
-   **Automated DICOM Parsing**: Reads data from RTDOSE, RTSTRUCT, and RTPLAN files.
-   **Comprehensive Dosimetry**: Calculates BED, EQD2, and accumulates dose from EBRT and previous brachytherapy fractions.
-   **Constraint Evaluation**: Evaluates plans against EMBRACE II or custom constraints.
-   **Automatic Prescription Point Mapping**: For cylinder plans, automatically identifies and maps prescription points like 'Tip', 'Shoulder', and '3cm'.

## 2. Installation

To run the BrachyD2ccEval tool, you will need to have Python installed on your system.

1.  Navigate to the project directory in your terminal.
2.  Install the required libraries using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

## 3. User Interface Guide

To launch the application, run the following command from the project directory:

```bash
streamlit run src/streamlit_gui.py
```

This will open the main interface in your web browser. The UI is organized into a sidebar for treatment parameters and three main tabs: **Pre-Planning**, **Plan Analysis**, and **Print Plan**.

### Sidebar: Treatment Parameters

The sidebar on the left is used to define the dose parameters for the entire treatment course.

-   **EBRT Dose:** Enter the total dose and number of fractions for the external beam portion of the treatment. The application correctly handles this dose, ensuring it is only counted **once** in a cumulative plan.
-   **Proposed Brachytherapy:**
    -   **Dose per Fraction:** The prescribed dose for the current brachytherapy plan.
    -   **Number of Fractions:** The number of fractions for the **current plan being uploaded only**.
    -   A caption below this input reminds you: *"Enter fractions for the CURRENT plan only. Previous plan fractions are read from the uploaded JSON."*

### "Pre-Planning" Tab

This tab is for setting up the context of your evaluation.

-   **Constraint Template:** Select the clinical protocol you are evaluating against (e.g., EMBRACE II).
-   **Previous Brachytherapy Data:** Use this file uploader to select a JSON results file from a previous ECHO session. This is the core of the dose summation feature.
-   **Previous Plan Summary:** After uploading a JSON file, a summary box appears, showing the Patient, Plan Name, and number of fractions from that previous plan. It also contains an important reminder on how EBRT dose is handled in summations.

### "Plan Analysis" Tab

This tab is for uploading files for a specific plan and reviewing the results.

-   **DICOM Files (Required):** The main file uploader for the RTDOSE, RTSTRUCT, and RTPLAN files.
-   **DVH Text File (Optional):** An uploader for the DVH report exported from your TPS (e.g., Oncentra). **Uploading this file is highly recommended** as it enables the validation features.
-   **Structure Mapping:** An expander that appears after files are uploaded. It provides an interface to map all structure names found in your files to the application's standard constraint names (e.g., Bladder, Rectum).
-   **Run Analysis Button:** Starts the calculation and validation process.
-   **Analysis Results:** After running, this section appears and includes:
    -   **Validation Warnings:** Displays any critical errors (like patient ID mismatch) or dose discrepancies.
    -   **TPS vs DICOM Comparison:** An expander showing a side-by-side comparison of metrics from the TPS text file vs. the recalculated DICOM data.
    -   **Download Full Results (JSON):** A button to save the complete analysis results for the current cumulative plan. This file can be used as the input for a future dose summation.
    -   **Constraint Evaluation:** The main results table.

### "Print Plan" Tab

This tab is for exporting the final results.

-   **Download Full Results (JSON):** A button to download the complete, cumulative results as a JSON file. This is identical to the button on the Plan Analysis tab.
-   **Generate PDF:** A button to generate a PDF report of the analysis.

## 4. Step-by-Step Workflow

There are two primary workflows in ECHO: analyzing a single plan or performing a cumulative dose summation over multiple plans.

### Workflow A: Analyzing a Single Plan

Use this workflow when you are evaluating the first plan in a patient's treatment course.

1.  **Launch the Application:**
    -   Open a terminal and run `streamlit run src/streamlit_gui.py`.

2.  **Set Treatment Parameters (Sidebar):**
    -   In the sidebar, enter the total **EBRT Dose** and number of fractions for the patient.
    -   Under "Proposed Brachytherapy", enter the **Dose per Fraction** and **Number of Fractions** for the plan you are about to upload.

3.  **Go to the "Plan Analysis" Tab.**

4.  **Upload Files:**
    -   Upload the RTDOSE, RTSTRUCT, and RTPLAN files.
    -   (Recommended) Upload the corresponding DVH report exported from your TPS to enable validation.

5.  **Map Structures:**
    -   In the "Structure Mapping" expander, map the structure names from your files to the standard constraint names.

6.  **Run Analysis and Review Results:**
    -   Click the **"Run Analysis"** button.
    -   Review the **Validation Warnings** and the **TPS vs DICOM Comparison** table.
    -   Review the final constraint evaluation.

7.  **Save Results for Future Summation:**
    -   In the "Analysis Results" section or the "Print Plan" tab, click **"Download Full Results (JSON)"**.
    -   Save this file with a descriptive name (e.g., `Patient_MRN_Fx1-3.json`). This file is required for the dose summation workflow.

### Workflow B: Cumulative Dose Summation

Use this workflow when you have already analyzed a previous plan and want to add a new one.

1.  **Go to the "Pre-Planning" Tab.**
    -   Select the appropriate **Constraint Template**.
    -   Under "Previous Brachytherapy Data", upload the JSON file you saved from the previous analysis (e.g., `Patient_MRN_Fx1-3.json`).
    -   A **"Previous Plan Summary"** will appear. **Verify** that the patient information and number of fractions displayed are correct.

2.  **Set Treatment Parameters (Sidebar):**
    -   **EBRT:** If you already entered the EBRT dose during the first analysis, you can set the EBRT dose to 0. The application counts the EBRT dose specified in the sidebar **once** per session.
    -   **Brachytherapy:** Enter the **Number of Fractions** for the **new plan** you are about to analyze (e.g., if you are adding one more fraction, enter `1`).

3.  **Go to the "Plan Analysis" Tab.**
    -   Upload the DICOM and (optional) DVH text files for the **new plan**.

4.  **Map Structures and Run Analysis:**
    -   Map any new structures and click **"Run Analysis"**.

5.  **Review and Save:**
    -   The results will now show the cumulative BED and EQD2 values from all combined plans.
    -   Download the new results JSON file. This new file now contains the complete history and can be used for the *next* fraction.

## 5. Interpreting the Report

The final report provides a comprehensive summary of the plan evaluation based on the **TPS text file data**.

### Validation Warnings

If a DVH text file was provided, the application will display warnings at the top of the results screen if any issues were detected:
-   **CRITICAL: Patient ID Mismatch:** This indicates the patient MRN in the DICOM files is different from the MRN in the text file. The data is unreliable and should not be used.
-   **QA Mismatch:** This warning appears if a dose metric (e.g., Bladder D2cc) differs between the TPS text file and the independent DICOM recalculation by more than the set tolerance. This may indicate a need to review the plan data or export settings.

### DVH Results

The main tables display the following metrics for each organ, calculated from the TPS data:
*   **Volume (cc):** The total volume of the organ.
*   **Dose Metrics (per fraction):** D0.1cc, D1cc, D2cc, D90, etc., as derived from the TPS DVH report.
*   **EQD2 (Gy):** The final accumulated Equivalent Dose in 2 Gy fractions, which includes contributions from EBRT and any previous brachytherapy sessions.
*   **Constraint Status:** Indicates whether the calculated EQD2 meets the predefined constraint.

## 6. Troubleshooting

-   **"Missing required files" error:** Ensure you have uploaded one of each: RTDOSE, RTSTRUCT, and RTPLAN.
-   **"CRITICAL: Patient ID Mismatch" warning:** Verify you have uploaded the correct DICOM and text files for the same patient.
-   **PDF Generation Fails:** Ensure the application has access to the `wkhtmltopdf.exe` executable located in the `src/vendor` directory.

For any other issues, please refer to the project's issue tracker or contact the development team.