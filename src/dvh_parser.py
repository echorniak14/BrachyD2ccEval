import pandas as pd
import numpy as np
import re
from io import StringIO

# Configuration derived from your BinAnalysis.py
C_GY_TO_GY_FACTOR = 100.0
ROI_SEPARATOR = 'ROI:'
HEADER_LINE_SUBSTRING = 'Bin' # Looks for the line containing "Bin"

def parse_dvh_text_file(file_content: str):
    """
    Parses the full text content of a generic DVH export (Oncentra style).
    Returns a dictionary of structure data.
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8')

    structures = {}
    
    # 1. Split content by ROI separator (Your logic)
    roi_blocks = file_content.split(ROI_SEPARATOR)
    
    # Skip the first block (header info)
    for block in roi_blocks[1:]:
        # Extract ROI Name (first line of the block)
        lines = block.strip().splitlines()
        if not lines:
            continue
            
        roi_name = lines[0].strip()
        
        # 2. Find the data header
        try:
            # Find line index containing "Bin"
            header_idx = next(i for i, line in enumerate(lines) if HEADER_LINE_SUBSTRING in line)
            data_string = "\n".join(lines[header_idx+1:]) # Join everything after header
        except StopIteration:
            continue # Header not found in this block
            
        # 3. Parse Data using pandas (Your logic)
        try:
            df = pd.read_csv(
                StringIO(data_string),
                sep=r'\t| {2,}', # Regex for tabs or multiple spaces
                engine='python',
                header=None
            ).dropna(axis=1, how='all').dropna(axis=0, how='all')
            
            if df.shape[1] < 3:
                continue

            # Column 1 = Dose (cGy), Column 2 = Volume (ccm)
            # We skip Col 0 (Bin number)
            doses_cgy = df.iloc[:, 1].values.astype(float)
            volumes_cc = df.iloc[:, 2].values.astype(float)
            
            # Convert to Gy
            doses_gy = doses_cgy / C_GY_TO_GY_FACTOR
            
            # Sort arrays by Dose (Ascending) just to be safe for interpolation
            sort_idx = np.argsort(doses_gy)
            doses_gy = doses_gy[sort_idx]
            volumes_cc = volumes_cc[sort_idx]

            structures[roi_name] = {
                "volume_cc": np.max(volumes_cc), # Max volume is usually at 0 dose
                "dose_axis": doses_gy,
                "vol_axis": volumes_cc,
                "dose_unit": "Gy"
            }
            
        except Exception as e:
            print(f"Warning: Could not parse block for {roi_name}: {e}")
            continue

    return structures

def get_dose_at_volume(structure_data, target_volume_cc):
    """
    Calculates D_V (Dose at Volume) using inverse interpolation.
    Adapted from your calculate_dose_at_volume logic.
    """
    doses = structure_data["dose_axis"]
    volumes = structure_data["vol_axis"]
    
    # Boundary checks
    if target_volume_cc > np.max(volumes): return 0.0
    if target_volume_cc <= np.min(volumes): return np.max(doses)
    
    # Interpolation: Volume (Decreasing) vs Dose (Increasing)
    # np.interp requires X coordinate to be increasing.
    # We flip volumes to make them increasing (0 -> MaxVol)
    # We flip doses to match (MaxDose -> 0)
    return np.interp(target_volume_cc, volumes[::-1], doses[::-1])

def get_dose_at_percent_volume(structure_data, percent):
    """
    Calculates D90%, D98%, etc.
    """
    total_vol = structure_data["volume_cc"]
    if total_vol == 0: return 0.0
    
    target_vol_cc = total_vol * (percent / 100.0)
    return get_dose_at_volume(structure_data, target_vol_cc)