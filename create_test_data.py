
import os
import shutil
import pydicom
import json
from glob import glob

SOURCE_DIR = r"c:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\Jane Doe"
DEST_BASE = r"c:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\integrity_test_cases"

def find_dicom_files(root_dir):
    dcm_files = {}
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.endswith(".dcm") or "." not in f: # scan all files just in case
                full_path = os.path.join(root, f)
                try:
                    ds = pydicom.dcmread(full_path, stop_before_pixels=True, force=True)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': dcm_files["RTPLAN"] = full_path
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': dcm_files["RTDOSE"] = full_path
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': dcm_files["RTSTRUCT"] = full_path
                except:
                    pass
    return dcm_files

def setup_test_folders():
    if os.path.exists(DEST_BASE):
        shutil.rmtree(DEST_BASE)
    os.makedirs(DEST_BASE)
    
    folders = [
        "1_Valid_Data",
        "2_PatientID_Mismatch",
        "3_Missing_Files",
        "4_Duplicate_Files",
        "5_JSON_Mismatch",
        "6_Warning_BadTime"
    ]
    
    paths = {}
    for folder in folders:
        p = os.path.join(DEST_BASE, folder)
        os.makedirs(p)
        paths[folder] = p
    return paths

def create_valid_set(dest_dir, source_files):
    for ftype, src in source_files.items():
        shutil.copy(src, os.path.join(dest_dir, f"{ftype}.dcm"))

def modify_dicom_tag(filepath, tag, value):
    ds = pydicom.dcmread(filepath)
    if hasattr(ds, tag):
        setattr(ds, tag, value)
    else:
        ds.add_new(tag, 'LO', value) # simplified
    ds.save_as(filepath)

def main():
    print("Finding source files...")
    sources = find_dicom_files(SOURCE_DIR)
    if len(sources) < 3:
        print(f"Error: Could not find all 3 DICOM types in {SOURCE_DIR}. Found: {sources.keys()}")
        return

    print("Creating folder structure...")
    dirs = setup_test_folders()
    
    # 1. Valid Data
    print("Generating Case 1: Valid Data")
    create_valid_set(dirs["1_Valid_Data"], sources)
    
    # 2. Patient ID Mismatch
    print("Generating Case 2: Patient ID Mismatch")
    create_valid_set(dirs["2_PatientID_Mismatch"], sources)
    # Modify Plan ID
    modify_dicom_tag(os.path.join(dirs["2_PatientID_Mismatch"], "RTPLAN.dcm"), "PatientID", "WRONG_ID_123")
    
    # 3. Missing Files
    print("Generating Case 3: Missing Files")
    # Only copy Plan and Struct
    shutil.copy(sources["RTPLAN"], os.path.join(dirs["3_Missing_Files"], "RTPLAN.dcm"))
    shutil.copy(sources["RTSTRUCT"], os.path.join(dirs["3_Missing_Files"], "RTSTRUCT.dcm"))
    
    # 4. Duplicate Files
    print("Generating Case 4: Duplicate Files")
    create_valid_set(dirs["4_Duplicate_Files"], sources)
    shutil.copy(sources["RTPLAN"], os.path.join(dirs["4_Duplicate_Files"], "RTPLAN_Copy.dcm"))
    
    # 5. JSON Mismatch
    print("Generating Case 5: JSON Mismatch")
    create_valid_set(dirs["5_JSON_Mismatch"], sources)
    # Create dummy JSON
    dummy_json = {
        "patient_name": "Doe^Jane",
        "patient_mrn": "MISMATCH_MRN_999",
        "plan_name": "Previous Plan",
        "dvh_results": {}
    }
    with open(os.path.join(dirs["5_JSON_Mismatch"], "history.json"), "w") as f:
        json.dump(dummy_json, f)

    # 6. Bad Time
    print("Generating Case 6: Plan Time Warning")
    create_valid_set(dirs["6_Warning_BadTime"], sources)
    # Set to 11 PM
    modify_dicom_tag(os.path.join(dirs["6_Warning_BadTime"], "RTPLAN.dcm"), "RTPlanTime", "230000")

    print(f"Done! Test data created in {DEST_BASE}")

if __name__ == "__main__":
    main()
