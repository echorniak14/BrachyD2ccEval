import numpy as np
import pydicom
from dicompylercore import dvhcalc
from .config import alpha_beta_ratios, constraints
import os
import contextlib
import re

def normalize_structure_name(name):
    """Normalizes structure names for consistent matching."""
    # Remove content in brackets (e.g., [cm3]) or parentheses
    name = re.sub(r'\s*\[.*?\]', '', name)
    name = re.sub(r'\s*\(.*?\]', '', name)
    # Convert to lowercase and strip whitespace
    return name.strip().lower()

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


# This file will contain the logic for dose-volume calculations.

def calculate_bed_and_eqd2(total_dose, dose_per_fraction, organ_name, ebrt_dose=0, previous_brachy_eqd2=0):
    """Calculates BED and EQD2 for a given total dose and dose per fraction, with an optional EBRT dose."""
    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    
    # Calculate BED for brachytherapy
    bed_brachy = total_dose * (1 + (dose_per_fraction / alpha_beta))
    
    # Calculate BED for EBRT
    bed_ebrt = ebrt_dose * (1 + (2 / alpha_beta)) # Assuming 2 Gy/fraction for EBRT

    # Calculate BED for previous brachytherapy
    bed_previous_brachy = previous_brachy_eqd2 * (1 + (2 / alpha_beta))
    
    # Total BED
    total_bed = bed_brachy + bed_ebrt + bed_previous_brachy
    
    # Calculate total EQD2
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2), round(bed_brachy, 2), round(bed_ebrt, 2), round(bed_previous_brachy, 2)

def calculate_dose_to_meet_constraint(eqd2_constraint, organ_name, number_of_fractions, ebrt_dose=0, previous_brachy_eqd2=0):
    """Calculates the brachytherapy dose per fraction needed to meet a specific EQD2 constraint."""
    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])

    # Convert EQD2 constraint back to total BED target
    k_factor = (1 + (2 / alpha_beta))
    total_bed_target = eqd2_constraint * k_factor

    # Calculate BED from EBRT
    bed_ebrt = ebrt_dose * k_factor

    # Calculate BED from previous brachytherapy
    bed_previous_brachy = previous_brachy_eqd2 * k_factor

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

def get_dvh(rtss_file, rtdose_file, structure_data, number_of_fractions, ebrt_dose=0, previous_brachy_eqd2_per_organ=None):
    """Calculates the Dose-Volume Histogram (DVH) for each structure."""
    if previous_brachy_eqd2_per_organ is None:
        previous_brachy_eqd2_per_organ = {}
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

            d0_1cc_gy_per_fraction = getattr(dvh, 'D0_1cc', 0.0)
            if hasattr(d0_1cc_gy_per_fraction, 'value'):
                d0_1cc_gy_per_fraction = d0_1cc_gy_per_fraction.value
        except Exception as e:
            print(f"Warning: Could not calculate DVH for {name} (ROI Number: {roi_number}). Error: {e}")
            d2cc_gy_per_fraction = 0.0
            d1cc_gy_per_fraction = 0.0
            d0_1cc_gy_per_fraction = 0.0

        # Calculations for D2cc
        total_d2cc_gy = d2cc_gy_per_fraction * number_of_fractions
        bed_d2cc, eqd2_d2cc, bed_brachy_d2cc, bed_ebrt_d2cc, bed_previous_brachy_d2cc = calculate_bed_and_eqd2(
            total_d2cc_gy, d2cc_gy_per_fraction, name, ebrt_dose, previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(name, 0)
        )

        # Calculations for D1cc
        total_d1cc_gy = d1cc_gy_per_fraction * number_of_fractions
        bed_d1cc, eqd2_d1cc, _, _, _ = calculate_bed_and_eqd2(
            total_d1cc_gy, d1cc_gy_per_fraction, name, ebrt_dose, previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(name, 0)
        )

        # Calculations for D0.1cc
        total_d0_1cc_gy = d0_1cc_gy_per_fraction * number_of_fractions
        bed_d0_1cc, eqd2_d0_1cc, _, _, _ = calculate_bed_and_eqd2(
            total_d0_1cc_gy, d0_1cc_gy_per_fraction, name, ebrt_dose, previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(name, 0)
        )

        dvh_results[name] = {
            "volume_cc": round(organ_volume_cc, 2),
            "d2cc_gy_per_fraction": round(d2cc_gy_per_fraction, 2),
            "d1cc_gy_per_fraction": round(d1cc_gy_per_fraction, 2),
            "d0_1cc_gy_per_fraction": round(d0_1cc_gy_per_fraction, 2),
            "total_d2cc_gy": round(total_d2cc_gy, 2),
            "bed_d2cc": bed_d2cc,
            "eqd2_d2cc": eqd2_d2cc,
            "bed_d1cc": bed_d1cc,
            "eqd2_d1cc": eqd2_d1cc,
            "bed_d0_1cc": bed_d0_1cc,
            "eqd2_d0_1cc": eqd2_d0_1cc,
            "bed_this_plan": bed_brachy_d2cc, # Assuming this is tied to D2cc
            "bed_ebrt": bed_ebrt_d2cc,
            "bed_previous_brachy": bed_previous_brachy_d2cc
        }

    return dvh_results

def evaluate_constraints(dvh_results):
    """Evaluates calculated DVH results against predefined constraints."""
    constraint_evaluation = {}
    for organ, data in dvh_results.items():
        if organ in constraints:
            organ_constraints = constraints[organ]
            evaluation = {}
            if "BED" in organ_constraints:
                max_bed = organ_constraints["BED"]["max"]
                evaluation["BED_met"] = str(data["bed_d2cc"] <= max_bed)
                evaluation["BED_value"] = data["bed_d2cc"]
                evaluation["BED_max"] = max_bed
            if "EQD2" in organ_constraints:
                max_eqd2 = organ_constraints["EQD2"]["max"]
                evaluation["EQD2_met"] = str(data["eqd2_d2cc"] <= max_eqd2)
                evaluation["EQD2_value"] = data["eqd2_d2cc"]
                evaluation["EQD2_max"] = max_eqd2
            constraint_evaluation[organ] = evaluation
    return constraint_evaluation