import sys
from .html_parser import parse_html_report
from .dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data
from .calculations import get_dvh, evaluate_constraints, calculate_dose_to_meet_constraint, calculate_point_dose_bed_eqd2
import argparse
from pathlib import Path
import json
from .config import alpha_beta_ratios, constraints

def generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, dvh_results, constraint_evaluation, dose_references, point_dose_results, output_path, alpha_beta_ratios):
    # Determine the base path for data files
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in a normal Python environment
        base_path = Path(__file__).parent

    template_path = Path(base_path) / "templates" / "report_template.html"

    with open(template_path, "r") as f:
        template = f.read()

    target_volume_rows = ""
    oar_rows = ""
    for organ, data in dvh_results.items():
        eqd2_met_class = ""
        if organ in constraint_evaluation:
            organ_constraints = constraint_evaluation[organ]
            if "EQD2_met" in organ_constraints:
                eqd2_met_class = "met" if organ_constraints["EQD2_met"] == "True" else "not-met"

        alpha_beta = alpha_beta_ratios.get(organ, alpha_beta_ratios["Default"])
        is_target = alpha_beta == 10

        if is_target:
            rowspan = 5
            target_volume_rows += f"""<tr>
                <td rowspan="{rowspan}">{organ}</td>
                <td rowspan="{rowspan}">{alpha_beta}</td>
                <td rowspan="{rowspan}">{data["volume_cc"]}</td>"""
            target_volume_rows += f"""<td>D98</td>
                <td>{data["d98_gy_per_fraction"]}</td>
                <td colspan="6"></td>
            </tr>"""
            target_volume_rows += f"""<tr>
                <td>D90</td>
                <td>{data.get("d90_gy_per_fraction", "N/A")}</td>
                <td colspan="6"></td>
            </tr>"""
            target_volume_rows += f"""<tr>
                <td>Max</td>
                <td>{data["max_dose_gy_per_fraction"]}</td>
                <td colspan="6"></td>
            </tr>"""
            target_volume_rows += f"""<tr>
                <td>Mean</td>
                <td>{data["mean_dose_gy_per_fraction"]}</td>
                <td colspan="6"></td>
            </tr>"""
            target_volume_rows += f"""<tr>
                <td>Min</td>
                <td>{data["min_dose_gy_per_fraction"]}</td>
                <td colspan="6"></td>
            </tr>"""
        else:
            rowspan = 3
            rows = []
            rows.append(f"""<tr>
                <td rowspan="{rowspan}">{organ}</td>
                <td rowspan="{rowspan}">{alpha_beta}</td>
                <td rowspan="{rowspan}">{data["volume_cc"]}</td>
                <td>D0.1cc</td>
                <td>{data["d0_1cc_gy_per_fraction"]}</td>
                <td>{data["d0_1cc_gy_per_fraction"] * number_of_fractions:.2f}</td>
                <td>{data["bed_d0_1cc"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d0_1cc"]}</td>
                <td></td>
                <td></td>
            </tr>""")
            rows.append(f"""<tr>
                <td>D1cc</td>
                <td>{data["d1cc_gy_per_fraction"]}</td>
                <td>{data["d1cc_gy_per_fraction"] * number_of_fractions:.2f}</td>
                <td>{data["bed_d1cc"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d1cc"]}</td>
                <td></td>
                <td></td>
            </tr>""")
            rows.append(f"""<tr>
                <td>D2cc</td>
                <td>{data["d2cc_gy_per_fraction"]}</td>
                <td>{data["total_d2cc_gy"]}</td>
                <td>{data["bed_this_plan"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d2cc"]}</td>
                <td class="{eqd2_met_class}">{'Met' if eqd2_met_class == 'met' else 'NOT Met'}</td>
                <td>{data.get("dose_to_meet_constraint", "N/A")}</td>
            </tr>""")
            oar_rows += "".join(rows)

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ plan_name }}", plan_name)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ target_volume_rows }}", target_volume_rows)
    html_content = html_content.replace("{{ oar_rows }}", oar_rows)

    dose_ref_rows = ""
    for dr in dose_references:
        dose_ref_rows += f"<tr><td>{dr['name']}</td><td>{dr['dose']}</td></tr>"
    html_content = html_content.replace("{{ dose_reference_rows }}", dose_ref_rows)

    point_dose_rows = ""
    for pr in point_dose_results:
        point_dose_rows += f"""<tr>
            <td>{pr['name']}</td>
            <td>{alpha_beta_ratios.get(pr['name'], alpha_beta_ratios["Default"])}</td>
            <td>{pr['dose']:.2f}</td>
            <td>{pr['total_dose']:.2f}</td>
            <td>{pr['bed_this_plan']:.2f}</td>
            <td>{pr['bed_previous_brachy']:.2f}</td>
            <td>{pr['bed_ebrt']:.2f}</td>
            <td>{pr['eqd2']:.2f}</td>
            <td></td>
            <td></td>
        </tr>"""
    html_content = html_content.replace("{{ point_dose_rows }}", point_dose_rows)

    with open(output_path, "w") as f:
        f.write(html_content)
    
    return html_content

def main(args, selected_point_names=None): # Added selected_point_names parameter
    data_dir = Path(args.data_dir)

    # Use custom alpha/beta ratios if provided, otherwise use defaults
    current_alpha_beta_ratios = alpha_beta_ratios.copy()
    if hasattr(args, 'alpha_beta_ratios') and args.alpha_beta_ratios:
        for organ, ratio in args.alpha_beta_ratios.items():
            current_alpha_beta_ratios[organ] = ratio

    # Find the subdirectories
    subdirectories = [d for d in data_dir.iterdir() if d.is_dir()]
    dose_dir = next((d for d in subdirectories if "RTDOSE" in d.name), None)
    struct_dir = next((d for d in subdirectories if "RTst" in d.name), None)
    plan_dir = next((d for d in subdirectories if "RTPLAN" in d.name), None)

    if not all([dose_dir, struct_dir, plan_dir]):
        print(json.dumps({"error": "Could not find all required DICOM subdirectories (RTDOSE, RTst, RTPLAN)."}))
        return

    # Find the DICOM files
    dose_file = find_dicom_file(dose_dir)
    struct_file = find_dicom_file(struct_dir)
    plan_file = find_dicom_file(plan_dir)

    if not all([dose_file, struct_file, plan_file]):
        print(json.dumps({"error": "Could not find all DICOM files." }))
        return

    # Load the DICOM files
    rt_dose_dataset = load_dicom_file(dose_file)
    rt_struct_dataset = load_dicom_file(struct_file)
    rt_plan_dataset = load_dicom_file(plan_file)

    if not all([rt_dose_dataset, rt_struct_dataset, rt_plan_dataset]):
        print(json.dumps({"error": "Could not load all DICOM files." }))
        return

    # Verify patient consistency
    patient_ids = {rt_dose_dataset.PatientID, rt_struct_dataset.PatientID, rt_plan_dataset.PatientID}
    if len(patient_ids) > 1:
        print(json.dumps({"error": "DICOM files belong to different patients." }))
        return

    patient_name = str(rt_dose_dataset.PatientName)
    patient_mrn = str(rt_dose_dataset.PatientID)

    # Get plan data
    plan_data = get_plan_data(plan_file)
    number_of_fractions = plan_data.get('number_of_fractions', 1)
    plan_name = plan_data.get('plan_name', 'N/A')
    brachy_dose_per_fraction = plan_data.get('brachy_dose_per_fraction', 'N/A')
    

    # Get structure data
    structure_data = get_structure_data(rt_struct_dataset)

    # Parse previous brachytherapy HTML report if provided
    previous_brachy_eqd2_per_organ = {}
    if args.previous_brachy_html:
        previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_html)

    # Calculate DVH
    dvh_results = get_dvh(
        struct_file,
        dose_file,
        structure_data,
        number_of_fractions,
        ebrt_dose=args.ebrt_dose,
        previous_brachy_eqd2_per_organ=previous_brachy_eqd2_per_organ,
        alpha_beta_ratios=current_alpha_beta_ratios
    )

    current_constraints = constraints
    # Evaluate constraints
    constraint_evaluation = evaluate_constraints(dvh_results, constraints=current_constraints)

    # Calculate dose to meet constraint for unmet EQD2 constraints
    for organ, data in dvh_results.items():
        if organ in constraint_evaluation:
            organ_constraints = constraint_evaluation[organ]
            if "EQD2_met" in organ_constraints and organ_constraints["EQD2_met"] == "False":
                eqd2_constraint = organ_constraints["EQD2_max"]
                dose_needed = calculate_dose_to_meet_constraint(
                    eqd2_constraint,
                    organ,
                    number_of_fractions,
                    args.ebrt_dose,
                    previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(organ, 0),
                    alpha_beta_ratios=current_alpha_beta_ratios
                )
                dvh_results[organ]["dose_to_meet_constraint"] = dose_needed
            else:
                dvh_results[organ]["dose_to_meet_constraint"] = "N/A"

    # Calculate BED and EQD2 for point doses
    point_dose_results = []
    # Filter dose references based on selected_point_names
    filtered_dose_references = []
    if selected_point_names:
        for dr in plan_data.get('dose_references', []):
            if dr['name'] in selected_point_names:
                filtered_dose_references.append(dr)
    else:
        filtered_dose_references = plan_data.get('dose_references', []) # If no selection, include all

    for dr in filtered_dose_references: # Use filtered_dose_references
        total_bed, eqd2, bed_brachy, bed_ebrt, bed_previous_brachy = calculate_point_dose_bed_eqd2(
            dr['dose'],
            number_of_fractions,
            dr['name'],
            args.ebrt_dose,
            previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(dr['name'], 0),
            alpha_beta_ratios=current_alpha_beta_ratios
        )
        point_dose_results.append({
            'name': dr['name'],
            'dose': dr['dose'],
            'total_dose': dr['dose'] * number_of_fractions,
            'bed': total_bed,
            'eqd2': eqd2,
            'bed_this_plan': bed_brachy,
            'bed_ebrt': bed_ebrt,
            'bed_previous_brachy': bed_previous_brachy
        })

    output_data = {
        "patient_name": patient_name,
        "patient_mrn": patient_mrn,
        "plan_name": plan_name,
        "brachy_dose_per_fraction": brachy_dose_per_fraction,
        "number_of_fractions": number_of_fractions,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation,
        "dose_references": plan_data.get('dose_references', []),
        "point_dose_results": point_dose_results,
        "used_alpha_beta_ratios": current_alpha_beta_ratios
    }

    if args.output_html:
        generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, args.ebrt_dose, dvh_results, constraint_evaluation, output_data['dose_references'], output_data['point_dose_results'], args.output_html, current_alpha_beta_ratios)

    return output_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brachytherapy Plan Evaluator")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the directory containing the patient's DICOM files.")
    parser.add_argument("--ebrt_dose", type=float, default=0.0, help="The prescription dose of the external beam radiation therapy in Gray (Gy).")
    parser.add_argument("--previous_brachy_html", type=str, help="Path to a previous brachytherapy HTML report to incorporate its EQD2 values.")
    parser.add_argument("--output_html", type=str, help="If provided, the results will be saved to this HTML file.")

    args = parser.parse_args()
    main(args)
