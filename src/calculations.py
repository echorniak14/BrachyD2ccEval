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
    if len(grid_frame_offset_vector) > 1:
        spacing_z = grid_frame_offset_vector[1] - grid_frame_offset_vector[0]
    else:
        spacing_z = 1.0 # Placeholder

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

    cumulative_dvh = dvh.cumulative.counts
    dose_bins = dvh.bincenters

    for i, vol in enumerate(cumulative_dvh):
        if vol <= volume_cc:
            if i == 0:
                return dose_bins[0]
            else:
                x1, x2 = cumulative_dvh[i-1], cumulative_dvh[i]
                y1, y2 = dose_bins[i-1], dose_bins[i]
                return y1 + (volume_cc - x1) * (y2 - y1) / (x2 - x1)
    return 0.0

def calculate_bed_and_eqd2(total_dose, dose_per_fraction, organ_name, ebrt_dose=0, ebrt_fractions=1, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates BED and EQD2 for a given total dose and dose per fraction, with an optional EBRT dose."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    
    bed_brachy = total_dose * (1 + (dose_per_fraction / alpha_beta))
    bed_ebrt = ebrt_dose * (1 + (2 / alpha_beta))
    total_bed = bed_brachy + bed_ebrt + previous_brachy_bed
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2), round(bed_brachy, 2), round(bed_ebrt, 2), round(previous_brachy_bed, 2)

def calculate_dose_to_meet_constraint(eqd2_constraint, organ_name, number_of_fractions, ebrt_dose=0, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates the brachytherapy dose per fraction needed to meet a specific EQD2 constraint."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    k_factor = (1 + (2 / alpha_beta))
    total_bed_target = eqd2_constraint * k_factor
    bed_ebrt = ebrt_dose * k_factor
    bed_brachy_needed = total_bed_target - bed_ebrt - previous_brachy_bed

    a = number_of_fractions / alpha_beta
    b = number_of_fractions
    c = -bed_brachy_needed
    discriminant = b**2 - 4*a*c

    if discriminant < 0:
        return None
    
    dose_per_fraction_solution = (-b + np.sqrt(discriminant)) / (2*a)

    if dose_per_fraction_solution < 0:
        return None

    return round(dose_per_fraction_solution, 2)

def calculate_point_dose_bed_eqd2(point_dose, number_of_fractions, organ_name, ebrt_dose=0, ebrt_fractions=1, previous_brachy_bed=0, alpha_beta_ratios=None):
    """Calculates BED and EQD2 for a given point dose."""
    if alpha_beta_ratios is None:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]

    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    total_dose = point_dose * number_of_fractions
    bed_brachy = total_dose * (1 + (point_dose / alpha_beta))
    bed_ebrt = ebrt_dose * (1 + (2 / alpha_beta))
    total_bed = bed_brachy + bed_ebrt + previous_brachy_bed
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2), round(bed_brachy, 2), round(bed_ebrt, 2), round(previous_brachy_bed, 2)

def get_dvh(rtss_file, rtdose_file, structure_data, number_of_fractions, ebrt_dose=0, ebrt_fractions=1, previous_brachy_bed_per_organ=None, alpha_beta_ratios=None):
    """Calculates the Dose-Volume Histogram (DVH) for each structure."""
    if previous_brachy_bed_per_organ is None:
        previous_brachy_bed_per_organ = {}
    dvh_results = {}

    all_calculated_volumes = calculate_contour_volumes(rtss_file, structure_data)

    for name, data in structure_data.items():
        normalized_name = normalize_structure_name(name)
        organ_volume_cc = all_calculated_volumes.get(normalized_name, 0.0)

        roi_number = data["ROINumber"]
        try:
            dvh = dvhcalc.get_dvh(rtss_file, rtdose_file, roi_number)

            d2cc_gy_per_fraction = getattr(dvh, 'D2cc', 0.0).value if hasattr(getattr(dvh, 'D2cc', 0.0), 'value') else getattr(dvh, 'D2cc', 0.0)
            d1cc_gy_per_fraction = getattr(dvh, 'D1cc', 0.0).value if hasattr(getattr(dvh, 'D1cc', 0.0), 'value') else getattr(dvh, 'D1cc', 0.0)
            d0_1cc_gy_per_fraction = calculate_d_volume(dvh, 0.1)
            max_dose_gy_per_fraction = getattr(dvh, 'max', 0.0).value if hasattr(getattr(dvh, 'max', 0.0), 'value') else getattr(dvh, 'max', 0.0)
            mean_dose_gy_per_fraction = getattr(dvh, 'mean', 0.0).value if hasattr(getattr(dvh, 'mean', 0.0), 'value') else getattr(dvh, 'mean', 0.0)
            min_dose_gy_per_fraction = getattr(dvh, 'min', 0.0).value if hasattr(getattr(dvh, 'min', 0.0), 'value') else getattr(dvh, 'min', 0.0)
            d95_gy_per_fraction = getattr(dvh, 'D95', 0.0).value if hasattr(getattr(dvh, 'D95', 0.0), 'value') else getattr(dvh, 'D95', 0.0)
            d98_gy_per_fraction = getattr(dvh, 'D98', 0.0).value if hasattr(getattr(dvh, 'D98', 0.0), 'value') else getattr(dvh, 'D98', 0.0)
            d90_gy_per_fraction = getattr(dvh, 'D90', 0.0).value if hasattr(getattr(dvh, 'D90', 0.0), 'value') else getattr(dvh, 'D90', 0.0)

        except Exception as e:
            d2cc_gy_per_fraction, d1cc_gy_per_fraction, d0_1cc_gy_per_fraction, max_dose_gy_per_fraction, mean_dose_gy_per_fraction, min_dose_gy_per_fraction, d95_gy_per_fraction, d98_gy_per_fraction, d90_gy_per_fraction = (0.0,) * 9
            
        dvh_results[normalized_name] = {
            'volume_cc': organ_volume_cc, # *** CORRECTED KEY ***
            'd2cc_gy_per_fraction': d2cc_gy_per_fraction,
            'd1cc_gy_per_fraction': d1cc_gy_per_fraction,
            'd0_1cc_gy_per_fraction': d0_1cc_gy_per_fraction,
            'max_dose_gy_per_fraction': max_dose_gy_per_fraction,
            'mean_dose_gy_per_fraction': mean_dose_gy_per_fraction,
            'min_dose_gy_per_fraction': min_dose_gy_per_fraction,
            'd95_gy_per_fraction': d95_gy_per_fraction,
            'd98_gy_per_fraction': d98_gy_per_fraction,
            'd90_gy_per_fraction': d90_gy_per_fraction,
        }
        
    return dvh_results

def evaluate_constraints(dvh_results, point_dose_results, target_constraints=None, oar_constraints=None, point_dose_constraints=None, dose_point_mapping=None):
    """Evaluates calculated DVH and point dose results against predefined constraints."""
    if target_constraints is None:
        from .config import templates
        target_constraints = templates["Cervix HDR - EMBRACE II"]["constraints"]["target_constraints"]
    if oar_constraints is None:
        from .config import templates
        oar_constraints = templates["Cervix HDR - EMBRACE II"]["constraints"]["oar_constraints"]
    if point_dose_constraints is None:
        from .config import templates
        point_dose_constraints = templates["Cervix HDR - EMBRACE II"]["point_dose_constraints"]
    if dose_point_mapping is None:
        dose_point_mapping = {}

    constraint_evaluation = {}
    for organ, data in dvh_results.items():
        evaluation = {}
        normalized_organ = normalize_structure_name(organ)

        if normalized_organ in oar_constraints and "D2cc" in oar_constraints[normalized_organ]:
            constraint_data = oar_constraints[normalized_organ]["D2cc"]
            max_eqd2 = constraint_data["max"]
            warning_eqd2 = constraint_data.get("warning")
            current_eqd2 = data["eqd2_d2cc"]
            evaluation.update({"EQD2_value": current_eqd2, "EQD2_max": max_eqd2, "EQD2_warning": warning_eqd2})
            if current_eqd2 <= max_eqd2:
                evaluation["EQD2_met"], evaluation["EQD2_status"] = ("True", "Warning" if warning_eqd2 and current_eqd2 > warning_eqd2 else "Met")
            else:
                evaluation["EQD2_met"], evaluation["EQD2_status"] = ("False", "NOT Met")
            constraint_evaluation[normalized_organ] = evaluation

        if "Hrctv D90" in target_constraints and normalized_organ == "Hrctv":
            constraint_data = target_constraints["Hrctv D90"]
            min_eqd2, max_eqd2 = constraint_data["min"], constraint_data.get("max")
            current_eqd2 = data["eqd2_d90"]
            evaluation.update({"EQD2_value_D90": current_eqd2, "EQD2_min_D90": min_eqd2, "EQD2_max_D90": max_eqd2})
            is_met = current_eqd2 >= min_eqd2 and (max_eqd2 is None or current_eqd2 <= max_eqd2)
            evaluation.update({"EQD2_met_D90": str(is_met), "EQD2_status_D90": "Met" if is_met else "NOT Met"})
            constraint_evaluation["Hrctv D90"] = evaluation

        if "Hrctv D98" in target_constraints and normalized_organ == "Hrctv":
            constraint_data = target_constraints["Hrctv D98"]
            min_eqd2 = constraint_data["min"]
            current_eqd2 = data["eqd2_d98"]
            evaluation.update({"EQD2_value_D98": current_eqd2, "EQD2_min_D98": min_eqd2})
            is_met = current_eqd2 >= min_eqd2
            evaluation.update({"EQD2_met_D98": str(is_met), "EQD2_status_D98": "Met" if is_met else "NOT Met"})
            constraint_evaluation["Hrctv D98"] = evaluation

        if "Gtv D98" in target_constraints and normalized_organ == "Gtv":
            constraint_data = target_constraints["Gtv D98"]
            min_eqd2 = constraint_data["min"]
            current_eqd2 = data["eqd2_d98"]
            evaluation.update({"EQD2_value_D98": current_eqd2, "EQD2_min_D98": min_eqd2})
            is_met = current_eqd2 >= min_eqd2
            evaluation.update({"EQD2_met_D98": str(is_met), "EQD2_status_D98": "Met" if is_met else "NOT Met"})
            constraint_evaluation["Gtv D98"] = evaluation

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
                        constraint_evaluation[f"Point Dose - {point_name}"] = {"status": status, "EQD2_value": current_eqd2, "EQD2_max": max_eqd2}
    return constraint_evaluation
    
def check_plan_time(plan_time):
    """Checks if the plan time is outside of normal business hours (7am-5pm)."""
    if plan_time == 'N/A':
        return None
    try:
        hour = int(plan_time[:2])
        if not 7 <= hour < 17:
            return "Warning: Plan time is outside of normal business hours (7am-5pm)."
    except (ValueError, IndexError):
        return "Warning: Invalid plan time format."
    return None

def calculate_optimization_goal(total_eqd2_constraint, alpha_beta, ebrt_dose, ebrt_fractions, previous_brachy_bed, num_new_brachy_fractions=1):
    """
    Calculates the maximum allowed physical dose per fraction for a new brachytherapy plan
    to stay within the total EQD2 constraint.

    Returns:
        The maximum physical dose (e.g., D2cc) per fraction, or 0.0 if the constraint is
        already met or exceeded.
    """
    # 1. Calculate the BED contribution from EBRT
    bed_ebrt = 0
    if ebrt_dose > 0 and ebrt_fractions > 0:
        ebrt_dose_per_fraction = ebrt_dose / ebrt_fractions
        bed_ebrt = ebrt_dose * (1 + ebrt_dose_per_fraction / alpha_beta)

    # 2. Calculate the total BED from all previously delivered radiation
    delivered_bed = bed_ebrt + previous_brachy_bed

    # 3. Convert the organ's total EQD2 constraint into a total BED constraint
    total_bed_constraint = total_eqd2_constraint * (1 + 2 / alpha_beta)

    # 4. Find the remaining BED budget for the new brachytherapy plan
    remaining_bed_budget = total_bed_constraint - delivered_bed

    if remaining_bed_budget <= 0:
        return 0.0 # Constraint is already exceeded

    # 5. Determine the allowed BED for each new fraction being planned
    bed_per_new_fraction = remaining_bed_budget / num_new_brachy_fractions

    # 6. Solve the quadratic equation BED = d*(1 + d/αβ) for the physical dose 'd'
    a = 1
    b = alpha_beta
    c = -alpha_beta * bed_per_new_fraction

    # We use the quadratic formula and take the positive root for the dose
    discriminant = (b**2) - (4 * a * c)
    if discriminant < 0:
        return 0.0

    physical_dose_per_fraction = (-b + np.sqrt(discriminant)) / (2 * a)

    return physical_dose_per_fraction