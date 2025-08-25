import numpy as np
import pydicom
from dicompylercore import dvhcalc
# from .config import alpha_beta_ratios, constraints # No longer needed as they are passed or accessed via templates
import os
import contextlib
import re

def normalize_structure_name(name):
    """Normalizes structure names for consistent matching."""
    # Remove content in brackets (e.g., [cm3]) or parentheses
    name = re.sub(r'\s*\[.*?\]', '', name)
    name = re.sub(r'\s*\(.*?\)', '', name)
    # Convert to lowercase, strip whitespace, and then capitalize the first letter
    return name.strip().lower().capitalize()

def calculate_contour_volumes(rtstruct_file, structure_data):
    """Calculates the volume of each contour in an RTSTRUCT file."""
    ds = pydicom.dcmread(rtstruct_file)
    volumes = {}
    for roi_contour, structure_set_roi in zip(ds.ROIContourSequence, ds.StructureSetROISequence):
        name = structure_set_roi.ROIName
        normalized_name = normalize_structure_name(name)
        if not hasattr(roi_contour, 'ContourSequence') or not roi_contour.ContourSequence:
            volumes[normalized_name] = 0
            continue
        slices_by_z = {}
        for contour_slice in roi_contour.ContourSequence:
            points = np.array(contour_slice.ContourData).reshape((-1, 3))
            z = round(points[0, 2], 4)
            if z not in slices_by_z:
                slices_by_z[z] = []
            slices_by_z[z].append(points[:, :2])
        sorted_z = sorted(slices_by_z.keys())
        total_volume_mm3 = 0
        if len(sorted_z) > 1:
            for i in range(len(sorted_z) - 1):
                z1, z2 = sorted_z[i], sorted_z[i+1]
                area1 = sum(0.5 * np.abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1))) for p in slices_by_z[z1])
                area2 = sum(0.5 * np.abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1))) for p in slices_by_z[z2])
                slice_thickness = abs(z1 - z2)
                total_volume_mm3 += (area1 + area2) / 2.0 * slice_thickness
        volumes[normalized_name] = total_volume_mm3 / 1000.0
    return volumes

def get_dose_at_point(dose_grid, dose_scaling, image_position_patient, pixel_spacing, grid_frame_offset_vector, point_coordinates):
    """Calculates the dose at a specific 3D point within the dose grid."""
    if dose_grid is None or not point_coordinates:
        return 0.0

    # Extract point coordinates
    point_x, point_y, point_z = point_coordinates

    # Extract dose grid origin and spacing
    origin_x, origin_y, origin_z = image_position_patient
    spacing_x, spacing_y = pixel_spacing

    # Determine z-spacing from GridFrameOffsetVector
    # Assuming uniform z-spacing for simplicity, or handling non-uniform if necessary
    if len(grid_frame_offset_vector) > 1:
        spacing_z = grid_frame_offset_vector[1] - grid_frame_offset_vector[0]
    else:
        # If only one slice, assume a default z-spacing or handle as error
        # For now, let's assume a reasonable default if only one slice is present
        # This might need to be refined based on actual DICOM data characteristics
        spacing_z = 1.0 # Placeholder, ideally this should be derived or provided

    # Convert patient coordinates to voxel coordinates
    voxel_x = (point_x - origin_x) / spacing_x
    voxel_y = (point_y - origin_y) / spacing_y
    voxel_z = (point_z - grid_frame_offset_vector[0]) / spacing_z

    # Round to nearest integer for nearest-neighbor interpolation
    idx_x = int(round(voxel_x))
    idx_y = int(round(voxel_y))
    idx_z = int(round(voxel_z))

    # Check for out-of-bounds
    if not (0 <= idx_x < dose_grid.shape[2] and
            0 <= idx_y < dose_grid.shape[1] and
            0 <= idx_z < dose_grid.shape[0]):
        return 0.0

    # Get dose value and apply scaling
    dose_value = dose_grid[idx_z, idx_y, idx_x] * dose_scaling
    return dose_value

def calculate_d_volume(dvh, volume_cc):
    """Calculates the dose to a specific volume from a DVH object."""
    if dvh is None or dvh.volume == 0:
        return 0.0

    # Get the cumulative DVH data
    cumulative_dvh = dvh.cumulative.counts
    dose_bins = dvh.bincenters

    # Find the dose at the specified volume
    for i, vol in enumerate(cumulative_dvh):
        if vol <= volume_cc:
            if i == 0:
                return dose_bins[0]
            else:
                # Interpolate between the two nearest points
                x1 = cumulative_dvh[i-1]
                x2 = cumulative_dvh[i]
                y1 = dose_bins[i-1]
                y2 = dose_bins[i]
                return y1 + (volume_cc - x1) * (y2 - y1) / (x2 - x1)

    return 0.0


# This file will contain the logic for dose-volume calculations.

def calculate_bed_and_eqd2(total_dose, dose_per_fraction, organ_name, ebrt_dose=0, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates BED and EQD2 for a given total dose and dose per fraction, with an optional EBRT dose."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"] # Fallback to default template

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    
    # Calculate BED for brachytherapy
    bed_brachy = total_dose * (1 + (dose_per_fraction / alpha_beta))
    
    # Calculate BED for EBRT
    bed_ebrt = ebrt_dose * (1 + (2 / alpha_beta)) # Assuming 2 Gy/fraction for EBRT

    # Total BED
    total_bed = bed_brachy + bed_ebrt + previous_brachy_bed
    
    # Calculate total EQD2
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2), round(bed_brachy, 2), round(bed_ebrt, 2), round(previous_brachy_bed, 2)

def calculate_dose_to_meet_constraint(eqd2_constraint, organ_name, number_of_fractions, ebrt_dose=0, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates the brachytherapy dose per fraction needed to meet a specific EQD2 constraint."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"] # Fallback to default template

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])

    # Convert EQD2 constraint back to total BED target
    k_factor = (1 + (2 / alpha_beta))
    total_bed_target = eqd2_constraint * k_factor

    # Calculate BED from EBRT
    bed_ebrt = ebrt_dose * k_factor

    # BED from previous brachytherapy is already in BED
    bed_previous_brachy = previous_brachy_bed

    # Remaining BED needed from brachytherapy
    bed_brachy_needed = total_bed_target - bed_ebrt - bed_previous_brachy

    # Solve quadratic equation for dose_per_fraction (D_f)
    # a * D_f^2 + b * D_f + c = 0
    # where bed_brachy_needed = N * D_f + (N / alpha_beta) * D_f^2
    a = number_of_fractions / alpha_beta
    b = number_of_fractions
    c = -bed_brachy_needed

    discriminant = b**2 - 4*a*c

    if discriminant < 0:
        return None # No real solution, constraint cannot be met with brachytherapy
    
    # We are looking for a positive dose, so we take the positive root
    dose_per_fraction_solution = (-b + np.sqrt(discriminant)) / (2*a)

    if dose_per_fraction_solution < 0:
        return None # Negative dose is not physically meaningful

    return round(dose_per_fraction_solution, 2)

def calculate_point_dose_bed_eqd2(point_dose, number_of_fractions, organ_name, ebrt_dose=0, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates BED and EQD2 for a given point dose."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"] # Fallback to default template

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    
    total_dose = point_dose * number_of_fractions

    # Calculate BED for brachytherapy
    bed_brachy = total_dose * (1 + (point_dose / alpha_beta))
    
    # Calculate BED for EBRT
    bed_ebrt = ebrt_dose * (1 + (1.8 / alpha_beta)) # Assuming 1.8 Gy/fraction for EBRT

    # BED from previous brachytherapy is already in BED
    bed_previous_brachy = previous_brachy_bed
    
    # Total BED
    total_bed = bed_brachy + bed_ebrt + bed_previous_brachy
    
    # Calculate total EQD2
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2), round(bed_brachy, 2), round(bed_ebrt, 2), round(bed_previous_brachy, 2)

def get_dvh(rtss_file, rtdose_file, structure_data, number_of_fractions, ebrt_dose=0, previous_brachy_bed_per_organ=None, alpha_beta_ratios=None):
    """Calculates the Dose-Volume Histogram (DVH) for each structure."""
    if previous_brachy_bed_per_organ is None:
        previous_brachy_bed_per_organ = {}
    dvh_results = {}

    # Calculate all volumes using our custom function once
    all_calculated_volumes = calculate_contour_volumes(rtss_file, structure_data)

    for name, data in structure_data.items():
        normalized_name = normalize_structure_name(name)
        organ_volume_cc = all_calculated_volumes.get(normalized_name, 0.0)

        # The rest of the DVH calculation still relies on dicompyler-core for D2cc, D1cc, D0.1cc
        # We will still use dvhcalc for dose metrics, but not for volume
        roi_number = data["ROINumber"]
        try:
            dvh = dvhcalc.get_dvh(rtss_file, rtdose_file, roi_number)

            d2cc_gy_per_fraction = getattr(dvh, 'D2cc', 0.0)
            if hasattr(d2cc_gy_per_fraction, 'value'):
                d2cc_gy_per_fraction = d2cc_gy_per_fraction.value

            d1cc_gy_per_fraction = getattr(dvh, 'D1cc', 0.0)
            if hasattr(d1cc_gy_per_fraction, 'value'):
                d1cc_gy_per_fraction = d1cc_gy_per_fraction.value

            d0_1cc_gy_per_fraction = calculate_d_volume(dvh, 0.1)
            
            max_dose_gy_per_fraction = getattr(dvh, 'max', 0.0)
            if hasattr(max_dose_gy_per_fraction, 'value'):
                max_dose_gy_per_fraction = max_dose_gy_per_fraction.value

            mean_dose_gy_per_fraction = getattr(dvh, 'mean', 0.0)
            if hasattr(mean_dose_gy_per_fraction, 'value'):
                mean_dose_gy_per_fraction = mean_dose_gy_per_fraction.value

            min_dose_gy_per_fraction = getattr(dvh, 'min', 0.0)
            if hasattr(min_dose_gy_per_fraction, 'value'):
                min_dose_gy_per_fraction = min_dose_gy_per_fraction.value

            d95_gy_per_fraction = getattr(dvh, 'D95', 0.0)
            if hasattr(d95_gy_per_fraction, 'value'):
                d95_gy_per_fraction = d95_gy_per_fraction.value
            
            d98_gy_per_fraction = getattr(dvh, 'D98', 0.0)
            if hasattr(d98_gy_per_fraction, 'value'):
                d98_gy_per_fraction = d98_gy_per_fraction.value

            d90_gy_per_fraction = getattr(dvh, 'D90', 0.0)
            if hasattr(d90_gy_per_fraction, 'value'):
                d90_gy_per_fraction = d90_gy_per_fraction.value

        except Exception as e:
            print(f"Warning: Could not calculate DVH for {name} (ROI Number: {roi_number}). Error: {e}")
            d2cc_gy_per_fraction = 0.0
            d1cc_gy_per_fraction = 0.0
            d0_1cc_gy_per_fraction = 0.0
            max_dose_gy_per_fraction = 0.0
            mean_dose_gy_per_fraction = 0.0
            min_dose_gy_per_fraction = 0.0
            d95_gy_per_fraction = 0.0
            d98_gy_per_fraction = 0.0
            d90_gy_per_fraction = 0.0

        # Calculations for D2cc
        total_d2cc_gy = d2cc_gy_per_fraction * number_of_fractions
        bed_d2cc, eqd2_d2cc, bed_brachy_d2cc, bed_ebrt, bed_previous_brachy = calculate_bed_and_eqd2(
            total_d2cc_gy, d2cc_gy_per_fraction, normalized_name, ebrt_dose, previous_brachy_bed=previous_brachy_bed_per_organ.get(normalized_name, {}).get("d2cc", 0), alpha_beta_ratios=alpha_beta_ratios
        )

        # Calculations for D1cc
        total_d1cc_gy = d1cc_gy_per_fraction * number_of_fractions
        bed_d1cc, eqd2_d1cc, _, _, _ = calculate_bed_and_eqd2(
            total_d1cc_gy, d1cc_gy_per_fraction, normalized_name, ebrt_dose, previous_brachy_bed=previous_brachy_bed_per_organ.get(normalized_name, {}).get("d1cc", 0), alpha_beta_ratios=alpha_beta_ratios
        )

        # Calculations for D0.1cc
        total_d0_1cc_gy = d0_1cc_gy_per_fraction * number_of_fractions
        bed_d0_1cc, eqd2_d0_1cc, _, _, _ = calculate_bed_and_eqd2(
            total_d0_1cc_gy, d0_1cc_gy_per_fraction, normalized_name, ebrt_dose, previous_brachy_bed=previous_brachy_bed_per_organ.get(normalized_name, {}).get("d0_1cc", 0), alpha_beta_ratios=alpha_beta_ratios
        )

        dvh_results[normalized_name] = {
            "volume_cc": round(organ_volume_cc, 2),
            "d2cc_gy_per_fraction": round(d2cc_gy_per_fraction, 2),
            "d1cc_gy_per_fraction": round(d1cc_gy_per_fraction, 2),
            "d0_1cc_gy_per_fraction": round(d0_1cc_gy_per_fraction, 2),
            "max_dose_gy_per_fraction": round(max_dose_gy_per_fraction, 2),
            "mean_dose_gy_per_fraction": round(mean_dose_gy_per_fraction, 2),
            "min_dose_gy_per_fraction": round(min_dose_gy_per_fraction, 2),
            "d95_gy_per_fraction": round(d95_gy_per_fraction, 2),
            "d98_gy_per_fraction": round(d98_gy_per_fraction, 2),
            "d90_gy_per_fraction": round(d90_gy_per_fraction, 2),
            "total_d2cc_gy": round(total_d2cc_gy, 2),
            "bed_d2cc": bed_d2cc,
            "eqd2_d2cc": eqd2_d2cc,
            "bed_d1cc": bed_d1cc,
            "eqd2_d1cc": eqd2_d1cc,
            "bed_d0_1cc": bed_d0_1cc,
            "eqd2_d0_1cc": eqd2_d0_1cc,
            "bed_this_plan": bed_brachy_d2cc, # Assuming this is tied to D2cc
            "bed_ebrt": bed_ebrt,
            "bed_previous_brachy": bed_previous_brachy
        }

    return dvh_results

def evaluate_constraints(dvh_results, point_dose_results, constraints=None, point_dose_constraints=None, dose_point_mapping=None):
    """Evaluates calculated DVH and point dose results against predefined constraints."""
    if constraints is None:
        from .config import templates
        constraints = templates["Cervix HDR - EMBRACE II"]["constraints"]
    if point_dose_constraints is None:
        from .config import templates
        point_dose_constraints = templates["Cervix HDR - EMBRACE II"]["point_dose_constraints"]
    if dose_point_mapping is None:
        dose_point_mapping = {}

    constraint_evaluation = {}
    for organ, data in dvh_results.items():
        evaluation = {}
        
        normalized_organ = normalize_structure_name(organ)

        if normalized_organ in constraints and "D2cc" in constraints[normalized_organ]:
            constraint_data = constraints[normalized_organ]["D2cc"]
            max_eqd2 = constraint_data["max"]
            warning_eqd2 = constraint_data.get("warning")
            
            current_eqd2 = data["eqd2_d2cc"]
            
            evaluation["EQD2_value"] = current_eqd2
            evaluation["EQD2_max"] = max_eqd2
            evaluation["EQD2_warning"] = warning_eqd2

            if current_eqd2 <= max_eqd2:
                evaluation["EQD2_met"] = "True"
                if warning_eqd2 is not None and current_eqd2 > warning_eqd2:
                    evaluation["EQD2_status"] = "Warning"
                else:
                    evaluation["EQD2_status"] = "Met"
            else:
                evaluation["EQD2_met"] = "False"
                evaluation["EQD2_status"] = "NOT Met"
            
            constraint_evaluation[normalized_organ] = evaluation

        if "HRCTV D90" in constraints and normalized_organ == "Hrctv":
            constraint_data = constraints["HRCTV D90"]
            min_eqd2 = constraint_data["min"]
            max_eqd2 = constraint_data.get("max")
            
            current_eqd2 = data["eqd2_d90"]
            
            evaluation["EQD2_value_D90"] = current_eqd2
            evaluation["EQD2_min_D90"] = min_eqd2
            evaluation["EQD2_max_D90"] = max_eqd2

            is_met = current_eqd2 >= min_eqd2
            if max_eqd2 is not None:
                is_met = is_met and current_eqd2 <= max_eqd2
            
            evaluation["EQD2_met_D90"] = str(is_met)
            evaluation["EQD2_status_D90"] = "Met" if is_met else "NOT Met"
            constraint_evaluation["HRCTV D90"] = evaluation

        if "HRCTV D98" in constraints and normalized_organ == "Hrctv":
            constraint_data = constraints["HRCTV D98"]
            min_eqd2 = constraint_data["min"]
            
            current_eqd2 = data["eqd2_d98"]
            
            evaluation["EQD2_value_D98"] = current_eqd2
            evaluation["EQD2_min_D98"] = min_eqd2

            is_met = current_eqd2 >= min_eqd2
            
            evaluation["EQD2_met_D98"] = str(is_met)
            evaluation["EQD2_status_D98"] = "Met" if is_met else "NOT Met"
            constraint_evaluation["HRCTV D98"] = evaluation

        if "GTV D98" in constraints and normalized_organ == "Gtv":
            constraint_data = constraints["GTV D98"]
            min_eqd2 = constraint_data["min"]
            
            current_eqd2 = data["eqd2_d98"]
            
            evaluation["EQD2_value_D98"] = current_eqd2
            evaluation["EQD2_min_D98"] = min_eqd2

            is_met = current_eqd2 >= min_eqd2
            
            evaluation["EQD2_met_D98"] = str(is_met)
            evaluation["EQD2_status_D98"] = "Met" if is_met else "NOT Met"
            constraint_evaluation["GTV D98"] = evaluation

    for point_dose in point_dose_results:
        point_name = point_dose['name']
        if point_name in dose_point_mapping:
            constraint_name = dose_point_mapping[point_name]
            if constraint_name in point_dose_constraints:
                constraint = point_dose_constraints[constraint_name]
                if not constraint.get('report_only', False):
                    max_eqd2 = constraint.get('max_eqd2')
                    if max_eqd2 is not None:
                        current_eqd2 = point_dose['EQD2']
                        status = "Met" if current_eqd2 <= max_eqd2 else "NOT Met"
                        constraint_evaluation[f"Point Dose - {point_name}"] = {
                            "status": status,
                            "EQD2_value": current_eqd2,
                            "EQD2_max": max_eqd2
                        }

    return constraint_evaluation