import pydicom
import os
from pathlib import Path

# Function to find the RTPLAN file
def find_rtplan_file(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if "RTPLAN" in root:
                file_path = os.path.join(root, file)
                if file.endswith('.dcm'):
                    return file_path
    return None

# Main script
dicom_dir = Path("C:\\Users\\echorniak\\GIT\\BrachyD2ccEval\\sample_data\\Jane Doe")
rtplan_file = find_rtplan_file(dicom_dir)

if rtplan_file:
    print(f"Inspecting RTPLAN file: {rtplan_file}\n")
    ds = pydicom.dcmread(rtplan_file)
    print(ds) # Print the entire dataset
else:
    print("RTPLAN file not found in the specified directory.")
