import sys
import base64
import pandas as pd
from datetime import datetime
from openpyxl import load_workbook
import pydicom
from .html_parser import parse_html_report
from .dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data, get_dose_data, get_dwell_times_and_positions
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

    fraction_headers = "".join([f"<th>Fraction {i+1} Dose (Gy)</th>" for i in range(number_of_fractions)])

    target_volume_rows = ""
    oar_rows = ""
    for organ, data in dvh_results.items():
        alpha_beta = alpha_beta_ratios.get(organ, alpha_beta_ratios["Default"])
        if alpha_beta == 10: # is_target
            # Generate fraction dose cells for target volumes
            target_fraction_dose_cells_d98 = "".join([f"<td>{data['d98_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])
            target_fraction_dose_cells_d90 = "".join([f"<td>{data.get('d90_gy_per_fraction', 0):.2f}</td>" for _ in range(number_of_fractions)])
            target_fraction_dose_cells_max = "".join([f"<td>{data['max_dose_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])
            target_fraction_dose_cells_mean = "".join([f"<td>{data['mean_dose_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])
            target_fraction_dose_cells_min = "".join([f"<td>{data['min_dose_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])

            target_volume_rows += f"""<tr><td rowspan="5">{organ}</td><td rowspan="5">{alpha_beta}</td><td rowspan="5">{data["volume_cc"]}</td><td>D98</td>{target_fraction_dose_cells_d98}<td>{data["eqd2_d98"]:.2f}</td></tr><tr><td>D90</td>{target_fraction_dose_cells_d90}<td>{data["eqd2_d90"]:.2f}</td></tr><tr><td>Max</td>{target_fraction_dose_cells_max}<td colspan="1"></td></tr><tr><td>Mean</td>{target_fraction_dose_cells_mean}<td colspan="1"></td></tr><tr><td>Min</td>{target_fraction_dose_cells_min}<td colspan="1"></td></tr>"""
        else: # OAR
            # Generate fraction dose cells for OARs
            oar_fraction_dose_cells_d0_1cc = "".join([f"<td>{data['d0_1cc_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])
            oar_fraction_dose_cells_d1cc = "".join([f"<td>{data['d1cc_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])
            oar_fraction_dose_cells_d2cc = "".join([f"<td>{data['d2cc_gy_per_fraction']:.2f}</td>" for _ in range(number_of_fractions)])

            oar_rows += f"""<tr><td rowspan="3">{organ}</td><td rowspan="3">{alpha_beta}</td><td rowspan="3">{data["volume_cc"]}</td><td>D0.1cc</td>{oar_fraction_dose_cells_d0_1cc}<td>{data["eqd2_d0_1cc"]:.2f}</td></tr><tr><td>D1cc</td>{oar_fraction_dose_cells_d1cc}<td>{data["eqd2_d1cc"]:.2f}</td></tr><tr><td>D2cc</td>{oar_fraction_dose_cells_d2cc}<td>{data["eqd2_d2cc"]:.2f}</td></tr>"""

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
    html_content = html_content.replace("{{ fraction_headers }}", fraction_headers)

    point_dose_rows = ""
    for pr in point_dose_results:
        # Generate fraction dose cells for point doses
        point_fraction_dose_cells = "".join([f"<td>{pr['dose']:.2f}</td>" for _ in range(number_of_fractions)])
        point_dose_rows += f"""<tr><td>{pr['name']}</td><td>{alpha_beta_ratios.get(pr['name'], alpha_beta_ratios["Default"])}</td>{point_fraction_dose_cells}<td>{pr['EQD2']:.2f}</td></tr>"""
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
    
    # --- CORRECTED LOGIC ---
    # Store the original planned number of fractions from the DICOM file.
    planned_number_of_fractions = plan_data.get('number_of_fractions', 1)
    
    # Use a separate variable for calculations. Default to the planned value.
    number_of_fractions_for_calc = planned_number_of_fractions
    
    # If a specific number of delivered fractions is provided by the user, it overrides the value for calculations.
    if num_fractions_delivered is not None:
        number_of_fractions_for_calc = num_fractions_delivered
    # --- END CORRECTION ---

    brachy_dose_per_fraction = plan_data.get('brachy_dose_per_fraction', 0)
    structure_data = get_structure_data(rt_struct_dataset)

    previous_brachy_bed_per_organ = {}
    if hasattr(args, 'previous_brachy_data') and args.previous_brachy_data:
        if isinstance(args.previous_brachy_data, str):
            previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_data)
            for organ, eqd2 in previous_brachy_eqd2_per_organ.items():
                alpha_beta = current_alpha_beta_ratios.get(organ, current_alpha_beta_ratios["Default"])
                previous_brachy_bed_per_organ[organ] = eqd2 * (1 + (2 / alpha_beta))

        elif isinstance(args.previous_brachy_data, dict):
            previous_brachy_bed_per_organ = args.previous_brachy_data

    dvh_results = get_dvh(
        struct_file, dose_file, structure_data, number_of_fractions_for_calc,
        ebrt_dose=args.ebrt_dose,
        previous_brachy_bed_per_organ=previous_brachy_bed_per_organ,
        alpha_beta_ratios=current_alpha_beta_ratios
    )

    current_constraints = custom_constraints.get("constraints")
    point_dose_constraints = custom_constraints.get("point_dose_constraints") if custom_constraints else None

    filtered_dose_references = []
    if selected_point_names:
        filtered_dose_references = [dr for dr in plan_data.get('dose_references', []) if dr['name'] in selected_point_names]
    else:
        filtered_dose_references = plan_data.get('dose_references', [])

    for dr in filtered_dose_references:
        total_bed, eqd2, bed_brachy, bed_ebrt, bed_previous_brachy = calculate_point_dose_bed_eqd2(
            dr['dose'], number_of_fractions_for_calc, dr['name'], args.ebrt_dose,
            previous_brachy_bed=previous_brachy_bed_per_organ.get(dr['name'], 0),
            alpha_beta_ratios=current_alpha_beta_ratios
        )
        point_dose_results.append({
            'name': dr['name'], 'dose': dr['dose'], 'total_dose': dr['dose'] * number_of_fractions_for_calc,
            'BED_this_plan': bed_brachy, 'BED_previous_brachy': bed_previous_brachy,
            'BED_EBRT': bed_ebrt, 'EQD2': eqd2,
        })

    constraint_evaluation = evaluate_constraints(dvh_results, point_dose_results, constraints=current_constraints, point_dose_constraints=point_dose_constraints, dose_point_mapping=dose_point_mapping)

    mapping_dict = {item[0]: item[1] for item in dose_point_mapping} if dose_point_mapping else {}
    point_dose_constraints = custom_constraints.get("point_dose_constraints", {}) if custom_constraints else {}

    for pr in point_dose_results:
        status_updated = False
        mapped_constraint_name = mapping_dict.get(pr['name'])
        if mapped_constraint_name and mapped_constraint_name in point_dose_constraints:
            constraint = point_dose_constraints[mapped_constraint_name]
            check_type = constraint.get("check_type")
            if check_type == "prescription_tolerance":
                tolerance = constraint.get("tolerance", 0.0)
                prescribed_dose = plan_data.get('brachy_dose_per_fraction', 0)
                point_dose_per_fraction = pr['dose']
                if prescribed_dose > 0:
                    lower_bound = prescribed_dose * (1 - tolerance)
                    upper_bound = prescribed_dose * (1 + tolerance)
                    if lower_bound <= point_dose_per_fraction <= upper_bound:
                        pr['Constraint Status'] = 'Pass'
                    else:
                        pr['Constraint Status'] = 'Fail'
                    status_updated = True
        if not status_updated:
            point_eval_key = f"Point Dose - {pr['name']}"
            point_eval = constraint_evaluation.get(point_eval_key, {})
            pr['Constraint Status'] = point_eval.get('status', 'N/A')

    for organ, data in dvh_results.items():
        if organ in constraint_evaluation and constraint_evaluation[organ].get("EQD2_met") == "False":
            eqd2_constraint = constraint_evaluation[organ]["EQD2_max"]
            dvh_results[organ]["dose_to_meet_constraint"] = calculate_dose_to_meet_constraint(
                eqd2_constraint, organ, number_of_fractions_for_calc, args.ebrt_dose,
                previous_brachy_bed=previous_brachy_bed_per_organ.get(organ, {}).get("d2cc", 0),
                alpha_beta_ratios=current_alpha_beta_ratios
            )
        else:
            dvh_results[organ]["dose_to_meet_constraint"] = "N/A"

    source_strength_ref_date = plan_data.get('source_strength_ref_date', 'N/A')
    source_strength_ref_time = plan_data.get('source_strength_ref_time', 'N/A')

    if source_strength_ref_date != 'N/A' and source_strength_ref_time != 'N/A':
        plan_datetime = datetime.strptime(f"{source_strength_ref_date}{source_strength_ref_time.split('.')[0]}", "%Y%m%d%H%M%S")
        formatted_plan_date = plan_datetime.strftime('%Y-%m-%d')
        formatted_plan_time = plan_datetime.strftime('%H:%M:%S')
    else:
        formatted_plan_date = 'N/A'
        formatted_plan_time = 'N/A'

    output_data = {
        "patient_name": str(rt_dose_dataset.PatientName),
        "patient_mrn": str(rt_dose_dataset.PatientID),
        "plan_name": plan_data.get('plan_name', 'N/A'),
        "plan_date": formatted_plan_date,
        "plan_time": formatted_plan_time,
        "source_info": plan_data.get('source_info', 'N/A'),
        "channel_mapping": plan_data.get('channel_mapping', []),
        "brachy_dose_per_fraction": brachy_dose_per_fraction,
        "planned_number_of_fractions": planned_number_of_fractions,
        "calculation_number_of_fractions": number_of_fractions_for_calc,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation,
        "point_dose_results": point_dose_results,
    }

    if args.output_html:
        html_content = generate_html_report(
            output_data["patient_name"], output_data["patient_mrn"], output_data["plan_name"], 
            output_data["plan_date"], output_data["plan_time"], output_data["source_info"],
            output_data["brachy_dose_per_fraction"], output_data["calculation_number_of_fractions"], 
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

def generate_dwell_time_sheet(mosaiq_schedule_path, rtplan_file, output_excel_path):
    """
    Generates a dwell time decay sheet from a Mosaiq schedule and an RTPLAN file.
    """
    # --- Helper Function from test_schedule_parser.py ---
    def parse_mosaiq_schedule_for_hdr_tx(file_path):
        try:
            df = pd.read_excel(file_path)
            hdr_tx_schedule = df[
                df['Activity'].str.contains('HDR', case=False, na=False) &
                df['Description'].str.contains('tx', case=False, na=False)
            ].copy()
            hdr_tx_schedule = hdr_tx_schedule[~hdr_tx_schedule['Sts'].str.contains('X', na=False)]
            hdr_tx_schedule['Date'] = pd.to_datetime(hdr_tx_schedule['Date'], errors='coerce')
            hdr_tx_schedule['Time'] = hdr_tx_schedule['Time'].astype(str)
            hdr_tx_schedule.dropna(subset=['Date'], inplace=True)
            hdr_tx_schedule['datetime'] = pd.to_datetime(
                hdr_tx_schedule['Date'].dt.strftime('%Y-%m-%d') + ' ' + hdr_tx_schedule['Time']
            )
            return sorted(hdr_tx_schedule['datetime'].tolist())
        except Exception as e:
            print(f"Error parsing Mosaiq schedule file: {e}")
            return []

    # --- Main logic from test_schedule_parser.py ---
    template_excel_path = r'sample_data/Dwell time decay Worksheet Cylinder.xlsx' # This path needs to be relative to the project root

    fraction_datetimes = parse_mosaiq_schedule_for_hdr_tx(mosaiq_schedule_path)
    if not fraction_datetimes:
        print("No 'HDR: tx' activities found in the schedule. Exiting.")
        return

    patient_name = "N/A"
    patient_mrn = "N/A"
    plan_name = "N/A"
    plan_date_str = "N/A"

    if rtplan_file:
        rtplan_dataset = pydicom.dcmread(rtplan_file)
        patient_name = str(rtplan_dataset.PatientName)
        patient_mrn = str(rtplan_dataset.PatientID)
        plan_data = get_plan_data(rtplan_file)
        plan_name = plan_data.get('plan_name', 'N/A')
        source_strength_ref_date = plan_data.get('source_strength_ref_date', 'N/A')
        source_strength_ref_time = plan_data.get('source_strength_ref_time', 'N/A')
        if source_strength_ref_date != 'N/A' and source_strength_ref_time != 'N/A':
            plan_datetime = datetime.strptime(f"{source_strength_ref_date}{source_strength_ref_time.split('.')[0]}", "%Y%m%d%H%M%S")
            plan_date_str = plan_datetime.strftime('%Y-%m-%d %H:%M')
        else:
            plan_date_str = "N/A"
        
        rakr = plan_data.get('rakr', 0.0)
        source_activity_ci = rakr / 4.0367 / 1000
    else:
        source_activity_ci = 0.0


    try:
        wb = load_workbook(template_excel_path)
        ws = wb.active

        ws['B5'] = patient_name
        ws['B6'] = patient_mrn
        ws['B7'] = plan_name
        ws['B11'] = plan_date_str

        fraction_cells = ['C11', 'D11', 'E11', 'F11', 'G11']
        for i, dt in enumerate(fraction_datetimes):
            if i < len(fraction_cells):
                ws[fraction_cells[i]] = dt.strftime('%Y-%m-%d %H:%M')

        ws['B9'] = "Plan"
        header_cells = ['C9', 'D9', 'E9', 'F9', 'G9']
        for i in range(len(fraction_datetimes)):
             if i < len(header_cells):
                ws[header_cells[i]] = i + 1
        
        ws['B13'] = source_activity_ci
        
        dwell_data = get_dwell_times_and_positions(rtplan_file)
        
        # Create a map of Excel position to dwell time based on the user's mapping
        excel_dwell_map = {300 - int(item['position']): item['dwell_time'] for item in dwell_data}

        dwell_time_start_row = 17
        for i in range(12): # Template has 12 rows for dwell times
            position_cell = f'A{dwell_time_start_row + i}'
            dwell_time_cell = f'B{dwell_time_start_row + i}'
            
            position = ws[position_cell].value
            if position is not None and position in excel_dwell_map:
                ws[dwell_time_cell] = excel_dwell_map[position]
            else:
                ws[dwell_time_cell] = 0.0

        wb.save(output_excel_path)

    except FileNotFoundError:
        print(f"Error: The template file was not found at '{template_excel_path}'.")
    except Exception as e:
        print(f"An error occurred while populating the Excel template: {e}")