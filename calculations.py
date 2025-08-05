import numpy as np
import pydicom
from dicompylercore import dvhcalc
from config import alpha_beta_ratios, constraints

# This file will contain the logic for dose-volume calculations.

def calculate_bed_and_eqd2(total_dose, dose_per_fraction, organ_name, ebrt_dose=0):
    """Calculates BED and EQD2 for a given total dose and dose per fraction, with an optional EBRT dose."""
    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])
    
    # Calculate BED for brachytherapy
    bed_brachy = total_dose * (1 + (dose_per_fraction / alpha_beta))
    
    # Calculate BED for EBRT
    bed_ebrt = ebrt_dose * (1 + (2 / alpha_beta)) # Assuming 2 Gy/fraction for EBRT
    
    # Total BED
    total_bed = bed_brachy + bed_ebrt
    
    # Calculate total EQD2
    eqd2 = total_bed / (1 + (2 / alpha_beta))
    
    return round(total_bed, 2), round(eqd2, 2)

def calculate_dose_to_meet_constraint(eqd2_constraint, organ_name, number_of_fractions, ebrt_dose=0):
    """Calculates the brachytherapy dose per fraction needed to meet a specific EQD2 constraint."""
    alpha_beta = alpha_beta_ratios.get(organ_name, alpha_beta_ratios["Default"])

    # Convert EQD2 constraint back to total BED target
    k_factor = (1 + (2 / alpha_beta))
    total_bed_target = eqd2_constraint * k_factor

    # Calculate BED from EBRT
    bed_ebrt = ebrt_dose * k_factor

    # Remaining BED needed from brachytherapy
    bed_brachy_needed = total_bed_target - bed_ebrt

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

def get_dvh(rtss_file, rtdose_file, structure_data, number_of_fractions, ebrt_dose=0):
    """Calculates the Dose-Volume Histogram (DVH) for each structure."""
    dvh_results = {}

    for name, data in structure_data.items():
        roi_number = data["ROINumber"]
        dvh = dvhcalc.get_dvh(rtss_file, rtdose_file, roi_number)

        d2cc_gy_per_fraction = dvh.D2cc.value
        organ_volume_cc = dvh.volume

        total_d2cc_gy = d2cc_gy_per_fraction * number_of_fractions

        bed, eqd2 = calculate_bed_and_eqd2(total_d2cc_gy, d2cc_gy_per_fraction, name, ebrt_dose)

        dvh_results[name] = {
            "volume_cc": round(organ_volume_cc, 2),
            "d2cc_gy_per_fraction": round(d2cc_gy_per_fraction, 2),
            "total_d2cc_gy": round(total_d2cc_gy, 2),
            "bed": bed,
            "eqd2": eqd2
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
                evaluation["BED_met"] = str(data["bed"] <= max_bed)
                evaluation["BED_value"] = data["bed"]
                evaluation["BED_max"] = max_bed
            if "EQD2" in organ_constraints:
                max_eqd2 = organ_constraints["EQD2"]["max"]
                evaluation["EQD2_met"] = str(data["eqd2"] <= max_eqd2)
                evaluation["EQD2_value"] = data["eqd2"]
                evaluation["EQD2_max"] = max_eqd2
            constraint_evaluation[organ] = evaluation
    return constraint_evaluation