import pydicom
from pathlib import Path

def find_dicom_file(directory):
    """Finds the first DICOM file in a directory."""
    files = list(Path(directory).rglob("*.dcm"))
    if files:
        return str(files[0])
    return None

def load_dicom_file(file_path):
    """Loads a single DICOM file."""
    try:
        return pydicom.dcmread(file_path)
    except Exception as e:
        print(f"Error loading DICOM file {file_path}: {e}")
        return None

def get_dicom_files(directory):
    """Finds all DICOM files in a directory."""
    return list(Path(directory).rglob("*.dcm"))

def verify_patient_consistency(dicom_files):
    """Verifies that all DICOM files belong to the same patient."""
    if not dicom_files:
        return True, None

    first_patient_id = pydicom.dcmread(dicom_files[0]).PatientID
    for f in dicom_files[1:]:
        patient_id = pydicom.dcmread(f).PatientID
        if patient_id != first_patient_id:
            return False, (first_patient_id, patient_id)
    return True, first_patient_id

def sort_dicom_files(dicom_files):
    """Sorts DICOM files by modality (RTDOSE, RTPLAN, RTSTRUCT)."""
    sorted_files = {
        "RTDOSE": None,
        "RTPLAN": None,
        "RTSTRUCT": None,
    }
    for f in dicom_files:
        modality = pydicom.dcmread(f).Modality
        if modality in sorted_files:
            sorted_files[modality] = f
    return sorted_files

def get_structure_data(rtstruct_dataset):
    """Extracts ROI names and contour data from an RTSTRUCT file."""
    if not rtstruct_dataset:
        return {}
    structures = {}
    for roi_contour, structure_set_roi in zip(rtstruct_dataset.ROIContourSequence, rtstruct_dataset.StructureSetROISequence):
        structures[structure_set_roi.ROIName] = {
            "ROINumber": structure_set_roi.ROINumber,
            "ContourData": [contour.ContourData for contour in roi_contour.ContourSequence]
        }
    return structures

def get_dose_data(rtdose_file):
    """Extracts dose grid, scaling factor, and position data from an RTDOSE file."""
    if not rtdose_file:
        return None, None, None, None, None, None
    ds = pydicom.dcmread(rtdose_file)
    return ds.pixel_array, ds.DoseGridScaling, ds.ImagePositionPatient, ds.PixelSpacing, ds.GridFrameOffsetVector, ds.ImageOrientationPatient

def get_plan_data(rtplan_file):
    """Extracts prescription data from an RTPLAN file."""
    if not rtplan_file:
        return {}
    ds = pydicom.dcmread(rtplan_file)
    plan_data = {}

    # Get Plan Name
    plan_name = 'N/A'
    if hasattr(ds, 'RTPlanLabel') and ds.RTPlanLabel:
        plan_name = ds.RTPlanLabel
    elif hasattr(ds, 'RTPlanName') and ds.RTPlanName:
        plan_name = ds.RTPlanName
    elif hasattr(ds, 'SeriesDescription') and ds.SeriesDescription:
        plan_name = ds.SeriesDescription
    plan_data['plan_name'] = plan_name

    # Get Number of Fractions and Dose per Fraction
    if hasattr(ds, 'FractionGroupSequence') and len(ds.FractionGroupSequence) > 0:
        fraction_group = ds.FractionGroupSequence[0]
        plan_data['number_of_fractions'] = int(getattr(fraction_group, 'NumberOfFractionsPlanned', 1))
        if hasattr(fraction_group, 'ReferencedBrachyApplicationSetupSequence') and len(fraction_group.ReferencedBrachyApplicationSetupSequence) > 0:
            brachy_setup = fraction_group.ReferencedBrachyApplicationSetupSequence[0]
            plan_data['brachy_dose_per_fraction'] = float(getattr(brachy_setup, 'BrachyApplicationSetupDose', 0.0))
        else:
            plan_data['brachy_dose_per_fraction'] = 0.0
    else:
        plan_data['number_of_fractions'] = 1
        plan_data['brachy_dose_per_fraction'] = 0.0

    # Get Dose Reference Data
    plan_data['dose_references'] = []
    if hasattr(ds, 'DoseReferenceSequence'):
        for dr in ds.DoseReferenceSequence:
            plan_data['dose_references'].append({
                'name': dr.DoseReferenceDescription,
                'dose': dr.TargetPrescriptionDose
            })

    return plan_data

def get_dose_point_mapping(rtplan_file, point_dose_constraints):
    """
    Parses the RTPLAN file to find dose reference points and maps them to the
    point dose constraints based on naming conventions.

    Args:
        rtplan_file (str): The path to the RTPLAN DICOM file.
        point_dose_constraints (dict): The dictionary of point dose constraints from the config.

    Returns:
        dict: A dictionary mapping the DICOM dose reference description to the
              corresponding key in the point_dose_constraints dictionary.
    """
    ds = pydicom.dcmread(rtplan_file)
    mapping = {}

    if "DoseReferenceSequence" not in ds:
        return mapping

    for dose_ref in ds.DoseReferenceSequence:
        if "DoseReferenceDescription" in dose_ref:
            dicom_point_name = dose_ref.DoseReferenceDescription.lower()
            # First, try to find an exact match (case-insensitive)
            exact_match_found = False
            for constraint_name in point_dose_constraints.keys():
                if dicom_point_name == constraint_name.lower():
                    mapping[dose_ref.DoseReferenceDescription] = constraint_name
                    exact_match_found = True
                    break
            
            # If no exact match, then try substring matching
            if not exact_match_found:
                for constraint_name in point_dose_constraints.keys():
                    if constraint_name.lower() in dicom_point_name:
                        mapping[dose_ref.DoseReferenceDescription] = constraint_name
                        break  # Move to the next dose reference once a match is found

    return mapping

def get_control_point_data(rtplan_file):
    """Extracts control point data from an RTPLAN file."""
    if not rtplan_file:
        return []
    ds = pydicom.dcmread(rtplan_file)
    control_points = []
    if hasattr(ds, 'BrachyApplicationSetupSequence'):
        for app_setup in ds.BrachyApplicationSetupSequence:
            if hasattr(app_setup, 'BrachyControlPointSequence'):
                for cp in app_setup.BrachyControlPointSequence:
                    control_points.append({
                        'position': cp.ControlPoint3DPosition,
                        'dose': cp.ControlPointCumulativeTimeWeight
                    })
    return control_points

from .calculations import get_dvh

if __name__ == "__main__":
    # Example usage:
    dicom_dir = "."
    all_files = get_dicom_files(dicom_dir)
    is_consistent, patient_ids = verify_patient_consistency(all_files)
    if is_consistent:
        print(f"All files belong to patient: {patient_ids}")
        sorted_files = sort_dicom_files(all_files)
        print("Sorted files:", sorted_files)
        structure_data = get_structure_data(sorted_files.get("RTSTRUCT"))
        if structure_data:
            print("\n--- Structure Data ---")
            for name, data in structure_data.items():
                print(f"ROI: {name}, ROINumber: {data['ROINumber']}, Contours: {len(data['ContourData'])}")

        dose_grid, dose_scaling, image_position, pixel_spacing, grid_frame_offset_vector, image_orientation = get_dose_data(sorted_files.get("RTDOSE"))
        if dose_grid is not None:
            print("\n--- Dose Data ---")
            print(f"Dose grid shape: {dose_grid.shape}")
            print(f"Dose scaling factor: {dose_scaling}")
            print(f"Image Position (Patient): {image_position}")
            print(f"Pixel Spacing: {pixel_spacing}")
            print(f"Grid Frame Offset Vector: {grid_frame_offset_vector}")
            print(f"Image Orientation (Patient): {image_orientation}")

        plan_data = get_plan_data(sorted_files.get("RTPLAN"))
        if plan_data:
            print("\n--- Plan Data ---")
            print(f"Plan Name: {plan_data.get('plan_name', 'N/A')}")
            print(f"Number of Fractions: {plan_data.get('number_of_fractions', 'N/A')}")
            print(f"Brachy Dose per Fraction: {plan_data.get('brachy_dose_per_fraction', 'N/A')}")

        dvh_results = get_dvh(structure_data, dose_grid, dose_scaling, image_position, pixel_spacing, grid_frame_offset_vector, plan_data.get('number_of_fractions', 1), image_orientation)
        if dvh_results:
            print("\n--- DVH Results ---")
            for name, data in dvh_results.items():
                print(f"Structure: {name}, Volume: {data['volume_cc']} cc, D2cc/fx: {data['d2cc_gy_per_fraction']} Gy, Total D2cc: {data['total_d2cc_gy']} Gy")
    else:
        print(f"Error: Mismatched patient IDs: {patient_ids[0]} vs {patient_ids[1]}")
