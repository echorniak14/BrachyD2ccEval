# src/validators.py
from datetime import datetime

def validate_patient_ids(dicom_datasets, json_history=None):
    """
    Checks if PatientIDs match across all DICOM files and optional JSON history.
    Returns: List of error messages.
    """
    errors = []
    if not dicom_datasets:
        return errors

    # 1. Check DICOM consistency
    reference_id = str(dicom_datasets[0].PatientID).strip()
    for ds in dicom_datasets[1:]:
        current_id = str(ds.PatientID).strip()
        if current_id != reference_id:
            errors.append(f"CRITICAL: Patient ID Mismatch. Found {reference_id} and {current_id} in DICOM files.")

    # 2. Check JSON consistency
    if json_history:
        json_id = str(json_history.get("patient_mrn", "")).strip()
        if json_id and json_id != reference_id:
            errors.append(f"CRITICAL: History Mismatch. Current Plan: {reference_id}, History JSON: {json_id}.")
            
    return errors

def validate_file_completeness(file_types_found):
    """
    Ensures RTPLAN, RTSTRUCT, and RTDOSE are present and unique.
    file_types_found: List of strings ['RTPLAN', 'RTDOSE', etc.]
    """
    errors = []
    required = {'RTPLAN', 'RTSTRUCT', 'RTDOSE'}
    found_set = set(file_types_found)
    
    # Check missing
    missing = required - found_set
    if missing:
        errors.append(f"Missing required files: {', '.join(missing)}")
        
    # Check duplicates (e.g. two RTPLANs)
    from collections import Counter
    counts = Counter(file_types_found)
    for ftype, count in counts.items():
        if ftype in required and count > 1:
            errors.append(f"Multiple files found for {ftype}. Please upload only one.")
            
    return errors

def check_plan_time(plan_time_str):
    """Checks if time is within 07:00 - 17:00."""
    warnings = []
    if not plan_time_str: return warnings
    
    try:
        # Format usually HHMMSS or HHMMSS.ffffff
        time_obj = datetime.strptime(plan_time_str.split('.')[0], "%H%M%S").time()
        start_day = datetime.strptime("070000", "%H%M%S").time()
        end_day = datetime.strptime("170000", "%H%M%S").time()
        
        if not (start_day <= time_obj <= end_day):
            warnings.append(f"Warning: Plan time ({time_obj}) is outside standard hours (07:00-17:00).")
    except ValueError:
        pass 
    return warnings

def validate_channel_mapping(channel_mapping, applicator_type):
    """
    Validates catheter-to-channel mapping based on applicator type.
    channel_mapping: List of dicts [{'channel_number': '1', 'transfer_tube_number': '1'}, ...]
    """
    warnings = []
    # Map input list to a simple dict: {Channel: Tube}
    map_dict = {str(c.get('channel_number')): str(c.get('transfer_tube_number')) for c in channel_mapping}
    
    if applicator_type == "Tandem and Ovoid":
        expected = {'1': '1', '2': '3', '3': '5'} # Cath 1->Ch1, Cath 2->Ch3, Cath 3->Ch5
        for cath, chan in expected.items():
            if map_dict.get(cath) != chan:
                warnings.append(f"T&O Mapping Error: Catheter {cath} should map to Channel {chan}. Found {map_dict.get(cath)}.")

    elif applicator_type == "Cylinder":
        # Cath 1 -> Channel 5
        if map_dict.get('1') != '5':
            warnings.append(f"Cylinder Mapping Error: Catheter 1 should map to Channel 5. Found {map_dict.get('1')}.")

    elif applicator_type == "Tandem and Ring":
        expected = {'1': '1', '2': '5'} # Ring->1, Tandem->5
        for cath, chan in expected.items():
            if map_dict.get(cath) != chan:
                warnings.append(f"T&R Mapping Error: Catheter {cath} should map to Channel {chan}. Found {map_dict.get(cath)}.")
                
    return warnings

def check_dwell_times(dwell_times):
    """Checks for dwell times between 0 and 1 second."""
    warnings = []
    for t in dwell_times:
        if 0.0 < t < 1.0:
            warnings.append(f"Warning: Found small dwell time of {t}s. Should be 0 or >1s.")
            break # One warning is enough
    return warnings

def check_fraction_count(planned, calculated):
    """Compares DICOM planned fractions vs User input."""
    warnings = []
    if int(planned) != int(calculated):
        warnings.append(f"Warning: DICOM plans for {planned} fractions, but calculation uses {calculated}.")
    return warnings

def validate_tps_import(calculated_dvh, reported_dvh, tolerance_gy=5.0):
    """
    Compares the Python-calculated voxel metrics against the imported TPS text file metrics.
    
    Args:
        calculated_dvh (dict): Results from get_dvh (DICOM-based).
        reported_dvh (dict): Results from get_dvh_metrics_from_text (Text-based).
        tolerance_gy (float): Allowed deviation in Gy before flagging.
    
    Returns:
        list: List of warning strings detailing specific mismatches.
    """
    warnings = []
    
    # Iterate through organs present in BOTH datasets
    for organ, tps_data in reported_dvh.items():
        if organ not in calculated_dvh:
            continue
            
        calc_data = calculated_dvh[organ]
        
        # Metrics to compare (Physical Dose per Fraction)
        metrics_to_check = {
            'D2cc': 'd2cc_gy_per_fraction',
            'D90': 'd90_gy_per_fraction',
            'D98': 'd98_gy_per_fraction'
        }
        
        for label, key in metrics_to_check.items():
            # Ensure key exists in both
            if key not in tps_data or key not in calc_data:
                continue
                
            val_tps = tps_data.get(key, 0.0)
            val_calc = calc_data.get(key, 0.0)
            
            # Calculate absolute difference
            diff = abs(val_tps - val_calc)
            
            if diff > tolerance_gy:
                warnings.append(
                    f"QA Mismatch [{organ} {label}]: TPS reported {val_tps:.2f} Gy, "
                    f"Calculated {val_calc:.2f} Gy. Diff: {diff:.2f} Gy (> {tolerance_gy} Gy limit)."
                )
                
    return warnings