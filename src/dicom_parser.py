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
    """
    Safely extracts dose grid, scaling factor, and position data from an RTDOSE file.
    Returns None for all values if essential tags are missing or the file is invalid.
    """
    if not rtdose_file:
        return None, None, None, None, None, None
    try:
        ds = pydicom.dcmread(rtdose_file)
        
        # The most critical check: does the file contain a dose grid?
        if 'PixelData' not in ds:
            print(f"Warning: RTDOSE file {rtdose_file} is missing the PixelData tag. Cannot process dose.")
            return None, None, None, None, None, None

        dose_grid = ds.pixel_array
        dose_scaling = ds.DoseGridScaling
        image_position = ds.ImagePositionPatient
        pixel_spacing = ds.PixelSpacing
        grid_offsets = ds.GridFrameOffsetVector
        orientation = ds.ImageOrientationPatient
        
        return dose_grid, dose_scaling, image_position, pixel_spacing, grid_offsets, orientation
        
    except (AttributeError, KeyError, Exception) as e:
        print(f"Error processing RTDOSE file {rtdose_file}. It may be incomplete or corrupt. Error: {e}")
        return None, None, None, None, None, None

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

    # Get Plan Date and Time
    plan_data['plan_date'] = getattr(ds, 'RTPlanDate', 'N/A')
    plan_data['plan_time'] = getattr(ds, 'RTPlanTime', 'N/A')
    
    # Get Source Information
    plan_data['source_info'] = 'N/A'
    plan_data['rakr'] = 0.0
    plan_data['source_strength_ref_date'] = 'N/A'
    plan_data['source_strength_ref_time'] = 'N/A'
    if hasattr(ds, 'SourceSequence') and len(ds.SourceSequence) > 0:
        source = ds.SourceSequence[0]
        if hasattr(source, 'ReferenceAirKermaRate'):
            rakr = float(source.ReferenceAirKermaRate)
            plan_data['source_info'] = f"{rakr:.2f} cGy cm^2/hr"
            plan_data['rakr'] = rakr
        plan_data['source_strength_ref_date'] = getattr(source, 'SourceStrengthReferenceDate', 'N/A')
        plan_data['source_strength_ref_time'] = getattr(source, 'SourceStrengthReferenceTime', 'N/A')

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
        unnamed_point_counter = 1
        for dr in ds.DoseReferenceSequence:
            point_name = getattr(dr, 'DoseReferenceDescription', '').strip()
            if not point_name or point_name == '-':
                point_name = f"Unnamed Point {unnamed_point_counter}"
                unnamed_point_counter += 1
            
            plan_data['dose_references'].append({
                'name': point_name,
                'dose': dr.TargetPrescriptionDose
            })

    # Get Prescription Points for Cylinder Plans
    plan_data['prescription_points'] = []
    if hasattr(ds, 'BrachyApplicationSetupSequence') and len(ds.BrachyApplicationSetupSequence) > 0:
        if getattr(ds.BrachyApplicationSetupSequence[0], 'ApplicationSetupType', '') == 'VAGINAL':
            if hasattr(ds, 'DoseReferenceSequence'):
                for dr in ds.DoseReferenceSequence:
                    point_name = dr.DoseReferenceDescription.lower()
                    if any(name in point_name for name in ['tip', 'shoulder', '3cm', '3.5cm', '2cm', '2.5cm']):
                        plan_data['prescription_points'].append({
                            'name': dr.DoseReferenceDescription,
                            'coordinates': dr.DoseReferencePointCoordinates
                        })

    # Get Channel Mapping Data
    plan_data['channel_mapping'] = []
    brachy_app_setup_sequence = ds.get((0x300a, 0x0230))
    if brachy_app_setup_sequence:
        for app_setup in brachy_app_setup_sequence:
            if hasattr(app_setup, 'ChannelSequence'):
                for channel_item in app_setup.ChannelSequence:
                    channel_info = {
                        'channel_number': getattr(channel_item, 'ChannelNumber', 'N/A'),
                        'source_applicator_id': getattr(channel_item, 'SourceApplicatorID', 'N/A'),
                        'source_applicator_type': getattr(channel_item, 'SourceApplicatorType', 'N/A'),
                        'source_position': getattr(channel_item, 'SourcePosition', 'N/A'),
                        'source_dwell_time': getattr(channel_item, 'SourceDwellTime', 'N/A'),
                        'source_dwell_position': getattr(channel_item, 'SourceDwellPosition', 'N/A'),
                        'transfer_tube_number': getattr(channel_item, 'TransferTubeNumber', 'N/A'),
                    }
                    plan_data['channel_mapping'].append(channel_info)

    return plan_data

def get_dose_point_mapping(rtplan_file, point_dose_constraints):
    """
    Parses the RTPLAN file to find dose reference points and maps them to the
    point dose constraints based on naming conventions.
    """
    ds = pydicom.dcmread(rtplan_file)
    mapping = {}

    if "DoseReferenceSequence" not in ds:
        return mapping

    for dose_ref in ds.DoseReferenceSequence:
        if "DoseReferenceDescription" in dose_ref:
            dicom_point_name = dose_ref.DoseReferenceDescription.lower()
            
            cylinder_point_keywords = ['tip', 'shoulder', '3cm', '3.5cm', '2cm', '2.5cm']
            if any(keyword in dicom_point_name for keyword in cylinder_point_keywords):
                mapping[dose_ref.DoseReferenceDescription] = "Prescription Point"
                continue

            rv_point_keywords = ['rv', 'rv point', 'rv pt']
            if any(keyword in dicom_point_name for keyword in rv_point_keywords):
                mapping[dose_ref.DoseReferenceDescription] = "RV Point"
                continue

            exact_match_found = False
            for constraint_name in point_dose_constraints.keys():
                if dicom_point_name == constraint_name.lower():
                    mapping[dose_ref.DoseReferenceDescription] = constraint_name
                    exact_match_found = True
                    break
            
            if not exact_match_found:
                for constraint_name in point_dose_constraints.keys():
                    if constraint_name.lower() in dicom_point_name:
                        mapping[dose_ref.DoseReferenceDescription] = constraint_name
                        break
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

def get_dwell_times_and_positions(rtplan_file):
    """
    Calculates the dwell times and positions from a DICOM RT Plan file.
    """
    plan = pydicom.dcmread(rtplan_file)
    dwell_data = []

    brachy_app_setup_sequence = plan.get((0x300a, 0x0230))
    if not brachy_app_setup_sequence or not hasattr(brachy_app_setup_sequence[0], 'ChannelSequence'):
        return dwell_data

    for channel in brachy_app_setup_sequence[0].ChannelSequence:
        channel_total_time = float(channel.ChannelTotalTime)
        final_cumulative_time_weight = float(channel.FinalCumulativeTimeWeight)
        
        if final_cumulative_time_weight == 0:
            continue

        control_points = channel.BrachyControlPointSequence
        
        for i in range(1, len(control_points)):
            dwell_time_weight = float(control_points[i].CumulativeTimeWeight) - float(control_points[i-1].CumulativeTimeWeight)
            
            if dwell_time_weight > 0:
                dwell_time = dwell_time_weight * channel_total_time / final_cumulative_time_weight
                position = float(control_points[i].ControlPointRelativePosition)
                dwell_data.append({"position": position, "dwell_time": dwell_time})
    return dwell_data

# The 'if __name__ == "__main__":' block and its import have been removed as 
# they are for direct script execution and testing, which is not needed in the final application.