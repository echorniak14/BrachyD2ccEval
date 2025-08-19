import sys
import base64
from .html_parser import parse_html_report
from .dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data
from .calculations import get_dvh, evaluate_constraints, calculate_dose_to_meet_constraint, calculate_point_dose_bed_eqd2
import argparse
from pathlib import Path
import json
# from .config import alpha_beta_ratios, constraints # No longer needed as they are passed as arguments
import pdfkit

def convert_html_to_pdf(html_content, output_path, wkhtmltopdf_path=None):
    """
    Converts HTML content to a PDF file using pdfkit.
    """
    try:
        config = None
        if wkhtmltopdf_path:
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        
        options = {
            'enable-local-file-access': None
        }
        
        pdfkit.from_string(html_content, output_path, configuration=config, options=options)
    except IOError as e:
        # Re-raise the error with a more helpful message for the GUI
        raise IOError(
            "Could not locate wkhtmltopdf. Please install it and ensure it's in your system's PATH, or provide the path in the sidebar."
            "\n\nSee: https://wkhtmltopdf.org/downloads.html"
            f"\n\nOriginal error: {e}"
        )



def generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, dvh_results, constraint_evaluation, dose_references, point_dose_results, output_path, alpha_beta_ratios):
    # Ensure alpha_beta_ratios is a dictionary and has a 'Default' key
    if not isinstance(alpha_beta_ratios, dict) or "Default" not in alpha_beta_ratios:
        from .config import templates
        alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy()
    # Determine the base path for data files
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in a normal Python environment
        base_path = Path(__file__).parent

    template_path = Path(base_path) / "templates" / "report_template.html"
    logo_path = Path(base_path) / "assets" / "2020-flame-red-02.PNG"

    with open(template_path, "r") as f:
        template = f.read()

    # Read and base64 encode the logo
    try:
        with open(logo_path, "rb") as img_file:
            logo_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            logo_data_uri = f"data:image/png;base64,{logo_base64}"
    except FileNotFoundError:
        print(f"Warning: Logo file not found at {logo_path}. Image will not be displayed.")
        logo_data_uri = "" # Fallback to empty string if logo not found

    target_volume_rows = ""
    oar_rows = ""
    for organ, data in dvh_results.items():
        alpha_beta = alpha_beta_ratios.get(organ, alpha_beta_ratios["Default"])
        is_target = alpha_beta == 10

        if is_target:
            # Target Volume (HRCTV, GTV)
            # Assuming HRCTV D90, HRCTV D98, GTV D98 are evaluated in constraint_evaluation
            hrctv_d90_eval = constraint_evaluation.get("HRCTV D90", {})
            hrctv_d98_eval = constraint_evaluation.get("HRCTV D98", {})
            gtv_d98_eval = constraint_evaluation.get("GTV D98", {})

            target_volume_rows += f"""<tr>
                <td rowspan="5">{organ}</td>
                <td rowspan="5">{alpha_beta}</td>
                <td rowspan="5">{data["volume_cc"]}</td>
                <td>D98</td>
                <td>{data["d98_gy_per_fraction"]}</td>
                <td>{data["eqd2_d98"]}</td>
                <td class="{'met' if hrctv_d98_eval.get('EQD2_met_D98') == 'True' else 'not-met'}">
                    {hrctv_d98_eval.get('EQD2_status_D98', 'N/A')}
                </td>
            </tr>
            <tr>
                <td>D90</td>
                <td>{data.get("d90_gy_per_fraction", "N/A")}</td>
                <td>{data["eqd2_d90"]}</td>
                <td class="{'met' if hrctv_d90_eval.get('EQD2_met_D90') == 'True' else 'not-met'}">
                    {hrctv_d90_eval.get('EQD2_status_D90', 'N/A')}
                </td>
            </tr>
            <tr>
                <td>Max</td>
                <td>{data["max_dose_gy_per_fraction"]}</td>
                <td colspan="2"></td>
            </tr>
            <tr>
                <td>Mean</td>
                <td>{data["mean_dose_gy_per_fraction"]}</td>
                <td colspan="2"></td>
            </tr>
            <tr>
                <td>Min</td>
                <td>{data["min_dose_gy_per_fraction"]}</td>
                <td colspan="2"></td>
            </tr>"""
        else:
            # OARs
            rowspan = 3
            oar_eval = constraint_evaluation.get(organ, {})
            eqd2_status = oar_eval.get("EQD2_status", "N/A")
            eqd2_met_class = ""
            if eqd2_status == "Met":
                eqd2_met_class = "met"
            elif eqd2_status == "Warning":
                eqd2_met_class = "warning"
            elif eqd2_status == "NOT Met":
                eqd2_met_class = "not-met"

            oar_rows += f"""<tr>
                <td rowspan="{rowspan}">{organ}</td>
                <td rowspan="{rowspan}">{alpha_beta}</td>
                <td rowspan="{rowspan}">{data["volume_cc"]}</td>
                <td>D0.1cc</td>
                <td>{data["d0_1cc_gy_per_fraction"]}</td>
                <td></td>
                <td>{data["bed_d0_1cc"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d0_1cc"]}</td>
                <td></td>
                <td></td>
            </tr>
            <tr>
                <td>D1cc</td>
                <td>{data["d1cc_gy_per_fraction"]}</td>
                <td></td>
                <td>{data["bed_d1cc"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d1cc"]}</td>
                <td></td>
                <td></td>
            </tr>
            <tr>
                <td>D2cc</td>
                <td>{data["d2cc_gy_per_fraction"]}</td>
                <td>{data["total_d2cc_gy"]}</td>
                <td>{data["bed_this_plan"]}</td>
                <td>{data["bed_previous_brachy"]}</td>
                <td>{data["bed_ebrt"]}</td>
                <td>{data["eqd2_d2cc"]}</td>
                <td class="{eqd2_met_class}">{eqd2_status}</td>
                <td>{data.get("dose_to_meet_constraint", "N/A")}</td>
            </tr>"""

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ plan_name }}", plan_name)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ target_volume_rows }}", target_volume_rows)
    html_content = html_content.replace("{{ oar_rows }}", oar_rows)

    html_content = html_content.replace("{{ logo_base64 }}", logo_data_uri)

    dose_ref_rows = ""
    for dr in dose_references:
        dose_ref_rows += f"<tr><td>{dr['name']}</td><td>{dr['dose']}</td></tr>"
    html_content = html_content.replace("{{ dose_reference_rows }}", dose_ref_rows)

    point_dose_rows = ""
    for pr in point_dose_results:
        point_eval_key = f"Point Dose - {pr['name']}"
        point_eval = constraint_evaluation.get(point_eval_key, {})
        
        status = point_eval.get("status", "N/A")
        met_class = ""
        if status == "Met":
            met_class = "met"
        elif status == "NOT Met":
            met_class = "not-met"
        elif status == "Warning": # Assuming a warning status for point doses if applicable
            met_class = "warning"

        point_dose_rows += f"""<tr>
            <td>{pr['name']}</td>
            <td>{alpha_beta_ratios.get(pr['name'], alpha_beta_ratios["Default"])}</td>
            <td>{pr['dose']:.2f}</td>
            <td>{pr['total_dose']:.2f}</td>
            <td>{pr['BED_this_plan']:.2f}</td>
            <td>{pr['BED_previous_brachy']:.2f}</td>
            <td>{pr['BED_EBRT']:.2f}</td>
            <td>{pr['EQD2']:.2f}</td>
            <td class="{met_class}">{status}</td>
            <td></td>
        </tr>"""
    html_content = html_content.replace("{{ point_dose_rows }}", point_dose_rows)

    with open(output_path, "w") as f:
        f.write(html_content)
    
    return html_content

def main(args, selected_point_names=None, custom_constraints=None): # Added selected_point_names parameter
    data_dir = Path(args.data_dir)

    # Use custom alpha/beta ratios if provided, otherwise use defaults from the default template
    if hasattr(args, 'alpha_beta_ratios') and args.alpha_beta_ratios:
        current_alpha_beta_ratios = args.alpha_beta_ratios.copy()
        # Ensure 'Default' key exists, if not, add it from the template
        if "Default" not in current_alpha_beta_ratios:
            from .config import templates
            default_template_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]
            current_alpha_beta_ratios["Default"] = default_template_ratios["Default"]
    else:
        # Fallback to the default template's alpha_beta_ratios if not provided via args
        from .config import templates
        current_alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy()

    # Calculate BED and EQD2 for point doses
    point_dose_results = []

    point_dose_results = [] # Initialize point_dose_results here

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

    # Parse previous brachytherapy data if provided
    previous_brachy_eqd2_per_organ = {}
    if hasattr(args, 'previous_brachy_data') and args.previous_brachy_data:
        if isinstance(args.previous_brachy_data, str): # It's an HTML file path
            previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_data)
        elif isinstance(args.previous_brachy_data, dict): # It's parsed JSON data
            previous_brachy_eqd2_per_organ = args.previous_brachy_data

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

    current_constraints = custom_constraints
    point_dose_constraints = None
    if custom_constraints and "point_dose_constraints" in custom_constraints:
        point_dose_constraints = custom_constraints["point_dose_constraints"]
    # Evaluate constraints
    constraint_evaluation = evaluate_constraints(dvh_results, point_dose_results, constraints=current_constraints, point_dose_constraints=point_dose_constraints)

    # Add constraint status to point_dose_results
    for pr in point_dose_results:
        point_eval_key = f"Point Dose - {pr['name']}"
        point_eval = constraint_evaluation.get(point_eval_key, {})
        pr['Constraint Status'] = point_eval.get('status', 'N/A') # Add the status here

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
            'BED_this_plan': bed_brachy,
            'BED_previous_brachy': bed_previous_brachy,
            'BED_EBRT': bed_ebrt,
            'EQD2': eqd2,
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
        html_content = generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, args.ebrt_dose, dvh_results, constraint_evaluation, output_data['dose_references'], output_data['point_dose_results'], args.output_html, current_alpha_beta_ratios)
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
