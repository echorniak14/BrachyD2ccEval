import sys
import base64
import pandas as pd
from datetime import datetime
from openpyxl import load_workbook
import pydicom
from .html_parser import parse_html_report
from .dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data, get_dwell_times_and_positions, get_dose_data
from .calculations import get_dvh, evaluate_constraints, calculate_dose_to_meet_constraint, calculate_point_dose_bed_eqd2, get_dose_at_point, check_plan_time, calculate_bed_and_eqd2
import argparse
from pathlib import Path
import json
import os
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

def convert_html_to_pdf(html_content, output_path):
    """
    Converts HTML content to a PDF file using pdfkit.
    """
    try:
        options = {'enable-local-file-access': None}

        # Determine base path
        if getattr(sys, 'frozen', False):
            # Path in bundled app (e.g., PyInstaller)
            base_path = Path(sys._MEIPASS)
        else:
            # Path in development
            base_path = Path(os.path.dirname(os.path.abspath(__file__)))

        # Construct path to the executable
        path_wkhtmltopdf = base_path / 'vendor' / 'bin' / 'wkhtmltopdf.exe'

        if not path_wkhtmltopdf.is_file():
            raise IOError(f"wkhtmltopdf.exe not found at the expected path: {path_wkhtmltopdf}")

        config = pdfkit.configuration(wkhtmltopdf=str(path_wkhtmltopdf))

        pdf_html_content = replace_css_variables(html_content)
        pdfkit.from_string(pdf_html_content, output_path, options=options, configuration=config)
    except IOError as e:
        # The original error is now less helpful, so let's create a more specific one
        if 'wkhtmltopdf' in str(e):
             raise IOError(
                "Could not generate PDF. There might be an issue with the wkhtmltopdf executable."
                f"\nPath being used: {path_wkhtmltopdf}"
                f"\n\nOriginal error: {e}"
             )
        raise e

def generate_html_report(patient_name, patient_mrn, plan_name, plan_date, plan_time, source_info, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, ebrt_fractions, dvh_results, constraint_evaluation, dose_references, point_dose_results, output_path, alpha_beta_ratios, previous_brachy_data=None):
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

    previous_fractions = 0
    if previous_brachy_data and isinstance(previous_brachy_data, dict):
        # Assuming the number of fractions is the length of the dvh_results for the first organ
        if previous_brachy_data.get("dvh_results"):
            first_organ = list(previous_brachy_data["dvh_results"].keys())[0]
            previous_fractions = len(previous_brachy_data["dvh_results"][first_organ].get("dose_fx", []))

    total_fractions = 0
    if previous_brachy_data and isinstance(previous_brachy_data, dict):
        if previous_brachy_data.get("dvh_results"):
            first_organ = list(previous_brachy_data["dvh_results"].keys())[0]
            total_fractions = len(previous_brachy_data["dvh_results"][first_organ].get("dose_fx", {}).get("d2cc_gy_per_fraction", []))
    total_fractions += number_of_fractions

    fraction_headers = "".join([f"<th>Fx {i+1} Dose (Gy)</th>" for i in range(total_fractions)])

    target_volume_rows = ""
    oar_rows = ""
    for organ, data in dvh_results.items():
        alpha_beta = alpha_beta_ratios.get(organ, alpha_beta_ratios["Default"])
        volume_cc = data.get("volume_cc", "N/A") # Changed to volume_cc
        if isinstance(volume_cc, (int, float)):
            volume_cc = f"{volume_cc:.2f}"

        if alpha_beta == 10: # is_target
            d98_cells = ""
            d90_cells = ""
            max_cells = ""
            mean_cells = ""
            min_cells = ""

            if previous_brachy_data and isinstance(previous_brachy_data, dict):
                if organ in previous_brachy_data.get("dvh_results", {}):
                    prev_doses = previous_brachy_data["dvh_results"][organ].get("dose_fx", {})
                    d98_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("d98_gy_per_fraction", [])])
                    d90_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("d90_gy_per_fraction", [])])
                    max_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("max_dose_gy_per_fraction", [])])
                    mean_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("mean_dose_gy_per_fraction", [])])
                    min_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("min_dose_gy_per_fraction", [])])

            d98_cells += f'<td>{data.get("d98_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            d90_cells += f'<td>{data.get("d90_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            max_cells += f'<td>{data.get("max_dose_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            mean_cells += f'<td>{data.get("mean_dose_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            min_cells += f'<td>{data.get("min_dose_gy_per_fraction", 0):.2f}</td>' * number_of_fractions

            target_volume_rows += f'''<tr><td rowspan="5">{organ}</td><td rowspan="5">{alpha_beta}</td><td rowspan="5">{volume_cc}</td><td>D98</td>{d98_cells}<td>{data.get("eqd2_d98", 0):.2f}</td></tr>
                                 <tr><td>D90</td>{d90_cells}<td>{data.get("eqd2_d90", 0):.2f}</td></tr>
                                 <tr><td>Max</td>{max_cells}<td colspan="1"></td></tr>
                                 <tr><td>Mean</td>{mean_cells}<td colspan="1"></td></tr>
                                 <tr><td>Min</td>{min_cells}<td colspan="1"></td></tr>'''
        else: # OAR
            d0_1cc_cells = ""
            d1cc_cells = ""
            d2cc_cells = ""

            if previous_brachy_data and isinstance(previous_brachy_data, dict):
                if organ in previous_brachy_data.get("dvh_results", {}):
                    prev_doses = previous_brachy_data["dvh_results"][organ].get("dose_fx", {})
                    d0_1cc_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("d0_1cc_gy_per_fraction", [])])
                    d1cc_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("d1cc_gy_per_fraction", [])])
                    d2cc_cells += "".join([f"<td>{dose:.2f}</td>" for dose in prev_doses.get("d2cc_gy_per_fraction", [])])

            d0_1cc_cells += f'<td>{data.get("d0_1cc_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            d1cc_cells += f'<td>{data.get("d1cc_gy_per_fraction", 0):.2f}</td>' * number_of_fractions
            d2cc_cells += f'<td>{data.get("d2cc_gy_per_fraction", 0):.2f}</td>' * number_of_fractions

            oar_rows += f'''<tr><td rowspan="3">{organ}</td><td rowspan="3">{alpha_beta}</td><td rowspan="3">{volume_cc}</td><td>D0.1cc</td>{d0_1cc_cells}<td>{data.get("eqd2_d0_1cc", 0):.2f}</td></tr>
                           <tr><td>D1cc</td>{d1cc_cells}<td>{data.get("eqd2_d1cc", 0):.2f}</td></tr>
                           <tr><td>D2cc</td>{d2cc_cells}<td>{data.get("eqd2_d2cc", 0):.2f}</td></tr>'''

    point_dose_rows = ""
    for pr in point_dose_results:
        point_fraction_cells = ""
        if previous_brachy_data and isinstance(previous_brachy_data, dict):
            if pr['name'] in previous_brachy_data.get("point_dose_results", {}):
                prev_doses = previous_brachy_data["point_dose_results"][pr['name']].get("dose_fx", [])
                for dose in prev_doses:
                    point_fraction_cells += f"<td>{dose:.2f}</td>"
        point_fraction_cells += f'<td>{pr.get("dose", 0):.2f}</td>' * number_of_fractions
        point_dose_rows += f'''<tr><td>{pr.get('name', 'N/A')}</td><td>{alpha_beta_ratios.get(pr.get('name', 'Default'), alpha_beta_ratios["Default"])}</td>{point_fraction_cells}<td>{pr.get('EQD2', 0):.2f}</td></tr>'''

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ plan_name }}", plan_name)
    html_content = html_content.replace("{{ plan_date }}", plan_date)
    html_content = html_content.replace("{{ plan_time }}", plan_time)
    html_content = html_content.replace("{{ source_info }}", source_info)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ ebrt_fractions }}", str(ebrt_fractions))
    html_content = html_content.replace("{{ target_volume_rows }}", target_volume_rows)
    html_content = html_content.replace("{{ oar_rows }}", oar_rows)
    html_content = html_content.replace("{{ logo_base64 }}", logo_data_uri)
    html_content = html_content.replace("{{ fraction_headers }}", fraction_headers)
    html_content = html_content.replace("{{ point_dose_rows }}", point_dose_rows)

    with open(output_path, "w", encoding='utf-8') as f:
        f.write(html_content)
    
    return html_content

def pre_analysis(uploaded_files):
    with tempfile.TemporaryDirectory() as tmpdir:
        rtstruct_file_path = None
        rtplan_file_path = None

        for uploaded_file in uploaded_files:
            file_path = os.path.join(tmpdir, uploaded_file.name)
            uploaded_file.seek(0)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            try:
                ds = pydicom.dcmread(file_path)
                if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure Set Storage
                    rtstruct_file_path = file_path
                elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                    rtplan_file_path = file_path
            except Exception as e:
                print(f"Warning: Could not read DICOM file {uploaded_file.name}: {e}")

        structure_data = None
        if rtstruct_file_path:
            from .dicom_parser import get_structure_data
            rtstruct_dataset = load_dicom_file(rtstruct_file_path)
            structure_data = get_structure_data(rtstruct_dataset)

        plan_data = None
        if rtplan_file_path:
            plan_data = get_plan_data(rtplan_file_path)

        return structure_data, plan_data

from fuzzywuzzy import process

def get_structure_mapping(current_structures, json_structures):
    mapping = {}
    for current_struct in current_structures:
        match, score = process.extractOne(current_struct, json_structures)
        if score > 80: # Confidence threshold
            mapping[current_struct] = match
    return mapping

def main(args, structure_data, plan_data, selected_point_names=None, custom_constraints=None, dose_point_mapping=None, num_fractions_delivered=None, ebrt_fractions=None, structure_mapping=None, confirmed_structure_mapping=None):
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


    previous_brachy_bed_per_organ = {}
    if hasattr(args, 'previous_brachy_data') and args.previous_brachy_data:
        if isinstance(args.previous_brachy_data, str): # HTML path
            previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_data)
            for organ, eqd2 in previous_brachy_eqd2_per_organ.items():
                alpha_beta = current_alpha_beta_ratios.get(organ, current_alpha_beta_ratios["Default"])
                previous_brachy_bed_per_organ[organ] = eqd2 * (1 + (2 / alpha_beta))

        elif isinstance(args.previous_brachy_data, dict): # JSON fractional dose data
            
            # DVH results from previous JSON
            for organ, dose_fx_data in args.previous_brachy_data.get('dvh_results', {}).items():
                if organ not in previous_brachy_bed_per_organ:
                    previous_brachy_bed_per_organ[organ] = {}
                
                alpha_beta = current_alpha_beta_ratios.get(organ, current_alpha_beta_ratios["Default"])
                
                for metric, dose_list in dose_fx_data.items():
                    # The metric from JSON is like 'd2cc_gy_per_fraction', we want 'd2cc'
                    simple_metric = metric.replace('_gy_per_fraction', '')
                    total_metric_bed = 0
                    if isinstance(dose_list, list):
                        for dose_fx in dose_list:
                            # BED formula: D * (1 + d/ab) where D=d for a single fraction
                            total_metric_bed += dose_fx * (1 + dose_fx / alpha_beta)
                    previous_brachy_bed_per_organ[organ][simple_metric] = total_metric_bed

            # Point dose results from previous JSON
            for point_name, dose_list in args.previous_brachy_data.get('point_dose_results', {}).items():
                alpha_beta = current_alpha_beta_ratios.get(point_name, current_alpha_beta_ratios["Default"])
                total_point_bed = 0
                if isinstance(dose_list, list):
                    for dose_fx in dose_list:
                        total_point_bed += dose_fx * (1 + dose_fx / alpha_beta)
                previous_brachy_bed_per_organ[point_name] = total_point_bed


    dose_dir = next((d for d in Path(args.data_dir).iterdir() if d.is_dir() and "RTDOSE" in d.name), None)
    struct_dir = next((d for d in Path(args.data_dir).iterdir() if d.is_dir() and "RTst" in d.name), None)
    dose_file = find_dicom_file(dose_dir)
    struct_file = find_dicom_file(struct_dir)

    planned_number_of_fractions = plan_data.get('number_of_fractions', 1)
    number_of_fractions_for_calc = planned_number_of_fractions
    
    if num_fractions_delivered is not None:
        number_of_fractions_for_calc = num_fractions_delivered

    dvh_results = get_dvh(
        struct_file, dose_file, structure_data, number_of_fractions_for_calc,
        ebrt_dose=args.ebrt_dose,
        ebrt_fractions=ebrt_fractions,
        previous_brachy_bed_per_organ=previous_brachy_bed_per_organ,
        alpha_beta_ratios=current_alpha_beta_ratios
    )

    for organ, data in dvh_results.items():
        dose_metrics = {
            'd2cc': 'd2cc_gy_per_fraction',
            'd1cc': 'd1cc_gy_per_fraction',
            'd0_1cc': 'd0_1cc_gy_per_fraction',
            'd90': 'd90_gy_per_fraction',
            'd98': 'd98_gy_per_fraction',
            'd95': 'd95_gy_per_fraction',
            'max': 'max_dose_gy_per_fraction',
            'mean': 'mean_dose_gy_per_fraction',
            'min': 'min_dose_gy_per_fraction',
        }
        for metric_key, dose_key in dose_metrics.items():
            dose_per_fraction = data.get(dose_key, 0)
            total_dose = dose_per_fraction * number_of_fractions_for_calc
            
            previous_brachy_bed = 0
            if confirmed_structure_mapping and organ in confirmed_structure_mapping:
                json_organ = confirmed_structure_mapping[organ]
                if json_organ in previous_brachy_bed_per_organ and isinstance(previous_brachy_bed_per_organ[json_organ], dict):
                    previous_brachy_bed = previous_brachy_bed_per_organ[json_organ].get(metric_key, 0)
            elif organ in previous_brachy_bed_per_organ and isinstance(previous_brachy_bed_per_organ[organ], dict):
                previous_brachy_bed = previous_brachy_bed_per_organ[organ].get(metric_key, 0)

            total_bed, eqd2, bed_brachy, _, _ = calculate_bed_and_eqd2(
                total_dose,
                dose_per_fraction,
                organ,
                args.ebrt_dose,
                ebrt_fractions,
                previous_brachy_bed,
                current_alpha_beta_ratios
            )
            data[f'bed_{metric_key}'] = total_bed
            data[f'eqd2_{metric_key}'] = eqd2
            data[f'bed_brachy_{metric_key}'] = bed_brachy


    current_target_constraints = custom_constraints.get("constraints", {}).get("target_constraints") if custom_constraints else None
    current_oar_constraints = custom_constraints.get("constraints", {}).get("oar_constraints") if custom_constraints else None
    point_dose_constraints = custom_constraints.get("point_dose_constraints") if custom_constraints else None

    filtered_dose_references = []
    if selected_point_names:
        filtered_dose_references = [dr for dr in plan_data.get('dose_references', []) if dr['name'] in selected_point_names]
    else:
        filtered_dose_references = plan_data.get('dose_references', [])

    for dr in filtered_dose_references:
        total_bed, eqd2, bed_brachy, bed_ebrt, bed_previous_brachy = calculate_point_dose_bed_eqd2(
            dr['dose'], number_of_fractions_for_calc, dr['name'], args.ebrt_dose, ebrt_fractions,
            previous_brachy_bed=previous_brachy_bed_per_organ.get(dr['name'], 0),
            alpha_beta_ratios=current_alpha_beta_ratios
        )
        point_dose_results.append({
            'name': dr['name'], 'dose': dr['dose'], 'total_dose': dr['dose'] * number_of_fractions_for_calc,
            'BED_this_plan': bed_brachy, 'BED_previous_brachy': bed_previous_brachy,
            'BED_EBRT': bed_ebrt, 'EQD2': eqd2,
        })

    constraint_evaluation = evaluate_constraints(dvh_results, point_dose_results, target_constraints=current_target_constraints, oar_constraints=current_oar_constraints, point_dose_constraints=point_dose_constraints, dose_point_mapping=dose_point_mapping)

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
            elif "max_eqd2" in constraint:
                max_eqd2 = constraint["max_eqd2"]
                current_eqd2 = pr['EQD2']
                if current_eqd2 <= max_eqd2:
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
            # *** FIX STARTS HERE: Correctly get the previous BED for the D2cc metric ***
            prev_bed_dict = previous_brachy_bed_per_organ.get(organ, {})
            # Ensure we handle both dicts (for OARs) and floats (for points, though unlikely here)
            prev_d2cc_bed = prev_bed_dict.get('d2cc', 0) if isinstance(prev_bed_dict, dict) else 0
            
            dvh_results[organ]["dose_to_meet_constraint"] = calculate_dose_to_meet_constraint(
                eqd2_constraint, organ, number_of_fractions_for_calc, args.ebrt_dose,
                previous_brachy_bed=prev_d2cc_bed,
                alpha_beta_ratios=current_alpha_beta_ratios
            )
            # *** FIX ENDS HERE ***
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

    plan_time_warning = check_plan_time(plan_data.get('plan_time'))

    rt_dose_dataset = load_dicom_file(dose_file)

    output_data = {
        "patient_name": str(rt_dose_dataset.PatientName),
        "patient_mrn": str(rt_dose_dataset.PatientID),
        "plan_name": plan_data.get('plan_name', 'N/A'),
        "plan_date": formatted_plan_date,
        "plan_time": formatted_plan_time,
        "source_info": plan_data.get('source_info', 'N/A'),
        "channel_mapping": plan_data.get('channel_mapping', []),
        "brachy_dose_per_fraction": plan_data.get('brachy_dose_per_fraction', 0),
        "planned_number_of_fractions": planned_number_of_fractions,
        "calculation_number_of_fractions": number_of_fractions_for_calc,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation,
        "point_dose_results": point_dose_results,
        "plan_time_warning": plan_time_warning,
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