import sys
import base64
from .html_parser import parse_html_report
from .dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data, get_dose_data
from .calculations import get_dvh, evaluate_constraints, calculate_dose_to_meet_constraint, calculate_point_dose_bed_eqd2, get_dose_at_point
import argparse
from pathlib import Path
import json
import pdfkit

def replace_css_variables(html_content):
    """Replaces CSS variables with their actual values for PDF generation."""
    colors = {
        '--text-color': '#333',
        '--background-color': '#fff',
        '--header-color-1': '#2a7ae2',
        '--header-color-2': '#1e5aab',
        '--border-color': '#ddd',
        '--table-header-bg': '#1e5aab',
        '--table-header-text': 'white',
        '--table-even-row-bg': '#eaf2fa',
        '--met-bg': '#77dd77',
        '--met-text': 'white',
        '--not-met-bg': '#ff6961',
        '--not-met-text': 'white',
        '--warning-bg': '#fdfd96',
        '--warning-text': 'black',
    }
    for var, value in colors.items():
        html_content = html_content.replace(f'var({var})', value)
    return html_content

def convert_html_to_pdf(html_content, output_path, wkhtmltopdf_path=None):
    """
    Converts HTML content to a PDF file using pdfkit.
    """
    try:
        config = None
        if wkhtmltopdf_path:
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        
        options = {'enable-local-file-access': None}
        
        pdf_html_content = replace_css_variables(html_content)
        pdfkit.from_string(pdf_html_content, output_path, configuration=config, options=options)
    except IOError as e:
        raise IOError(
            "Could not locate wkhtmltopdf. Please install it and ensure it's in your system's PATH, or provide the path in the sidebar."
            f"\n\nOriginal error: {e}"
        )

def generate_html_report(patient_name, patient_mrn, plan_name, plan_date, plan_time, source_info, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, dvh_results, constraint_evaluation, dose_references, point_dose_results, output_path, alpha_beta_ratios):
    if not isinstance(alpha_beta_ratios, dict) or "Default" not in alpha_beta_ratios:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy()
    
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = Path(__file__).parent

    template_path = Path(base_path) / "templates" / "report_template.html"
    logo_path = Path(base_path) / "assets" / "2020-flame-red-02.PNG"

    with open(template_path, "r") as f:
        template = f.read()

    try:
        with open(logo_path, "rb") as img_file:
            logo_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            logo_data_uri = f"data:image/png;base64,{logo_base64}"
    except FileNotFoundError:
        logo_data_uri = ""

    target_volume_rows = ""
    oar_rows = ""
    for organ, data in dvh_results.items():
        alpha_beta = alpha_beta_ratios.get(organ, alpha_beta_ratios["Default"])
        if alpha_beta == 10: # is_target
            target_volume_rows += f"""<tr><td rowspan="5">{organ}</td><td rowspan="5">{alpha_beta}</td><td rowspan="5">{data["volume_cc"]}</td><td>D98</td><td>{data["d98_gy_per_fraction"]:.2f}</td><td>{(data["d98_gy_per_fraction"] * number_of_fractions):.2f}</td><td>{data["eqd2_d98"]:.2f}</td></tr><tr><td>D90</td><td>{data.get("d90_gy_per_fraction", 0):.2f}</td><td>{(data.get("d90_gy_per_fraction", 0) * number_of_fractions):.2f}</td><td>{data["eqd2_d90"]:.2f}</td></tr><tr><td>Max</td><td>{data["max_dose_gy_per_fraction"]:.2f}</td><td>{(data["max_dose_gy_per_fraction"] * number_of_fractions):.2f}</td><td colspan="1"></td></tr><tr><td>Mean</td><td>{data["mean_dose_gy_per_fraction"]:.2f}</td><td>{(data["mean_dose_gy_per_fraction"] * number_of_fractions):.2f}</td><td colspan="1"></td></tr><tr><td>Min</td><td>{data["min_dose_gy_per_fraction"]:.2f}</td><td>{(data["min_dose_gy_per_fraction"] * number_of_fractions):.2f}</td><td colspan="1"></td></tr>"""
        else: # OAR
            oar_rows += f"""<tr><td rowspan="3">{organ}</td><td rowspan="3">{alpha_beta}</td><td rowspan="3">{data["volume_cc"]}</td><td>D0.1cc</td><td>{data["d0_1cc_gy_per_fraction"]:.2f}</td><td>{(data["d0_1cc_gy_per_fraction"] * number_of_fractions):.2f}</td><td>{data["eqd2_d0_1cc"]:.2f}</td></tr><tr><td>D1cc</td><td>{data["d1cc_gy_per_fraction"]:.2f}</td><td>{(data["d1cc_gy_per_fraction"] * number_of_fractions):.2f}</td><td>{data["eqd2_d1cc"]:.2f}</td></tr><tr><td>D2cc</td><td>{data["d2cc_gy_per_fraction"]:.2f}</td><td>{data["total_d2cc_gy"]:.2f}</td><td>{data["eqd2_d2cc"]:.2f}</td></tr>"""

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ plan_name }}", plan_name)
    html_content = html_content.replace("{{ plan_date }}", plan_date)
    html_content = html_content.replace("{{ plan_time }}", plan_time)
    html_content = html_content.replace("{{ source_info }}", source_info)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ target_volume_rows }}", target_volume_rows)
    html_content = html_content.replace("{{ oar_rows }}", oar_rows)
    html_content = html_content.replace("{{ logo_base64 }}", logo_data_uri)

    point_dose_rows = ""
    for pr in point_dose_results:
        point_dose_rows += f"""<tr><td>{pr['name']}</td><td>{alpha_beta_ratios.get(pr['name'], alpha_beta_ratios["Default"])}</td><td>{pr['dose']:.2f}</td><td>{pr['total_dose']:.2f}</td><td>{pr['EQD2']:.2f}</td></tr>"""
    html_content = html_content.replace("{{ point_dose_rows }}", point_dose_rows)

    with open(output_path, "w") as f:
        f.write(html_content)
    
    return html_content

def main(args, selected_point_names=None, custom_constraints=None, dose_point_mapping=None, num_fractions_delivered=None):
    data_dir = Path(args.data_dir)

    if hasattr(args, 'alpha_beta_ratios') and args.alpha_beta_ratios:
        current_alpha_beta_ratios = args.alpha_beta_ratios.copy()
        if "Default" not in current_alpha_beta_ratios:
            from .config import templates
            current_alpha_beta_ratios["Default"] = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]["Default"]
    else:
        from .config import templates
        current_alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy()

    point_dose_results = []

    subdirectories = [d for d in data_dir.iterdir() if d.is_dir()]
    dose_dir = next((d for d in subdirectories if "RTDOSE" in d.name), None)
    struct_dir = next((d for d in subdirectories if "RTst" in d.name), None)
    plan_dir = next((d for d in subdirectories if "RTPLAN" in d.name), None)

    if not all([dose_dir, struct_dir, plan_dir]):
        return {"error": "Could not find all required DICOM subdirectories (RTDOSE, RTst, RTPLAN)."}

    dose_file = find_dicom_file(dose_dir)
    struct_file = find_dicom_file(struct_dir)
    plan_file = find_dicom_file(plan_dir)

    if not all([dose_file, struct_file, plan_file]):
        return {"error": "Could not find all DICOM files."}

    rt_dose_dataset = load_dicom_file(dose_file)
    rt_struct_dataset = load_dicom_file(struct_file)
    rt_plan_dataset = load_dicom_file(plan_file)

    if not all([rt_dose_dataset, rt_struct_dataset, rt_plan_dataset]):
        return {"error": "Could not load all DICOM files."}
    
    plan_data = get_plan_data(plan_file)
    number_of_fractions = plan_data.get('number_of_fractions', 1)
    brachy_dose_per_fraction = plan_data.get('brachy_dose_per_fraction', 0)
    
    # If a specific number of delivered fractions is provided, it overrides the value from the plan.
    if num_fractions_delivered is not None:
        number_of_fractions = num_fractions_delivered
    
    structure_data = get_structure_data(rt_struct_dataset)

    previous_brachy_bed_per_organ = {}
    if hasattr(args, 'previous_brachy_data') and args.previous_brachy_data:
        if isinstance(args.previous_brachy_data, str):
            # Assuming the HTML report contains EQD2 values that need to be converted to BED.
            # This part might need adjustment based on the content of the HTML report.
            previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_data)
            for organ, eqd2 in previous_brachy_eqd2_per_organ.items():
                alpha_beta = current_alpha_beta_ratios.get(organ, current_alpha_beta_ratios["Default"])
                previous_brachy_bed_per_organ[organ] = eqd2 * (1 + (2 / alpha_beta))

        elif isinstance(args.previous_brachy_data, dict):
            previous_brachy_bed_per_organ = args.previous_brachy_data

    dvh_results = get_dvh(
        struct_file, dose_file, structure_data, number_of_fractions,
        ebrt_dose=args.ebrt_dose,
        previous_brachy_bed_per_organ=previous_brachy_bed_per_organ,
        alpha_beta_ratios=current_alpha_beta_ratios
    )

    current_constraints = custom_constraints
    point_dose_constraints = current_constraints.get("point_dose_constraints") if current_constraints else None

    filtered_dose_references = []
    if selected_point_names:
        filtered_dose_references = [dr for dr in plan_data.get('dose_references', []) if dr['name'] in selected_point_names]
    else:
        filtered_dose_references = plan_data.get('dose_references', [])

    for dr in filtered_dose_references:
        total_bed, eqd2, bed_brachy, bed_ebrt, bed_previous_brachy = calculate_point_dose_bed_eqd2(
            dr['dose'], number_of_fractions, dr['name'], args.ebrt_dose,
            previous_brachy_bed=previous_brachy_bed_per_organ.get(dr['name'], 0),
            alpha_beta_ratios=current_alpha_beta_ratios
        )
        point_dose_results.append({
            'name': dr['name'], 'dose': dr['dose'], 'total_dose': dr['dose'] * number_of_fractions,
            'BED_this_plan': bed_brachy, 'BED_previous_brachy': bed_previous_brachy,
            'BED_EBRT': bed_ebrt, 'EQD2': eqd2,
        })

    constraint_evaluation = evaluate_constraints(dvh_results, point_dose_results, constraints=current_constraints, point_dose_constraints=point_dose_constraints, dose_point_mapping=dose_point_mapping)

    # --- START DEBUGGER BLOCK ---
    mapping_dict = {item[0]: item[1] for item in dose_point_mapping} if dose_point_mapping else {}
    point_dose_constraints = custom_constraints.get("point_dose_constraints", {}) if custom_constraints else {}

    print("\n--- POINT DOSE DEBUGGER ---")
    print(f"Mapping received: {mapping_dict}")
    print(f"Point constraints available: {list(point_dose_constraints.keys())}")

    for pr in point_dose_results:
        print(f"\nProcessing Point: '{pr['name']}'")
        
        status_updated = False
        mapped_constraint_name = mapping_dict.get(pr['name'])
        print(f" -> Mapped to: '{mapped_constraint_name}'")

        if mapped_constraint_name and mapped_constraint_name in point_dose_constraints:
            constraint = point_dose_constraints[mapped_constraint_name]
            print(f" -> Found Constraint: {constraint}")
            check_type = constraint.get("check_type")

            if check_type == "prescription_tolerance":
                print(" -> Constraint type is 'prescription_tolerance'. Performing check.")
                tolerance = constraint.get("tolerance", 0.0)
                prescribed_dose = plan_data.get('brachy_dose_per_fraction', 0)
                point_dose_per_fraction = pr['dose']
                
                print(f"    - Point Dose: {point_dose_per_fraction:.2f} Gy")
                print(f"    - Prescribed Dose: {prescribed_dose:.2f} Gy")
                print(f"    - Tolerance: {tolerance:.2f}")

                if prescribed_dose > 0:
                    lower_bound = prescribed_dose * (1 - tolerance)
                    upper_bound = prescribed_dose * (1 + tolerance)
                    print(f"    - Bounds: [{lower_bound:.2f}, {upper_bound:.2f}]")
                    if lower_bound <= point_dose_per_fraction <= upper_bound:
                        pr['Constraint Status'] = 'Pass'
                    else:
                        pr['Constraint Status'] = 'Fail'
                    status_updated = True
                    print(f" -> Status updated to: '{pr['Constraint Status']}'")
                else:
                    print(" -> SKIPPED: Prescribed dose is 0, cannot evaluate tolerance.")
            else:
                print(f" -> SKIPPED: Constraint check_type is '{check_type}', not 'prescription_tolerance'.")

        if not status_updated:
            point_eval_key = f"Point Dose - {pr['name']}"
            point_eval = constraint_evaluation.get(point_eval_key, {})
            pr['Constraint Status'] = point_eval.get('status', 'N/A')
            print(f" -> No specific check performed. Falling back to generic status: '{pr['Constraint Status']}'")

    print("--- END POINT DOSE DEBUGGER ---\n")
    # --- END DEBUGGER BLOCK ---


    for organ, data in dvh_results.items():
        if organ in constraint_evaluation and constraint_evaluation[organ].get("EQD2_met") == "False":
            eqd2_constraint = constraint_evaluation[organ]["EQD2_max"]
            dvh_results[organ]["dose_to_meet_constraint"] = calculate_dose_to_meet_constraint(
                eqd2_constraint, organ, number_of_fractions, args.ebrt_dose,
                previous_brachy_bed=previous_brachy_bed_per_organ.get(organ, {}).get("d2cc", 0),
                alpha_beta_ratios=current_alpha_beta_ratios
            )
        else:
            dvh_results[organ]["dose_to_meet_constraint"] = "N/A"

    plan_date_str = plan_data.get('plan_date', 'N/A')
    formatted_plan_date = f"{plan_date_str[4:6]}-{plan_date_str[6:8]}-{plan_date_str[0:4]}" if len(plan_date_str) == 8 else plan_date_str
    plan_time_str = plan_data.get('plan_time', 'N/A')
    formatted_plan_time = f"{plan_time_str[0:2]}:{plan_time_str[2:4]}:{plan_time_str[4:6]}" if len(plan_time_str) >= 6 else plan_time_str

    output_data = {
        "patient_name": str(rt_dose_dataset.PatientName),
        "patient_mrn": str(rt_dose_dataset.PatientID),
        "plan_name": plan_data.get('plan_name', 'N/A'),
        "plan_date": formatted_plan_date,
        "plan_time": formatted_plan_time,
        "source_info": plan_data.get('source_info', 'N/A'),
        "channel_mapping": plan_data.get('channel_mapping', []),
        "brachy_dose_per_fraction": brachy_dose_per_fraction,
        "number_of_fractions": number_of_fractions,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation,
        "point_dose_results": point_dose_results,
    }

    if args.output_html:
        html_content = generate_html_report(
            output_data["patient_name"], output_data["patient_mrn"], output_data["plan_name"], 
            output_data["plan_date"], output_data["plan_time"], output_data["source_info"],
            output_data["brachy_dose_per_fraction"], output_data["number_of_fractions"], 
            output_data["ebrt_dose"], output_data["dvh_results"], 
            output_data["constraint_evaluation"], plan_data.get('dose_references', []), 
            output_data["point_dose_results"], args.output_html, current_alpha_beta_ratios
        )
        output_data['html_report'] = html_content

    return output_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brachytherapy Plan Evaluator")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the directory containing the patient's DICOM files.")
    parser.add_argument("--ebrt_dose", type=float, default=0.0, help="The prescription dose of the external beam radiation therapy in Gray (Gy).")
    parser.add_argument("--previous_brachy_html", type=str, help="Path to a previous brachytherapy HTML report to incorporate its EQD2 values.")
    parser.add_argument("--output_html", type=str, help="If provided, the results will be saved to this HTML file.")
    args = parser.parse_args()
    main(args)