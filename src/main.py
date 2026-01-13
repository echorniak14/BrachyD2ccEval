import sys
import json
import io
from datetime import datetime

import pydicom

# The following imports are now from the backend's core and services
from backend.src.core import calculations, validators
from backend.src.services.parser_service import ParserService
from backend.src.config import templates # Assuming you created this from previous step



def main(args, structure_data, plan_data, selected_point_names=None, custom_constraints=None, dose_point_mapping=None, num_fractions_delivered=None, ebrt_fractions=None, structure_mapping=None, confirmed_structure_mapping=None):
    data_dir = Path(args.data_dir)

    if hasattr(args, 'alpha_beta_ratios') and args.alpha_beta_ratios:
        current_alpha_beta_ratios = args.alpha_beta_ratios.copy()
    else:
        from .config import templates
        current_alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy()
    
    if "Default" not in current_alpha_beta_ratios:
        from .config import templates
        current_alpha_beta_ratios["Default"] = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]["Default"]

    point_dose_results, previous_brachy_bed_per_organ = [], {}

    if hasattr(args, 'previous_brachy_data') and args.previous_brachy_data:
            if isinstance(args.previous_brachy_data, dict):
                # Correctly parse DVH results by accessing the nested 'dose_fx' dictionary
                for organ, data in args.previous_brachy_data.get('dvh_results', {}).items():
                    organ_lower = organ.lower()
                    if organ not in previous_brachy_bed_per_organ:
                        previous_brachy_bed_per_organ[organ] = {}
                    alpha_beta = current_alpha_beta_ratios.get(organ, current_alpha_beta_ratios["Default"])
                    
                    dose_fx_dict = data.get('dose_fx', {}) # Access the inner dictionary
                    for metric, dose_list in dose_fx_dict.items():
                        simple_metric = metric.replace('_gy_per_fraction', '')
                        if isinstance(dose_list, list):
                            total_metric_bed = sum(dose * (1 + dose / alpha_beta) for dose in dose_list)
                            previous_brachy_bed_per_organ[organ][simple_metric] = total_metric_bed

                # Correctly parse point dose results
                for point_name, data in args.previous_brachy_data.get('point_dose_results', {}).items():
                    alpha_beta = current_alpha_beta_ratios.get(point_name, current_alpha_beta_ratios["Default"])
                    dose_list = data.get('dose_fx', []) # Get the dose list for the point
                    if isinstance(dose_list, list):
                        total_point_bed = sum(dose * (1 + dose / alpha_beta) for dose in dose_list)
                        previous_brachy_bed_per_organ[point_name] = total_point_bed
        # --- START: corrected EQD2 with json brachy data ---

    dose_dir = next((d for d in Path(args.data_dir).iterdir() if d.is_dir() and "RTDOSE" in d.name), None)
    struct_dir = next((d for d in Path(args.data_dir).iterdir() if d.is_dir() and "RTst" in d.name), None)
    dose_file, struct_file = find_dicom_file(dose_dir), find_dicom_file(struct_dir)

    planned_number_of_fractions = plan_data.get('number_of_fractions', 1)
    number_of_fractions_for_calc = num_fractions_delivered if num_fractions_delivered is not None else planned_number_of_fractions

    alpha_beta_for_calc = {}
    if structure_mapping:
        for dicom_name, mapped_name in structure_mapping.items():
            standard_ab_ratio = current_alpha_beta_ratios.get(mapped_name.capitalize(), current_alpha_beta_ratios.get(mapped_name, current_alpha_beta_ratios["Default"]))
            alpha_beta_for_calc[dicom_name] = standard_ab_ratio
    else:
        alpha_beta_for_calc = current_alpha_beta_ratios

    dvh_results_orig_names = get_dvh(
        struct_file, dose_file, structure_data, number_of_fractions_for_calc,
        ebrt_dose=args.ebrt_dose, ebrt_fractions=ebrt_fractions,
        previous_brachy_bed_per_organ=previous_brachy_bed_per_organ,
        alpha_beta_ratios=alpha_beta_for_calc,
        confirmed_structure_mapping=confirmed_structure_mapping
    )

    rt_dose_dataset = load_dicom_file(dose_file)

    # --- NEW: HYBRID ARCHITECTURE LOGIC ---
    # 1. We have the DICOM calculation above (Digital Twin / QA Check)
    dvh_results_dicom = dvh_results_orig_names 
    tps_warnings = []

    # 2. Check for Text File (Source of Truth)
    if hasattr(args, 'dvh_text_path') and args.dvh_text_path:
        try:
            print(f"Loading TPS Text File: {args.dvh_text_path}")
            with open(args.dvh_text_path, 'r') as f:
                # --- NEW: Unpack Tuple ---
                parsed_dvh_data, text_metadata = parse_dvh_text_file(f.read())
            
            if parsed_dvh_data:
                # A. Transform data
                dvh_results_text = get_dvh_metrics_from_text(
                    parsed_dvh_data,
                    structure_mapping=confirmed_structure_mapping,
                    number_of_fractions=number_of_fractions_for_calc,
                    previous_brachy_bed_per_organ=previous_brachy_bed_per_organ
                )
                
                # B. VALIDATION: Now passing IDs
                tps_warnings = validate_tps_import(
                    calculated_dvh=dvh_results_dicom,
                    reported_dvh=dvh_results_text,
                    dicom_patient_id=rt_dose_dataset.PatientID, # Pass DICOM ID
                    text_metadata=text_metadata,                # Pass Text ID
                    tolerance_gy=5.0 
                )

                # --- NEW: GENERATE DATAFRAME ---
                validation_df = generate_validation_dataframe(
                    dicom_results=dvh_results_dicom,
                    text_results=dvh_results_text,
                    patient_id=str(rt_dose_dataset.PatientID)
                )
                # -------------------------------
                
                # C. SWAP Results
                dvh_results_orig_names = dvh_results_text
                
            else:
                 tps_warnings.append("DVH Text file was empty or could not be parsed.")
                 
        except Exception as e:
            tps_warnings.append(f"Error processing TPS Text file: {e}")
    
    # --- START: FINAL Case-Insensitive Mapping Logic ---
    dvh_results_mapped = {}
    if structure_mapping:
        case_insensitive_mapping = {key.lower(): value for key, value in structure_mapping.items()}
        for original_dicom_name, dvh_data in dvh_results_orig_names.items():
            from .calculations import normalize_structure_name
            normalized_lookup_key = normalize_structure_name(original_dicom_name)
            
            mapped_name = case_insensitive_mapping.get(normalized_lookup_key.lower())
            
            if mapped_name and mapped_name != "Ignore":
                dvh_results_mapped[mapped_name] = dvh_data
            # Also pass through unmapped OARs
            elif original_dicom_name in ["Bladder", "Rectum", "Sigmoid", "Bowel"]:
                 dvh_results_mapped[original_dicom_name] = dvh_data
    else:
        # Fallback if no mapping was provided
        dvh_results_mapped = dvh_results_orig_names
    # --- END: FINAL Case-Insensitive Mapping Logic ---

    for organ, data in dvh_results_mapped.items():

        dose_metrics = {
            'd2cc': 'd2cc_gy_per_fraction', 'd1cc': 'd1cc_gy_per_fraction', 'd0_1cc': 'd0_1cc_gy_per_fraction',
            'd90': 'd90_gy_per_fraction', 'd98': 'd98_gy_per_fraction', 'd95': 'd95_gy_per_fraction',
            'max': 'max_dose_gy_per_fraction', 'mean': 'mean_dose_gy_per_fraction', 'min': 'min_dose_gy_per_fraction',
        }
        for metric_key, dose_key in dose_metrics.items():
            dose_per_fraction = data.get(dose_key, 0)
            # This now correctly calculates the dose for the NEW fractions planned
            total_dose = dose_per_fraction * number_of_fractions_for_calc
            previous_brachy_bed = data.get('previous_brachy_bed', {}).get(metric_key, 0)
            total_bed, eqd2, bed_brachy, _, _ = calculate_bed_and_eqd2(
                total_dose, dose_per_fraction, organ, args.ebrt_dose, ebrt_fractions,
                previous_brachy_bed, current_alpha_beta_ratios
            )
            data[f'bed_{metric_key}'], data[f'eqd2_{metric_key}'], data[f'bed_brachy_{metric_key}'] = total_bed, eqd2, bed_brachy

    current_target_constraints = custom_constraints.get("constraints", {}).get("target_constraints", {})
    current_oar_constraints = custom_constraints.get("constraints", {}).get("oar_constraints", {})
    point_dose_constraints = custom_constraints.get("point_dose_constraints", {})
    
    filtered_dose_references = [dr for dr in plan_data.get('dose_references', []) if (selected_point_names and dr['name'] in selected_point_names) or not selected_point_names]
    for dr in filtered_dose_references:
        total_bed, eqd2, bed_brachy, bed_ebrt, bed_previous_brachy = calculate_point_dose_bed_eqd2(
            dr['dose'], number_of_fractions_for_calc, dr['name'], args.ebrt_dose, ebrt_fractions,
            previous_brachy_bed=previous_brachy_bed_per_organ.get(dr['name'], 0), alpha_beta_ratios=current_alpha_beta_ratios
        )
        point_dose_results.append({
            'name': dr['name'], 'dose': dr['dose'], 'total_dose': dr['dose'] * number_of_fractions_for_calc,
            'BED_this_plan': bed_brachy, 'BED_previous_brachy': bed_previous_brachy, 'BED_EBRT': bed_ebrt, 'EQD2': eqd2,
        })

    constraint_evaluation = evaluate_constraints(dvh_results_mapped, point_dose_results, current_target_constraints, current_oar_constraints, point_dose_constraints, dose_point_mapping)

    mapping_dict = {item[0]: item[1] for item in dose_point_mapping} if dose_point_mapping else {}
    for pr in point_dose_results:
        status_updated = False
        mapped_constraint_name = mapping_dict.get(pr['name'])
        if mapped_constraint_name and mapped_constraint_name in point_dose_constraints:
            constraint = point_dose_constraints[mapped_constraint_name]
            if constraint.get("check_type") == "prescription_tolerance":
                tolerance = constraint.get("tolerance", 0.0)
                prescribed_dose = plan_data.get('brachy_dose_per_fraction', 0)
                if prescribed_dose > 0:
                    pr['Constraint Status'] = 'Pass' if prescribed_dose * (1 - tolerance) <= pr['dose'] <= prescribed_dose * (1 + tolerance) else 'Fail'
                    status_updated = True
            elif "max_eqd2" in constraint:
                pr['Constraint Status'] = 'Pass' if pr['EQD2'] <= constraint["max_eqd2"] else 'Fail'
                status_updated = True
        if not status_updated:
            point_eval = constraint_evaluation.get(f"Point Dose - {pr['name']}", {})
            pr['Constraint Status'] = point_eval.get('status', 'N/A')

    for organ, data in dvh_results_mapped.items():
        if organ in constraint_evaluation and constraint_evaluation[organ].get("EQD2_met") == "False":
            eqd2_constraint = constraint_evaluation[organ]["EQD2_max"]
            prev_bed_dict = previous_brachy_bed_per_organ.get(organ, {})
            prev_d2cc_bed = prev_bed_dict.get('d2cc', 0) if isinstance(prev_bed_dict, dict) else 0
            data["dose_to_meet_constraint"] = calculate_dose_to_meet_constraint(
                eqd2_constraint, organ, number_of_fractions_for_calc, args.ebrt_dose,
                ebrt_fractions=ebrt_fractions, previous_brachy_bed=prev_d2cc_bed, alpha_beta_ratios=current_alpha_beta_ratios
            )
        else:
            data["dose_to_meet_constraint"] = "N/A"

    source_strength_ref_date = plan_data.get('source_strength_ref_date', 'N/A')
    source_strength_ref_time = plan_data.get('source_strength_ref_time', 'N/A')
    if source_strength_ref_date != 'N/A' and source_strength_ref_time != 'N/A':
        plan_datetime = datetime.strptime(f"{source_strength_ref_date}{source_strength_ref_time.split('.')[0]}", "%Y%m%d%H%M%S")
        formatted_plan_date, formatted_plan_time = plan_datetime.strftime('%Y-%m-%d'), plan_datetime.strftime('%H:%M:%S')
    else:
        formatted_plan_date, formatted_plan_time = 'N/A', 'N/A'
    
    output_data = {
        "patient_name": str(rt_dose_dataset.PatientName), "patient_mrn": str(rt_dose_dataset.PatientID),
        "plan_name": plan_data.get('plan_name', 'N/A'), "plan_date": formatted_plan_date, "plan_time": formatted_plan_time,
        "source_info": plan_data.get('source_info', 'N/A'), "channel_mapping": plan_data.get('channel_mapping', []),
        "brachy_dose_per_fraction": plan_data.get('brachy_dose_per_fraction', 0), "planned_number_of_fractions": planned_number_of_fractions,
        "calculation_number_of_fractions": number_of_fractions_for_calc, "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results_mapped,
        "constraint_evaluation": constraint_evaluation,
        "point_dose_results": point_dose_results,
        "plan_time_warning": check_plan_time(plan_data.get('plan_time')),
        "tps_validation_warnings": tps_warnings,
        "validation_df": validation_df if 'validation_df' in locals() else None,
    }

    if args.output_html:
        html_content = generate_html_report(
            output_data["patient_name"], output_data["patient_mrn"], output_data["plan_name"], 
            output_data["plan_date"], output_data["plan_time"], output_data["source_info"],
            output_data["brachy_dose_per_fraction"], output_data["calculation_number_of_fractions"], 
            output_data["ebrt_dose"], ebrt_fractions, output_data["dvh_results"], 
            output_data["constraint_evaluation"], plan_data.get('dose_references', []), 
            output_data["point_dose_results"], args.output_html, current_alpha_beta_ratios,
            previous_brachy_data=args.previous_brachy_data
        )
        output_data['html_report'] = html_content

    return output_data
