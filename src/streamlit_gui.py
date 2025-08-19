import streamlit as st
import argparse
import sys
import os
import pydicom
import pandas as pd # Added pandas import
import json # Added json import

# Add the project root to the Python path
# This is necessary for the 'src' module to be found
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.dicom_parser import get_plan_data
from src.main import main as run_analysis, convert_html_to_pdf
from src.config import templates # Added templates
import tempfile

def main():
    st.set_page_config(layout="wide")
    st.title("Brachytherapy Plan Evaluator")

    # Initialize widget_key_suffix for dynamic key generation
    if 'widget_key_suffix' not in st.session_state:
        st.session_state.widget_key_suffix = 0

    st.header("Upload DICOM Files")
    uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, and RTPLAN files", type=["dcm", "DCM"], accept_multiple_files=True)

    st.sidebar.header("Parameters")
    ebrt_dose = st.sidebar.number_input("EBRT Dose (Gy)", value=0.0)
    previous_brachy_data_file = st.sidebar.file_uploader("Upload previous brachytherapy data (optional)", type=["html", "json"])
    wkhtmltopdf_path = st.sidebar.text_input("Path to wkhtmltopdf.exe (optional)")

    st.sidebar.header("Templates")
    template_names = list(templates.keys())
    
    # Initialize current_template_name in session state
    if "current_template_name" not in st.session_state:
        st.session_state.current_template_name = "Cervix HDR - EMBRACE II" # Default template

    selected_template_name = st.sidebar.selectbox(
        "Select Template",
        options=template_names,
        index=template_names.index(st.session_state.current_template_name),
        key="template_selector"
    )

    # Update session state if a new template is selected
    if selected_template_name != st.session_state.current_template_name:
        st.session_state.current_template_name = selected_template_name
        # Reset alpha/beta ratios and constraints to the selected template's defaults
        st.session_state.ab_ratios = templates[selected_template_name]["alpha_beta_ratios"].copy()
        st.session_state.custom_constraints = templates[selected_template_name]["constraints"].copy()
        # Clear input widgets by setting a unique key for each
        st.session_state.widget_key_suffix = st.session_state.get('widget_key_suffix', 0) + 1


    # Initialize ab_ratios and custom_constraints in session state if not already present
    if "ab_ratios" not in st.session_state:
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
    if "custom_constraints" not in st.session_state:
        st.session_state.custom_constraints = templates[st.session_state.current_template_name]["constraints"].copy()

    st.sidebar.header("Alpha/Beta Ratios")

    # Reset button for alpha/beta ratios
    if st.sidebar.button("Reset Alpha/Beta Ratios to Template Defaults"):
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
        st.session_state.widget_key_suffix = st.session_state.get('widget_key_suffix', 0) + 1 # Force re-render

    # Display and update alpha/beta ratios
    for organ, val in st.session_state.ab_ratios.items():
        st.session_state.ab_ratios[organ] = st.sidebar.number_input(
            f"{organ}",
            value=float(val),
            key=f"ab_{organ}_{st.session_state.widget_key_suffix}"
        )

    st.sidebar.header("Constraints")

    # Reset constraints button
    if st.sidebar.button("Reset Constraints to Template Defaults"):
        st.session_state.custom_constraints = templates[st.session_state.current_template_name]["constraints"].copy()
        st.session_state.widget_key_suffix = st.session_state.get('widget_key_suffix', 0) + 1 # Force re-render

    # Display and update constraints
    with st.sidebar.expander("Edit Constraints"):
        for organ, organ_constraints in st.session_state.custom_constraints.items():
            st.subheader(f"{organ} Constraints")
            # Handle HRCTV D90, D98, GTV D98
            if "min" in organ_constraints and "max" in organ_constraints: # HRCTV D90
                st.session_state.custom_constraints[organ]["min"] = st.number_input(
                    f"{organ} Min (Gy)",
                    value=float(organ_constraints["min"]),
                    key=f"constraint_{organ}_min_{st.session_state.widget_key_suffix}"
                )
                st.session_state.custom_constraints[organ]["max"] = st.number_input(
                    f"{organ} Max (Gy)",
                    value=float(organ_constraints["max"]),
                    key=f"constraint_{organ}_max_{st.session_state.widget_key_suffix}"
                )
            elif "min" in organ_constraints: # HRCTV D98, GTV D98
                st.session_state.custom_constraints[organ]["min"] = st.number_input(
                    f"{organ} Min (Gy)",
                    value=float(organ_constraints["min"]),
                    key=f"constraint_{organ}_min_{st.session_state.widget_key_suffix}"
                )
            elif "D2cc" in organ_constraints: # OARs
                if "warning" in organ_constraints["D2cc"]:
                    st.session_state.custom_constraints[organ]["D2cc"]["warning"] = st.number_input(
                        f"{organ} D2cc Warning (Gy)",
                        value=float(organ_constraints["D2cc"]["warning"]),
                        key=f"constraint_{organ}_D2cc_warning_{st.session_state.widget_key_suffix}"
                    )
                st.session_state.custom_constraints[organ]["D2cc"]["max"] = st.number_input(
                    f"{organ} D2cc Max (Gy)",
                    value=float(organ_constraints["D2cc"]["max"]),
                    key=f"constraint_{organ}_D2cc_max_{st.session_state.widget_key_suffix}"
                )

    # Ensure ab_ratios is defined for use in args and DVH loop
    ab_ratios = st.session_state.ab_ratios

    # Initialize selected_point_names and available_point_names in session state at the top
    if 'available_point_names' not in st.session_state:
        st.session_state.available_point_names = []
    if 'selected_point_names' not in st.session_state:
        st.session_state.selected_point_names = []

    # Logic to handle uploaded files and extract dose references
    rtplan_file_path = None
    if uploaded_files:
        with tempfile.TemporaryDirectory() as tmpdir:
            rtdose_dir = os.path.join(tmpdir, "RTDOSE")
            rtstruct_dir = os.path.join(tmpdir, "RTst")
            rtplan_dir = os.path.join(tmpdir, "RTPLAN")

            os.makedirs(rtdose_dir)
            os.makedirs(rtstruct_dir)
            os.makedirs(rtplan_dir)

            for uploaded_file in uploaded_files:
                file_path = os.path.join(tmpdir, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                try:
                    ds = pydicom.dcmread(file_path)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': # RT Dose Storage
                        os.rename(file_path, os.path.join(rtdose_dir, uploaded_file.name))
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure Set Storage
                        os.rename(file_path, os.path.join(rtstruct_dir, uploaded_file.name))
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                        os.rename(file_path, os.path.join(rtplan_dir, uploaded_file.name))
                        rtplan_file_path = os.path.join(rtplan_dir, uploaded_file.name) # Store RTPLAN path
                except Exception as e:
                    st.warning(f"Could not read DICOM file {uploaded_file.name}: {e}")

            # Extract dose references if RTPLAN is available
            if rtplan_file_path:
                plan_data = get_plan_data(rtplan_file_path)
                dose_references = [dr['name'] for dr in plan_data.get('dose_references', [])]
                
                # Store dose_references in session state
                st.session_state.available_point_names = dose_references
            else:
                st.session_state.available_point_names = []
    else:
        st.session_state.available_point_names = [] # Clear available points if no files uploaded
        st.session_state.selected_point_names = [] # Clear selected points if no files uploaded

    # Point selection UI
    if st.session_state.available_point_names:
        st.session_state.selected_point_names = st.multiselect(
            "Select Points to Display in Report",
            options=st.session_state.available_point_names,
            default=st.session_state.available_point_names # Select all by default
        )
    else:
        st.session_state.selected_point_names = [] # No points to select

    if st.button("Run Analysis"):
        if uploaded_files:
            st.write([file.name for file in uploaded_files])
            # Re-create tmpdir and move files for analysis run
            with tempfile.TemporaryDirectory() as tmpdir_analysis:
                rtdose_dir_analysis = os.path.join(tmpdir_analysis, "RTDOSE")
                rtstruct_dir_analysis = os.path.join(tmpdir_analysis, "RTst")
                rtplan_dir_analysis = os.path.join(tmpdir_analysis, "RTPLAN")

                os.makedirs(rtdose_dir_analysis)
                os.makedirs(rtstruct_dir_analysis)
                os.makedirs(rtplan_dir_analysis)

                rtdose_path = None
                rtstruct_path = None
                rtplan_path = None

                for uploaded_file in uploaded_files:
                    file_path = os.path.join(tmpdir_analysis, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    try:
                        ds = pydicom.dcmread(file_path)
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': # RT Dose Storage
                            rtdose_path = os.path.join(rtdose_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtdose_path)
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure Set Storage
                            rtstruct_path = os.path.join(rtstruct_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtstruct_path)
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                            rtplan_path = os.path.join(rtplan_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtplan_path)
                    except Exception as e:
                        st.warning(f"Could not read DICOM file {uploaded_file.name}: {e}")

                if rtdose_path and rtstruct_path and rtplan_path:
                    previous_brachy_eqd2_data = {}
                    if previous_brachy_data_file:
                        file_extension = os.path.splitext(previous_brachy_data_file.name)[1].lower()
                        if file_extension == ".html":
                            # Save the uploaded HTML file to a temporary location
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_html_file:
                                tmp_html_file.write(previous_brachy_data_file.getbuffer())
                                previous_brachy_html_path = tmp_html_file.name
                            # Pass the path to main.py for parsing
                            previous_brachy_eqd2_data = previous_brachy_html_path
                        elif file_extension == ".json":
                            # Read and parse the JSON content
                            json_content = json.loads(previous_brachy_data_file.read().decode("utf-8"))
                            # Extract EQD2 values from the JSON structure
                            # Assuming the JSON structure has "dvh_results" with "eqd2_d2cc" for each organ
                            for organ, data in json_content.get("dvh_results", {}).items():
                                previous_brachy_eqd2_data[organ] = data.get("eqd2_d2cc", 0.0)
                            # Also check point dose results if needed for accumulation
                            for point_data in json_content.get("point_dose_results", {}):
                                previous_brachy_eqd2_data[point_data["name"]] = point_data.get("EQD2", 0.0)
                        
                    args = argparse.Namespace(
                        data_dir=tmpdir_analysis, # Use the new tmpdir for analysis
                        ebrt_dose=ebrt_dose,
                        previous_brachy_data=previous_brachy_eqd2_data, # Pass parsed data or path
                        output_html=os.path.join(tmpdir_analysis, "report.html"),
                        alpha_beta_ratios=ab_ratios,
                        selected_point_names=st.session_state.selected_point_names, # Pass selected points
                        custom_constraints=st.session_state.custom_constraints # Pass custom constraints
                    )

                    results = run_analysis(args, selected_point_names=st.session_state.selected_point_names)

                    st.header("Results")

                    st.write(f"**Patient Name:** {results['patient_name']}")
                    st.write(f"**Patient MRN:** {results['patient_mrn']}")
                    st.write(f"**Plan Name:** {results['plan_name']}")

                    tab1, tab2, tab3 = st.tabs(["DVH Results", "Point Dose Results", "Report"])

                    with tab1:
                        st.subheader("Target Volume DVH Results")
                        target_dvh_data = []
                        oar_dvh_data = []

                        for organ, data in results["dvh_results"].items():
                            alpha_beta = ab_ratios.get(organ, ab_ratios.get("Default"))
                            is_target = alpha_beta == 10

                            if is_target:
                                target_dvh_data.append({
                                    "Organ": organ,
                                    "Volume (cc)": data["volume_cc"],
                                    "D98 (Gy)": data["d98_gy_per_fraction"],
                                    "D90 (Gy)": data["d90_gy_per_fraction"],
                                    "Max Dose (Gy)": data["max_dose_gy_per_fraction"],
                                    "Mean Dose (Gy)": data["mean_dose_gy_per_fraction"],
                                    "Min Dose (Gy)": data["min_dose_gy_per_fraction"],
                                })
                            else:
                                # Get constraint evaluation for OARs
                                constraint_status = "N/A"
                                dose_to_meet = "N/A"
                                if organ in results["constraint_evaluation"] and "EQD2_met" in results["constraint_evaluation"][organ]:
                                    constraint_status = "Met" if results["constraint_evaluation"][organ]["EQD2_met"] == "True" else "NOT Met"
                                    dose_to_meet = data.get("dose_to_meet_constraint", "N/A")

                                # D0.1cc row
                                oar_dvh_data.append({
                                    "Organ": organ,
                                    "Volume (cc)": data["volume_cc"],
                                    "Dose Metric": "D0.1cc",
                                    "Dose (Gy)": data["d0_1cc_gy_per_fraction"],
                                    "BED (Gy)": data["bed_d0_1cc"],
                                    "EQD2 (Gy)": data["eqd2_d0_1cc"],
                                    "Constraint Met": "", # Only for D2cc
                                    "Dose to Meet Constraint (Gy)": "", # Only for D2cc
                                    "Constraint Status": constraint_status # Hidden column for styling
                                })
                                # D1cc row
                                oar_dvh_data.append({
                                    "Organ": organ,
                                    "Volume (cc)": "", # Mimic rowspan
                                    "Dose Metric": "D1cc",
                                    "Dose (Gy)": data["d1cc_gy_per_fraction"],
                                    "BED (Gy)": data["bed_d1cc"],
                                    "EQD2 (Gy)": data["eqd2_d1cc"],
                                    "Constraint Met": "", # Only for D2cc
                                    "Dose to Meet Constraint (Gy)": "", # Only for D2cc
                                    "Constraint Status": constraint_status # Hidden column for styling
                                })
                                # D2cc row
                                oar_dvh_data.append({
                                    "Organ": organ,
                                    "Volume (cc)": "", # Mimic rowspan
                                    "Dose Metric": "D2cc",
                                    "Dose (Gy)": data["d2cc_gy_per_fraction"],
                                    "BED (Gy)": data["bed_d2cc"],
                                    "EQD2 (Gy)": data["eqd2_d2cc"],
                                    "Constraint Met": constraint_status,
                                    "Dose to Meet Constraint (Gy)": dose_to_meet,
                                    "Constraint Status": constraint_status # Hidden column for styling
                                })
                        
                        if target_dvh_data:
                            st.dataframe(pd.DataFrame(target_dvh_data))
                        else:
                            st.info("No target volume DVH data available.")

                        st.subheader("OAR DVH Results")
                        if oar_dvh_data:
                            oar_df = pd.DataFrame(oar_dvh_data)
                            
                            def highlight_constraint_status(row):
                                organ = row["Organ"] # Directly use row["Organ"]
                                eqd2_value = row["EQD2 (Gy)"]
                                
                                # Get the current constraints from session state
                                current_constraints = st.session_state.custom_constraints
                                
                                # Apply color coding only for D2cc rows
                                if row["Dose Metric"] == "D2cc" and organ in current_constraints and "D2cc" in current_constraints[organ]:
                                    constraint_data = current_constraints[organ]["D2cc"]
                                    max_constraint = constraint_data["max"]
                                    warning_constraint = constraint_data.get("warning") # Get warning if it exists

                                    if eqd2_value > max_constraint:
                                        return ['background-color: #dc3545; color: white'] * len(row) # Reddish (NOT Met)
                                    elif warning_constraint is not None and eqd2_value >= warning_constraint and eqd2_value <= max_constraint:
                                        return ['background-color: #ffc107; color: black'] * len(row) # Yellowish (Warning)
                                    elif eqd2_value < warning_constraint if warning_constraint is not None else eqd2_value <= max_constraint:
                                        return ['background-color: #28a745; color: white'] * len(row) # Greenish (Met)
                                # If not a D2cc row or no constraint applies, return transparent background
                                return ['background-color: transparent'] * len(row)

                            st.dataframe(oar_df.style.apply(highlight_constraint_status, axis=1))
                        else:
                            st.info("No OAR DVH data available.")

                    with tab2:
                        st.subheader("Point Dose Results")
                        st.table(results["point_dose_results"])
                    
                    with tab3:
                        st.subheader("Report")
                        html_report = results.get('html_report', '')
                        if html_report:
                            st.components.v1.html(html_report, height=600, scrolling=True)
                            
                            # Prepare data for JSON export
                            export_data = {
                                "dvh_results": results["dvh_results"],
                                "point_dose_results": results["point_dose_results"]
                            }
                            json_export_str = json.dumps(export_data, indent=4)

                            st.download_button(
                                label="Download Brachy Data (JSON)",
                                data=json_export_str,
                                file_name="brachy_data.json",
                                mime="application/json"
                            )

                            try:
                                pdf_path = os.path.join(tmpdir_analysis, "report.pdf")
                                convert_html_to_pdf(html_report, pdf_path, wkhtmltopdf_path=wkhtmltopdf_path)

                                with open(pdf_path, "rb") as f:
                                    pdf_bytes = f.read()
                                
                                st.download_button(
                                    label="Download PDF",
                                    data=pdf_bytes,
                                    file_name="report.pdf",
                                    mime="application/pdf"
                                )
                            except IOError as e:
                                st.error(
                                    "Could not generate PDF. This is likely because the 'wkhtmltopdf' executable was not found."
                                    "\n\nPlease install 'wkhtmltopdf' and ensure it is in your system's PATH."
                                    "\n\nSee the installation guide: https://wkhtmltopdf.org/downloads.html"
                                    f"\n\n**Error details:**\n\n{e}"
                                )
                        else:
                            st.warning("Could not generate HTML report.")

                else:
                    st.error("Please upload all required DICOM files (RTDOSE, RTSTRUCT, RTPLAN).")
        else:
            st.error("Please upload DICOM files.")

if __name__ == "__main__":
    main()
