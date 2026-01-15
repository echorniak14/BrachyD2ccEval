from datetime import datetime
import pandas as pd
import os

def validate_patient_ids(dicom_data_tuples, json_history=None):
    """
    Checks if PatientIDs match across all DICOM files and optional JSON history.
    dicom_data_tuples: List of (pydicom.Dataset, filename/modality_string)
    Returns: List of error messages.
    """
    errors = []
    if not dicom_data_tuples:
        return errors

    # 1. Check DICOM consistency
    # ref_ds is the first dataset
    ref_ds, ref_name = dicom_data_tuples[0]
    reference_id = str(ref_ds.PatientID).strip()
    
    for ds, fname in dicom_data_tuples[1:]:
        current_id = str(ds.PatientID).strip()
        if current_id != reference_id:
            errors.append(f"CRITICAL: Patient ID Mismatch. File '{fname}' has ID '{current_id}', but '{ref_name}' has '{reference_id}'.")

    # 2. Check JSON consistency
    if json_history:
        json_id = str(json_history.get("patient_mrn", "")).strip()
        if json_id and json_id != reference_id:
            errors.append(f"CRITICAL: History Mismatch. Current Plan ({reference_id}) does not match History JSON ({json_id}).")
            
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

def check_fraction_count(planned_fractions, proposed_fractions):
    """Compares DICOM planned fractions vs User input."""
    warnings = []
    if planned_fractions != proposed_fractions:
        warnings.append(f"Fraction count mismatch: Planned {planned_fractions} vs Proposed {proposed_fractions}. Calculation will use {proposed_fractions} fractions **for this plan** (plus any historical fractions).")
    return warnings

def check_dose_grid(rtdose_ds):
    """
    Checks if the RTDOSE file actually contains dose data.
    """
    errors = []
    import numpy as np
    
    if not hasattr(rtdose_ds, 'PixelData'):
        errors.append("CRITICAL: RTDOSE file has no PixelData.")
        return errors

    if not hasattr(rtdose_ds, 'DoseGridScaling'):
        errors.append("CRITICAL: RTDOSE file missing DoseGridScaling.")
        return errors

    # Check max value
    arr = rtdose_ds.pixel_array
    if np.max(arr) <= 0:
        errors.append("CRITICAL: RTDOSE grid is empty (Max pixel value <= 0).")
        
    return errors

def validate_tps_import(calculated_dvh, reported_dvh, dicom_patient_id, text_metadata, tolerance_gy=5.0):
    """
    Compares Python-calculated metrics vs TPS text file metrics.
    ALSO validates Patient ID consistency.
    """
    warnings = []
    
    # 1. CRITICAL: Check Patient ID
    text_id = text_metadata.get('patient_id', '')
    
    # Normalize IDs (remove spaces/dashes for comparison)
    norm_text_id = str(text_id).strip().replace(' ', '').replace('-', '').lower()
    norm_dicom_id = str(dicom_patient_id).strip().replace(' ', '').replace('-', '').lower()
    
    if norm_text_id and norm_dicom_id:
        if norm_text_id != norm_dicom_id:
            warnings.append(
                f"CRITICAL: Patient ID Mismatch! DICOM: '{dicom_patient_id}' vs Text File: '{text_id}'"
            )

    # 2. QA Check: Dose Discrepancies
    for organ, tps_data in reported_dvh.items():
        if organ not in calculated_dvh:
            continue
            
        calc_data = calculated_dvh[organ]
        
        metrics_to_check = {
            'D2cc': 'd2cc_gy_per_fraction',
            'D90': 'd90_gy_per_fraction'
        }
        
        for label, key in metrics_to_check.items():
            if key not in tps_data or key not in calc_data: continue
                
            val_tps = tps_data.get(key, 0.0)
            val_calc = calc_data.get(key, 0.0)
            
            if val_tps == 0 and val_calc == 0: continue

            diff = abs(val_tps - val_calc)
            if diff > tolerance_gy:
                warnings.append(
                    f"QA Mismatch [{organ} {label}]: TPS {val_tps:.2f} Gy vs Calc {val_calc:.2f} Gy. (Diff {diff:.2f})"
                )
                
    return warnings

def generate_validation_dataframe(dicom_results, text_results, patient_id):
    """
    Generates a pandas DataFrame comparing DICOM vs TPS Text metrics.
    Does NOT save to file (UI handles saving).
    """
    rows = []
    
    metrics_map = {
        'volume_cc': 'Volume (cc)',
        'd2cc_gy_per_fraction': 'D2cc (Gy)',
        'd1cc_gy_per_fraction': 'D1cc (Gy)',
        'd0_1cc_gy_per_fraction': 'D0.1cc (Gy)',
        'd90_gy_per_fraction': 'D90 (Gy)',
        'd98_gy_per_fraction': 'D98 (Gy)',
    }

    for organ_name, tps_data in text_results.items():
        dicom_data = dicom_results.get(organ_name)
        
        if not dicom_data:
            continue # Skip unmatched organs for cleanliness

        for metric_key, metric_label in metrics_map.items():
            val_text = tps_data.get(metric_key, 0.0)
            val_dicom = dicom_data.get(metric_key, 0.0)
            
            if val_text < 0.001 and val_dicom < 0.001:
                continue

            diff = val_dicom - val_text
            pct_diff = (diff / val_text * 100.0) if val_text != 0 else 0.0

            rows.append({
                'PatientID': patient_id, # Crucial for aggregation
                'Structure': organ_name,
                'Metric': metric_label,
                'TPS_Text': round(val_text, 3),
                'Calc_DICOM': round(val_dicom, 3),
                'Diff': round(diff, 3),
                'Pct_Diff': round(pct_diff, 2)
            })

    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame() # Return empty if no data