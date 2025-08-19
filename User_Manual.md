# BrachyD2ccEval User Manual

## 1. Introduction

The BrachyD2ccEval tool is a software application designed to streamline the evaluation of HDR brachytherapy plans, particularly for cases planned using Oncentra. It automates the process of calculating dose-volume histogram (DVH) metrics, Biological Effective Dose (BED), and Equivalent Dose in 2 Gy fractions (EQD2), providing a comprehensive report for clinical review.

### Key Features:

*   Automated parsing of DICOM RT Dose, RT Structure Set, and RT Plan files.
*   Calculation of critical DVH metrics, including D2cc, D1cc, and D0.1cc.
*   Integration of External Beam Radiation Therapy (EBRT) and previous brachytherapy doses.
*   Evaluation of treatment plans against predefined constraints (based on EMBRACE II).
*   Generation of a clear and concise report in both HTML and PDF formats.

## 2. Installation

To run the BrachyD2ccEval tool, you will need to have Python installed on your system, along with the required libraries. You can install the necessary libraries using the following command:

```
pip install -r requirements.txt
```

## 3. User Interface Guide

The BrachyD2ccEval tool features a user-friendly graphical user interface (GUI) that allows you to easily perform plan evaluations.

To launch the application, open a new terminal, navigate to the project directory, and run the command:
```
streamlit run src/streamlit_gui.py
```

![GUI Screenshot](src/assets/gui_screenshot.png)  <!-- This is the updated GUI screenshot -->

### Components:

*   **DICOM Data Directory:** Use the "Browse" button to select the directory containing the patient's DICOM files (RTDOSE, RTst, RTPLAN).
*   **EBRT Dose (Gy):** Enter the prescribed dose of the external beam radiation therapy in Gray (Gy).
*   **Previous Brachy Report (HTML):** If the patient has undergone previous brachytherapy treatments, you can select the HTML report from the previous evaluation to incorporate its EQD2 values.
*   **Run Evaluation:** Once you have entered all the required information, click this button to start the evaluation process.
*   **Plan Name:** The name of the treatment plan will be displayed here after the evaluation is complete.

## 4. Step-by-Step Workflow


    ```
    
    ```
2.  **Select DICOM Data Directory:** Click the "Browse" button and select the folder containing the patient's DICOM files.
3.  **Enter EBRT Dose:** If applicable, enter the EBRT dose in the corresponding field.
4.  **Select Previous Brachy Report:** If applicable, select the HTML report from a previous brachytherapy treatment.
5.  **Run Evaluation:** Click the "Run Evaluation" button.
6.  **View Report:** Once the evaluation is complete, a message box will appear, and the HTML report will automatically open in your web browser. A PDF report will also be generated in the `reports` directory.

## 5. Interpreting the Report

The report provides a comprehensive summary of the plan evaluation.

### Patient Information:

This section displays the patient's name, MRN, the plan name, and the prescribed doses.

### Dose Volume Histogram (DVH) Results:

This table displays the following metrics for each organ at risk (OAR):

*   **Volume (cc):** The total volume of the organ in cubic centimeters.
*   **D0.1cc (per fraction) (Gy):** The minimum dose received by the 0.1cc of the organ that receives the highest dose.
*   **D1cc (per fraction) (Gy):** The minimum dose received by the 1cc of the organ that receives the highest dose.
*   **D2cc (per fraction) (Gy):** The minimum dose received by the 2cc of the organ that receives the highest dose.
*   **Total D2cc (Gy):** The total D2cc dose over all fractions.
*   **BED (Gy):** The Biological Effective Dose, which accounts for the biological effects of different dose fractionation schedules.
*   **EQD2 (Gy):** The Equivalent Dose in 2 Gy fractions, which allows for the comparison of different fractionation schedules.
*   **EQD2 Constraint Met:** Indicates whether the calculated EQD2 meets the predefined constraint for that organ.
*   **Dose to Meet Constraint (Gy):** If the EQD2 constraint is not met, this value indicates the dose per fraction that would be required to meet the constraint.

## 6. Troubleshooting

*   **"Could not find all required DICOM subdirectories" error:** Make sure the selected directory contains subdirectories with "RTDOSE", "RTst", and "RTPLAN" in their names.
*   **"DICOM files belong to different patients" error:** Ensure that all the DICOM files in the selected directory belong to the same patient.

For any other issues, please contact the development team.
