import sys
import base64
import pandas as pd
from datetime import datetime
from pathlib import Path
import os
import pdfkit
from ..config import templates

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

def _get_frontend_src_path():
    """
    Helper to locate the root 'src' folder (where templates/assets/vendor live).
    Traverses up from: backend/src/services/report_generator.py -> root/src
    """
    # Current file: .../backend/src/services/report_generator.py
    # parents[0] = services
    # parents[1] = src (backend)
    # parents[2] = backend
    # parents[3] = Project Root
    project_root = Path(__file__).resolve().parents[3]
    return project_root / 'src'

def convert_html_to_pdf(html_content):
    """
    Converts HTML content to a PDF file using pdfkit and returns its bytes.
    """
    try:
        options = {'enable-local-file-access': None}
        
        # Locate wkhtmltopdf in the frontend src/vendor folder
        frontend_src = _get_frontend_src_path()
        path_wkhtmltopdf = frontend_src / 'vendor' / 'bin' / 'wkhtmltopdf.exe'
        
        if not path_wkhtmltopdf.is_file():
            # Fallback: Assume it's in system PATH
            config = pdfkit.configuration(wkhtmltopdf='wkhtmltopdf')
        else:
            config = pdfkit.configuration(wkhtmltopdf=str(path_wkhtmltopdf))
            
        pdf_html_content = replace_css_variables(html_content)
        
        # Return PDF as bytes directly
        pdf_bytes = pdfkit.from_string(pdf_html_content, False, options=options, configuration=config)
        return pdf_bytes
    except IOError as e:
        if 'wkhtmltopdf' in str(e):
             raise IOError(
                "Could not generate PDF. Issue with wkhtmltopdf executable."
                f"\nExpected Path: {path_wkhtmltopdf}"
                f"\nOriginal error: {e}"
             )
        raise e

        raise e

def format_patient_name(raw_name):
    """
    Formats DICOM name (Family^Given^Middle) to 'Given Middle Family'.
    Removes carets and extra spaces.
    Handles 'Family, Given' format as fallback.
    """
    if not raw_name: return "Unknown"
    
    s_name = str(raw_name)
    
    # Check for DICOM format with carets
    if '^' in s_name:
        parts = s_name.replace('^^', '^').split('^')
        # Filter empty parts
        parts = [p.strip() for p in parts if p.strip()]
        
        if not parts: return s_name
        
        # Standard DICOM: Family^Given^Middle
        family = parts[0]
        given = parts[1] if len(parts) > 1 else ""
        middle = parts[2] if len(parts) > 2 else ""
        
        full_name = f"{given} {middle} {family}".strip()
        return " ".join(full_name.split())

    # Check for 'Family, Given' format
    if ',' in s_name:
        parts = s_name.split(',')
        family = parts[0].strip()
        given = parts[1].strip() if len(parts) > 1 else ""
        return f"{given} {family}".strip()
        
    return s_name

def generate_html_report(patient_name, patient_mrn, plan_name, plan_date, plan_time, source_info, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, ebrt_fractions, dvh_results, constraint_evaluation, dose_references, point_dose_results, alpha_beta_ratios, previous_brachy_data=None):
    """
    Generates the HTML report string.
    """
    # Locate templates and assets in the frontend src folder
    frontend_src = _get_frontend_src_path()
    template_path = frontend_src / "templates" / "report_template.html"
    logo_path = frontend_src / "assets" / "2020-flame-red-02.PNG"

    try:
        with open(template_path, "r") as f:
            template = f.read()
    except FileNotFoundError:
        return f"Error: Template not found at {template_path}"

    try:
        with open(logo_path, "rb") as img_file:
            logo_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            logo_data_uri = f"data:image/png;base64,{logo_base64}"
    except FileNotFoundError:
        logo_data_uri = ""

    previous_fractions = 0
    if previous_brachy_data and isinstance(previous_brachy_data, dict):
        max_len = 0
        if previous_brachy_data.get("dvh_results"):
            for organ_data in previous_brachy_data["dvh_results"].values():
                for dose_list in organ_data.get("dose_fx", {}).values():
                    if isinstance(dose_list, list):
                        max_len = max(max_len, len(dose_list))
        if previous_brachy_data.get("point_dose_results"):
            for dose_list in previous_brachy_data["point_dose_results"].values():
                 if isinstance(dose_list, list):
                        max_len = max(max_len, len(dose_list))
        previous_fractions = max_len

    # Calculate max length from unified lists in dvh_results
    max_dvh_len = 0
    if dvh_results:
        for organ_data in dvh_results.values():
            doses_map = organ_data.get("doses_per_fraction", {})
            for d_list in doses_map.values():
                if isinstance(d_list, list):
                    max_dvh_len = max(max_dvh_len, len(d_list))

    total_fractions = max(previous_fractions + number_of_fractions, max_dvh_len)
    fraction_headers = "".join([f"<th>Fx {i+1} Dose (Gy)</th>" for i in range(total_fractions)])
    target_volume_rows = ""
    oar_rows = ""

    # Create case-insensitive lookup map for alpha/beta ratios
    ab_lookup = {k.lower(): v for k, v in alpha_beta_ratios.items()}

    for organ, data in dvh_results.items():
        # Try exact match first, then case-insensitive, then Default
        if organ in alpha_beta_ratios:
            alpha_beta = alpha_beta_ratios[organ]
        else:
            alpha_beta = ab_lookup.get(organ.lower(), alpha_beta_ratios.get("Default", 3.0))
            
        volume_cc = data.get("volume_cc", "N/A")
        if isinstance(volume_cc, (int, float)):
            volume_cc = f"{volume_cc:.2f}"
        
        # Determine if target based on alpha/beta (Target=10)
        is_target = alpha_beta == 10
        
        doses_per_fraction_map = data.get("doses_per_fraction", {})
        
        if is_target:
            metrics = [
                {'name': 'D98', 'dose_key': 'd98_gy_per_fraction', 'eqd2_key': 'eqd2_d98', 'list_key': 'd98'},
                {'name': 'D90', 'dose_key': 'd90_gy_per_fraction', 'eqd2_key': 'eqd2_d90', 'list_key': 'd90'}
            ]
            html_rows_for_organ = []
            for i, metric in enumerate(metrics):
                fx_doses_html = ""
                
                # Check for unified list first
                if metric['list_key'] in doses_per_fraction_map:
                    dose_list = doses_per_fraction_map[metric['list_key']]
                    fx_doses_html += "".join([f"<td>{dose:.2f}</td>" for dose in dose_list])
                else:
                    # Fallback to old logic
                    if previous_brachy_data and isinstance(previous_brachy_data, dict):
                        prev_doses = previous_brachy_data.get("dvh_results", {}).get(organ, {}).get("dose_fx", {})
                        dose_list = prev_doses.get(metric['dose_key'], [])
                        if isinstance(dose_list, list):
                            fx_doses_html += "".join([f"<td>{dose:.2f}</td>" for dose in dose_list])
                    current_dose = data.get(metric['dose_key'], 0)
                    fx_doses_html += f'<td>{current_dose:.2f}</td>' * number_of_fractions

                eqd2_val = data.get(metric['eqd2_key'], 0)
                
                row_start = f'<td rowspan="{len(metrics)}">{organ}</td><td rowspan="{len(metrics)}">{alpha_beta}</td><td rowspan="{len(metrics)}">{volume_cc}</td>' if i == 0 else ''
                html_rows_for_organ.append(
                    f'<tr>{row_start}<td>{metric["name"]}</td>{fx_doses_html}<td>{eqd2_val:.2f}</td></tr>'
                )
            target_volume_rows += "".join(html_rows_for_organ)
        else:
            metrics = [
                {'name': 'D0.1cc', 'dose_key': 'd0_1cc_gy_per_fraction', 'eqd2_key': 'eqd2_d0_1cc', 'list_key': 'd0_1cc'},
                {'name': 'D1cc', 'dose_key': 'd1cc_gy_per_fraction', 'eqd2_key': 'eqd2_d1cc', 'list_key': 'd1cc'},
                {'name': 'D2cc', 'dose_key': 'd2cc_gy_per_fraction', 'eqd2_key': 'eqd2_d2cc', 'list_key': 'd2cc'}
            ]
            html_rows_for_organ = []
            for i, metric in enumerate(metrics):
                fx_doses_html = ""
                
                # Check for unified list first
                if metric['list_key'] in doses_per_fraction_map:
                    dose_list = doses_per_fraction_map[metric['list_key']]
                    fx_doses_html += "".join([f"<td>{dose:.2f}</td>" for dose in dose_list])
                else:
                    if previous_brachy_data and isinstance(previous_brachy_data, dict):
                        prev_doses = previous_brachy_data.get("dvh_results", {}).get(organ, {}).get("dose_fx", {})
                        dose_list = prev_doses.get(metric['dose_key'], [])
                        if isinstance(dose_list, list):
                            fx_doses_html += "".join([f"<td>{dose:.2f}</td>" for dose in dose_list])
                    current_dose = data.get(metric['dose_key'], 0)
                    fx_doses_html += f'<td>{current_dose:.2f}</td>' * number_of_fractions
                
                eqd2_val = data.get(metric['eqd2_key'], 0)
                
                row_start = f'<td rowspan="{len(metrics)}">{organ}</td><td rowspan="{len(metrics)}">{alpha_beta}</td><td rowspan="{len(metrics)}">{volume_cc}</td>' if i == 0 else ''
                html_rows_for_organ.append(
                    f'<tr>{row_start}<td>{metric["name"]}</td>{fx_doses_html}<td>{eqd2_val:.2f}</td></tr>'
                )
            oar_rows += "".join(html_rows_for_organ)

    point_dose_rows = ""
    for pr in point_dose_results:
        point_fraction_cells = ""
        if previous_brachy_data and isinstance(previous_brachy_data, dict):
            prev_doses_list = previous_brachy_data.get("point_dose_results", {}).get(pr.get('name', ''), [])
            if isinstance(prev_doses_list, list):
                for dose in prev_doses_list:
                    point_fraction_cells += f"<td>{dose:.2f}</td>"
        
        current_dose = pr.get("dose", 0)
        point_fraction_cells += f'<td>{current_dose:.2f}</td>' * number_of_fractions
        # Fallback alpha_beta 3.0 if not found
        point_alpha_beta = alpha_beta_ratios.get(pr.get('name', 'Default'), 3.0)
        
        point_dose_rows += (
            f'<tr>'
            f'<td>{pr.get("name", "N/A")}</td>'
            f'<td>{point_alpha_beta}</td>'
            f'{point_fraction_cells}'
            f'<td>{pr.get("EQD2", 0):.2f}</td>'
            f'</tr>'
        )

    # --- Brachy Fractions Logic ---
    # Try to determine total fractions from history + 1 logic
    total_brachy_fractions = number_of_fractions # Fallback
    
    if previous_brachy_data and isinstance(previous_brachy_data, dict):
        # Inspect a robust key to count history length
        # 'doses_per_fraction' list length in DVH results is the best indicator of Total History
        # dvh_results structure: organ -> doses_per_fraction -> list
        # Actually, previous_brachy_data IS the 'results' JSON which contains 'dvh_results' with MERGED data?
        # NO, if we pass 'results', it has 'dvh_results' which has List of Doses.
        # The LENGTH of that list IS the Total Number of Fractions (History + Current).
        
        # Check an arbitrary key 'GTV' or 'Hrctv' or 'Bladder'
        found_fx_count = None
        pd_dvh = previous_brachy_data.get('dvh_results', {})
        for organ_key, data in pd_dvh.items():
             # Try 'dose_fx' -> generic keys
             # Data structure: { 'dose_fx': { 'd90_gy_per_fraction': [1,1,1] } }
             # or direct in old format?
             # New format Step 71 logic:
             # final_dvh[std_name] = { ..., 'dose_fx': { 'd2cc_gy_per_fraction': [list] } }
             if 'dose_fx' in data:
                 for metric_key, val_list in data['dose_fx'].items():
                     if isinstance(val_list, list):
                         found_fx_count = len(val_list)
                         break
             if found_fx_count: break
        
        if found_fx_count:
            total_brachy_fractions = found_fx_count
        else:
             # Fallback: check if 'number_of_fractions_delivered' in prev matches?
             # If prev_data is the full results, number_of_fractions_delivered might already be total?
             pass

    # --- EBRT Data Logic ---
    hist_ebrt_dose = 0.0
    hist_ebrt_fx = 0
    if previous_brachy_data and isinstance(previous_brachy_data, dict):
        hist_ebrt_dose = float(previous_brachy_data.get('ebrt_dose_input', 0.0))
        hist_ebrt_fx = int(previous_brachy_data.get('ebrt_fractions_input', 0))

    # Current (Sidebar) Input
    curr_ebrt_dose = float(ebrt_dose)
    curr_ebrt_fx = int(ebrt_fractions)

    total_ebrt_dose = hist_ebrt_dose + curr_ebrt_dose
    total_ebrt_fx = hist_ebrt_fx + curr_ebrt_fx
    
    html_content = template.replace("{{ patient_name }}", str(format_patient_name(patient_name)))
    html_content = html_content.replace("{{ patient_mrn }}", str(patient_mrn))
    html_content = html_content.replace("{{ plan_name }}", str(plan_name))
    html_content = html_content.replace("{{ plan_date }}", str(plan_date))
    html_content = html_content.replace("{{ source_info }}", str(source_info))
    
    # Used for "Total Fractions" in Brachy Box
    html_content = html_content.replace("{{ total_brachy_fractions }}", str(total_brachy_fractions))
    
    # EBRT Replacements
    html_content = html_content.replace("{{ hist_ebrt_dose }}", f"{hist_ebrt_dose:.2f}")
    html_content = html_content.replace("{{ hist_ebrt_fx }}", str(hist_ebrt_fx))
    html_content = html_content.replace("{{ curr_ebrt_dose }}", f"{curr_ebrt_dose:.2f}")
    html_content = html_content.replace("{{ curr_ebrt_fx }}", str(curr_ebrt_fx))
    html_content = html_content.replace("{{ total_ebrt_dose }}", f"{total_ebrt_dose:.2f}")
    
    html_content = html_content.replace("{{ target_volume_rows }}", target_volume_rows)

    html_content = html_content.replace("{{ oar_rows }}", oar_rows)
    html_content = html_content.replace("{{ logo_base64 }}", logo_data_uri)
    html_content = html_content.replace("{{ fraction_headers }}", fraction_headers)
    html_content = html_content.replace("{{ point_dose_rows }}", point_dose_rows)
    
    return html_content