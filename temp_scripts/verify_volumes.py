import pydicom
from pathlib import Path
import numpy as np
import pandas as pd
import os
from src.calculations import calculate_contour_volumes, normalize_structure_name

def find_dicom_files(root_dir, patient_id):
    """Finds RTSTRUCT and RTDOSE files for a given patient ID."""
    files = {"RTSTRUCT": None, "RTDOSE": None}
    for dirpath, _, filenames in os.walk(root_dir):
        if patient_id in dirpath:
            for f in filenames:
                if f.endswith('.dcm'):
                    file_path = os.path.join(dirpath, f)
                    try:
                        ds = pydicom.dcmread(file_path, force=True)
                        if ds.Modality == 'RTSTRUCT':
                            files["RTSTRUCT"] = file_path
                        elif ds.Modality == 'RTDOSE':
                            files["RTDOSE"] = file_path
                    except Exception:
                        continue # Ignore files that are not valid DICOM
    return files

def get_expected_volumes(excel_file):
    """Reads the ground truth volumes from the specified Excel file using direct cell access."""
    try:
        df = pd.read_excel(excel_file, sheet_name='gyn HDR BT docu', header=None)
        volumes = {}

        # Map structure names to their corresponding cell locations (row, column)
        # Note: pandas uses 0-based indexing, so C53 is (52, 2), C67 is (66, 2), etc.
        structure_cells = {
            "bladder": (52, 2),  # C53
            "rectum": (66, 2),   # C67
            "sigmoid": (78, 2),  # C79
            "bowel": (99, 2)     # C100 (Intestines)
        }

        for name, (row, col) in structure_cells.items():
            if row < len(df) and col < len(df.columns):
                volume_value = df.iloc[row, col]
                if pd.notna(volume_value) and isinstance(volume_value, (int, float)):
                    volumes[name] = float(volume_value)
                else:
                    print(f"Warning: Could not read volume for {name} from cell ({row+1}, {col+1}). Value: {volume_value}")
            else:
                print(f"Warning: Cell ({row+1}, {col+1}) for {name} is out of bounds.")

    except Exception as e:
        print(f"Error reading or parsing Excel file: {e}")
        return {}
    return volumes

def main():
    patient_id = 'A2512389'
    sample_data_dir = r"C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data"
    excel_file = r"C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\ABS Spreadsheet 2.xls"

    dicom_files = find_dicom_files(sample_data_dir, patient_id)
    rtstruct_file = dicom_files.get("RTSTRUCT")

    if not rtstruct_file or not Path(rtstruct_file).is_file():
        print(f"Error: RTSTRUCT file for patient {patient_id} not found in {sample_data_dir}")
        return
    if not Path(excel_file).is_file():
        print(f"Error: Excel file not found at {excel_file}")
        return

    # We need to load the RTSTRUCT dataset to pass to calculate_contour_volumes
    rt_struct_dataset = pydicom.dcmread(rtstruct_file)
    calculated_volumes = calculate_contour_volumes(rtstruct_file, rt_struct_dataset)
    expected_volumes = get_expected_volumes(excel_file)

    print("--- Contour Volume Comparison ---")
    print(f"{'Structure':<25} | {'Calculated (cm³)':<20} | {'Expected (cm³)':<20} | {'Difference (cm³)':<20}")
    print("-" * 90)

    all_structures = sorted(set(calculated_volumes.keys()) | set(expected_volumes.keys()))

    for name in all_structures:
        calc_vol = calculated_volumes.get(name)
        exp_vol = expected_volumes.get(name)
        
        display_name = name.capitalize()

        calc_str = f"{calc_vol:.2f}" if calc_vol is not None else "Not Found"
        exp_str = f"{exp_vol:.2f}" if exp_vol is not None else "Not Found"
        
        if calc_vol is not None and exp_vol is not None:
            diff_str = f"{calc_vol - exp_vol:+.2f}"
        else:
            diff_str = "N/A"
        
        print(f"{display_name:<25} | {calc_str:<20} | {exp_str:<20} | {diff_str:<20}")

if __name__ == "__main__":
    main()