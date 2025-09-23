import streamlit as st
import argparse
import sys
import os
import pydicom
import pandas as pd
import json

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.dicom_parser import get_plan_data, get_dose_point_mapping
from src.main import main as run_analysis, convert_html_to_pdf
from src.config import templates
import tempfile

def main():
    st.set_page_config(layout="wide")
    
    # Injected CSS
    st.markdown("""
    <style>
        /* Target headers in the main page */
        [data-testid="stHeader"] + [data-testid="stHorizontalBlock"] {
            margin-top: -25px;
        }
        /* Target headers in the sidebar */
        [data-testid="stSidebar"] [data-testid="stHeader"] + [data-testid="stHorizontalBlock"] {
            margin-top: -25px;
        }
        /* Define the style for the results section container */
        .results-container {
            background-color: #e9ecef; /* A darker grey background */
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #e6e6e6;
        }
        /* Style for expander headers to match h2 */
        summary > div[data-testid="stMarkdownContainer"] p {
            font-size: 1.5rem; /* Equivalent to h2 font size */
            font-weight: 600; /* Equivalent to h2 font weight */
        }
    </style>
    """, unsafe_allow_html=True)
    # Custom CSS to change header colors
    st.markdown("""
    <style>
    h1, h2, h3, h4, h5, h6, summary {
        color: #FF5733 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.title("Brachytherapy Evaluation and Analysis Module")

    st.markdown("""
    This tool allows you to analyze and evaluate brachytherapy treatment plans.

    **Instructions:**

    1.  **Upload DICOM Files:** Use the file uploader below to select the RTDOSE, RTSTRUCT, and RTPLAN files for the plan you want to evaluate.
    2.  **Select Constraint Template:** Choose a constraint template from the dropdown menu.
    3.  **Set Parameters:** After uploading DICOM files, you can set optional parameters like EBRT dose and previous brachytherapy data.
    4.  **Run Analysis:** Click the "Run Analysis" button to process the files and view the results.
    5.  **View Results:** The results will be displayed in tabs, including DVH data, point doses, and a downloadable PDF report.
    """)

    # Initialize widget_key_suffix for dynamic key generation
    if 'widget_key_suffix' not in st.session_state:
        st.session_state.widget_key_suffix = 0

    st.header("Upload DICOM Files")
    uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, and RTPLAN files", type=["dcm", "DCM"], accept_multiple_files=True)

    if uploaded_files:
        rtplan_count = 0
        rtstruct_count = 0
        rtdose_count = 0

        for uploaded_file in uploaded_files:
            try:
                uploaded_file.seek(0)
                ds = pydicom.dcmread(uploaded_file, stop_before_pixels=True)
                sop_class_uid = ds.SOPClassUID
                if sop_class_uid == '1.2.840.10008.5.1.4.1.1.481.5':
                    rtplan_count += 1
                elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.481.3':
                    rtstruct_count += 1
                elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.481.2':
                    rtdose_count += 1
            except Exception:
                # Not a valid DICOM file, skip
                pass
            finally:
                uploaded_file.seek(0)

        if rtplan_count > 1:
            st.warning(f"Warning: {rtplan_count} RTPLAN files were uploaded. Please upload only one.")
        if rtstruct_count > 1:
            st.warning(f"Warning: {rtstruct_count} RTSTRUCT files were uploaded. Please upload only one.")
        if rtdose_count > 1:
            st.warning(f"Warning: {rtdose_count} RTDOSE files were uploaded. Please upload only one.")

    st.header("Constraint Template")
    template_names = list(templates.keys())
    
    # Initialize current_template_name in session state
    if "current_template_name" not in st.session_state:
        st.session_state.current_template_name = "Cervix HDR - EMBRACE II" # Default template

    selected_template_name = st.selectbox(
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
        # Clear manual mapping when template changes
        if 'manual_mapping' in st.session_state:
            del st.session_state['manual_mapping']

    # Initialize ab_ratios and custom_constraints in session state if not already present
    if "ab_ratios" not in st.session_state:
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
    if "custom_constraints" not in st.session_state:
        st.session_state.custom_constraints = templates[st.session_state.current_template_name]["constraints"].copy()

    # Initialize selected_point_names and available_point_names in session state at the top
    if 'available_point_names' not in st.session_state:
        st.session_state.available_point_names = []
    if 'selected_point_names' not in st.session_state:
        st.session_state.selected_point_names = []

    # These will be populated from the UI later
    ebrt_dose = 0.0
    previous_brachy_data_file = None
    num_fractions_delivered = 1


    if st.session_state.current_template_name == "Custom":
        with st.expander("Customize Template", expanded=True):
            st.header("Alpha/Beta Ratios")

            # Reset button for alpha/beta ratios
            if st.button("Reset Alpha/Beta Ratios to Template Defaults"):
                st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
                st.session_state.widget_key_suffix = st.session_state.get('widget_key_suffix', 0) + 1 # Force re-render

            # Display and update alpha/beta ratios
            for organ, val in st.session_state.ab_ratios.items():
                st.session_state.ab_ratios[organ] = st.number_input(
                    f"{organ}",
                    value=float(val),
                    key=f"ab_{organ}_{st.session_state.widget_key_suffix}"
                )

            st.header("Constraints")

            # Reset constraints button
            if st.button("Reset Constraints to Template Defaults"):
                st.session_state.custom_constraints = templates[st.session_state.current_template_name]["constraints"].copy()
                st.session_state.widget_key_suffix = st.session_state.get('widget_key_suffix', 0) + 1 # Force re-render

            # Separate constraints into target and OAR
            target_constraints = st.session_state.custom_constraints.get("target_constraints", {})
            oar_constraints = st.session_state.custom_constraints.get("oar_constraints", {})

            # Display and update constraints for Custom template
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Target Volumes")
                for organ, organ_constraints in target_constraints.items():
                    st.write(f"**{organ}**")
                    if "min" in organ_constraints:
                        st.session_state.custom_constraints["target_constraints"][organ]["min"] = st.number_input(
                            f"Min (Gy)",
                            value=float(organ_constraints["min"]),
                            key=f"constraint_{organ}_min_{st.session_state.widget_key_suffix}"
                        )
                    if "max" in organ_constraints:
                        st.session_state.custom_constraints["target_constraints"][organ]["max"] = st.number_input(
                            f"Max (Gy)",
                            value=float(organ_constraints["max"]),
                            key=f"constraint_{organ}_max_{st.session_state.widget_key_suffix}"
                        )
                    if "D90" in organ_constraints:
                        st.session_state.custom_constraints["target_constraints"][organ]["D90"] = st.number_input(
                            f"D90 (Gy)",
                            value=float(organ_constraints["D90"]),
                            key=f"constraint_{organ}_D90_{st.session_state.widget_key_suffix}"
                        )
                    if "D98" in organ_constraints:
                        st.session_state.custom_constraints["target_constraints"][organ]["D98"] = st.number_input(
                            f"D98 (Gy)",
                            value=float(organ_constraints["D98"]),
                            key=f"constraint_{organ}_D98_{st.session_state.widget_key_suffix}"
                        )

            with col2:
                st.subheader("Organs at Risk")
                for organ, organ_constraints in oar_constraints.items():
                    st.write(f"**{organ}**")
                    if "warning" in organ_constraints["D2cc"]:
                        st.session_state.custom_constraints["oar_constraints"][organ]["D2cc"]["warning"] = st.number_input(
                            f"D2cc Warning (Gy)",
                            value=float(organ_constraints["D2cc"]["warning"]),
                            key=f"constraint_{organ}_D2cc_warning_{st.session_state.widget_key_suffix}"
                        )
                    st.session_state.custom_constraints["oar_constraints"][organ]["D2cc"]["max"] = st.number_input(
                        f"D2cc Max (Gy)",
                        value=float(organ_constraints["D2cc"]["max"]),
                        key=f"constraint_{organ}_D2cc_max_{st.session_state.widget_key_suffix}"
                    )
    
    st.sidebar.header("Loaded EQD2 Constraints")
    target_constraints = st.session_state.custom_constraints.get("target_constraints", {})
    oar_constraints = st.session_state.custom_constraints.get("oar_constraints", {})
    st.sidebar.subheader("Target Volumes")
    for organ, organ_constraints in target_constraints.items():
        col_left, col_right = st.sidebar.columns([0.4, 1])
        with col_left:
            st.sidebar.write(f"**{organ} (α/β = {st.session_state.ab_ratios.get(organ.split(' ')[0], 'N/A')})**")
        with col_right:
            if "min" in organ_constraints and "max" in organ_constraints:
                st.sidebar.write(f"Min: {organ_constraints['min']} Gy, Max: {organ_constraints['max']} Gy")
            elif "min" in organ_constraints:
                st.sidebar.write(f"Min: {organ_constraints['min']} Gy")
    st.sidebar.subheader("Organs at Risk")
    for organ, organ_constraints in oar_constraints.items():
        col_left, col_right = st.sidebar.columns([0.4, 1])
        with col_left:
            st.sidebar.write(f"**{organ} (α/β = {st.session_state.ab_ratios.get(organ.split(' ')[0], 'N/A')})**")
        with col_right:
            if "warning" in organ_constraints["D2cc"]:
                st.sidebar.write(f"D2cc Warning: {organ_constraints['D2cc']['warning']} Gy, Max: {organ_constraints['D2cc']['max']} Gy")
            else:
                st.sidebar.write(f"D2cc Max: {organ_constraints['D2cc']['max']} Gy")

    if uploaded_files:
        # --- Get patient info from the first DICOM file ---
        if 'patient_info' not in st.session_state or st.session_state.get("last_uploaded_files") != "_".join(sorted([f.name for f in uploaded_files])):
            try:
                first_file = uploaded_files[0]
                first_file.seek(0)
                ds = pydicom.dcmread(first_file, stop_before_pixels=True)
                st.session_state['patient_info'] = {
                    "name": str(ds.PatientName),
                    "mrn": str(ds.PatientID)
                }
                first_file.seek(0)
            except Exception as e:
                st.warning(f"Could not read patient information from DICOM files: {e}")
                st.session_state['patient_info'] = {"name": "N/A", "mrn": "N/A"}
        # --- End of new code ---

        with st.expander("Optional Inputs", expanded=True):
            st.markdown("<h3 style='color: #fc8781;'>Previous Brachytherapy Treatments Delivered</h3>", unsafe_allow_html=True)
            previous_brachy_data_file = st.file_uploader("Upload previous brachytherapy data (optional)", type=["html", "json"])
            if previous_brachy_data_file is not None and previous_brachy_data_file.name.endswith('.json'):
                try:
                    # Make sure to be able to read the file multiple times
                    previous_brachy_data_file.seek(0)
                    json_content = json.loads(previous_brachy_data_file.read().decode("utf-8"))
                    json_patient_name = json_content.get("patient_name", "N/A")
                    json_patient_mrn = json_content.get("patient_mrn", "N/A")

                    current_patient_name = st.session_state.get('patient_info', {}).get('name', 'N/A')
                    current_patient_mrn = st.session_state.get('patient_info', {}).get('mrn', 'N/A')

                    if json_patient_name != current_patient_name or json_patient_mrn != current_patient_mrn:
                        st.warning(f"Patient mismatch! Current patient: {current_patient_name} ({current_patient_mrn}). JSON patient: {json_patient_name} ({json_patient_mrn}).")
                    
                    if "ebrt_summary" in json_content:
                        st.session_state.ebrt_total_dose = json_content["ebrt_summary"].get("total_dose", 0.0)
                        st.session_state.ebrt_num_fractions = json_content["ebrt_summary"].get("number_of_fractions", 25)
                        st.session_state.ebrt_fraction_dose = json_content["ebrt_summary"].get("dose_per_fraction", 0.0)

                    from src.main import get_structure_mapping
                    structure_names = list(st.session_state.structure_mapping.keys())
                    json_structure_names = list(json_content.get("dvh_results", {}).keys())
                    proposed_mapping = get_structure_mapping(structure_names, json_structure_names)

                    with st.expander("Confirm Structure Mapping"):
                        if 'confirmed_structure_mapping' not in st.session_state:
                            st.session_state.confirmed_structure_mapping = {}

                        for current_struct, json_struct in proposed_mapping.items():
                            mapping = st.selectbox(
                                f"Map '{current_struct}' to:",
                                options=json_structure_names,
                                index=json_structure_names.index(json_struct),
                                key=f"confirm_map_{current_struct}"
                            )
                            st.session_state.confirmed_structure_mapping[current_struct] = mapping

                    previous_brachy_data_file.seek(0)
                except Exception as e:
                    st.error(f"Error reading patient info from JSON file: {e}")

            # Initialize session state for EBRT if it doesn't exist
            if 'ebrt_total_dose' not in st.session_state:
                st.session_state.ebrt_total_dose = 0.0
            if 'ebrt_fraction_dose' not in st.session_state:
                st.session_state.ebrt_fraction_dose = 0.0
            if 'ebrt_num_fractions' not in st.session_state:
                st.session_state.ebrt_num_fractions = 25

            st.markdown("<h3 style='color: #fc8781;'>EBRT Dose (Gy)</h3>", unsafe_allow_html=True)

            # Callback functions to update EBRT values
            def update_total_dose():
                st.session_state.ebrt_total_dose = st.session_state.ebrt_fraction_dose * st.session_state.ebrt_num_fractions

            def update_fraction_dose():
                if st.session_state.ebrt_num_fractions > 0:
                    st.session_state.ebrt_fraction_dose = st.session_state.ebrt_total_dose / st.session_state.ebrt_num_fractions
                else:
                    st.session_state.ebrt_fraction_dose = 0

            def update_num_fractions():
                if st.session_state.ebrt_fraction_dose > 0:
                    st.session_state.ebrt_num_fractions = round(st.session_state.ebrt_total_dose / st.session_state.ebrt_fraction_dose)
                else:
                    st.session_state.ebrt_num_fractions = 0

            # Create columns for EBRT inputs
            col1, col2, col3 = st.columns(3)

            with col1:
                st.number_input("Total Dose (Gy)", 
                                key='ebrt_total_dose', 
                                on_change=update_fraction_dose)
            with col2:
                st.number_input("Number of Fractions", 
                                min_value=0, 
                                step=1, 
                                key='ebrt_num_fractions', 
                                on_change=update_total_dose)
            with col3:
                st.number_input("Dose per Fraction (Gy)", 
                                key='ebrt_fraction_dose', 
                                on_change=update_total_dose)

            # --- CORRECTED LOGIC TO FIND DEFAULT FRACTIONS ---
            default_num_fractions = 1
            for uploaded_file in uploaded_files:
                try:
                    # Use seek(0) to ensure we read from the beginning
                    uploaded_file.seek(0)
                    ds = pydicom.dcmread(uploaded_file, stop_before_pixels=True)

                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                        if hasattr(ds, 'FractionGroupSequence') and ds.FractionGroupSequence:
                            default_num_fractions = ds.FractionGroupSequence[0].NumberOfFractionsPlanned
                        break # Found the plan, no need to check other files
                except Exception:
                    # This file is not a readable DICOM or not the one we're looking for, continue
                    continue
                finally:
                    # IMPORTANT: Reset the file pointer so it can be read again later
                    uploaded_file.seek(0)
            # --- END CORRECTED LOGIC ---

            st.markdown("<h3 style='color: #fc8781;'>Number of Fractions to be Delivered</h3>", unsafe_allow_html=True)
            num_fractions_delivered = st.number_input(
                " ", # Empty label as we are using markdown for the label
                value=default_num_fractions,
                min_value=1,
                step=1,
                key="num_fractions_delivered_input"
            )

            st.subheader("Dwell Time Decay Sheet")
            st.markdown("""
            **Instructions for generating the Mosaiq schedule report:**

            In Mosaiq, open the patient's chart and go to 'Schedule' > 'All'. Right-click and select 'Reports' > 'Patient Appointment Calendar'. 
            Select all departments, the current patient, and adjust the date range. For the report format, select 'Display Appointments in LIST format'. 
            Save the report as an .xlsx file.
            """)
            mosaiq_schedule_file = st.file_uploader("Upload Mosaiq schedule report (.xlsx)", type=["xlsx"])

        st.sidebar.subheader("EBRT Summary")
        st.sidebar.write(f"Total Dose: {st.session_state.ebrt_total_dose:.2f} Gy")
        st.sidebar.write(f"Fractions: {st.session_state.ebrt_num_fractions}")
        st.sidebar.write(f"Dose per Fraction: {st.session_state.ebrt_fraction_dose:.2f} Gy")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a unique key for the temporary directory based on uploaded file names
            # This helps ensure that when files change, we re-process them.
            uploaded_file_key = "_".join(sorted([f.name for f in uploaded_files]))
            if st.session_state.get("last_uploaded_files") != uploaded_file_key:
                st.session_state.last_uploaded_files = uploaded_file_key
                if "manual_mapping" in st.session_state:
                    del st.session_state.manual_mapping # Clear mapping on new file upload

            rtdose_dir = os.path.join(tmpdir, "RTDOSE")
            rtstruct_dir = os.path.join(tmpdir, "RTst")
            rtplan_dir = os.path.join(tmpdir, "RTPLAN")

            os.makedirs(rtdose_dir)
            os.makedirs(rtstruct_dir)
            os.makedirs(rtplan_dir)

            rtstruct_file_path = None
            for uploaded_file in uploaded_files:
                file_path = os.path.join(tmpdir, uploaded_file.name)
                uploaded_file.seek(0)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                try:
                    ds = pydicom.dcmread(file_path)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': # RT Dose Storage
                        os.rename(file_path, os.path.join(rtdose_dir, uploaded_file.name))
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure Set Storage
                        os.rename(file_path, os.path.join(rtstruct_dir, uploaded_file.name))
                        rtstruct_file_path = os.path.join(rtstruct_dir, uploaded_file.name)
                    elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                        os.rename(file_path, os.path.join(rtplan_dir, uploaded_file.name))
                        rtplan_file_path = os.path.join(rtplan_dir, uploaded_file.name) # Store RTPLAN path
                except Exception as e:
                    st.warning(f"Could not read DICOM file {uploaded_file.name}: {e}")

            # Extract dose references if RTPLAN is available
            if rtplan_file_path:
                plan_data = get_plan_data(rtplan_file_path)
                dose_references = [dr['name'] for dr in plan_data.get('dose_references', [])]
                
                st.session_state.available_point_names = dose_references

                point_dose_constraints = templates[st.session_state.current_template_name].get("point_dose_constraints", {})
                
                dose_point_mapping = get_dose_point_mapping(rtplan_file_path, point_dose_constraints)
                
                with st.expander("Dose Point to Constraint Mapping"):
                    # --- START: New Manual Mapping Section ---
                    clinical_point_names = ["N/A"] + list(point_dose_constraints.keys())

                    if 'manual_mapping' not in st.session_state:
                        st.session_state.manual_mapping = {}

                    # Initialize manual_mapping with automatic mappings, but prioritize existing session state
                    # This ensures user overrides are kept during a re-run, but auto-mapping is applied once.
                    auto_mapping_dict = dose_point_mapping.copy()
                    # Merge dictionaries: manual_mapping (user choices) overwrites auto_mapping
                    merged_mapping = {**auto_mapping_dict, **st.session_state.manual_mapping}
                    st.session_state.manual_mapping = merged_mapping
                    
                    for dicom_point in st.session_state.available_point_names:
                        # Ensure the point name is valid before creating a widget
                        if dicom_point and dicom_point.strip():
                            col1, col2 = st.columns([1, 2])
                            
                            with col1:
                                st.write(f"**{dicom_point}**")
                                
                            with col2:
                                current_mapping = st.session_state.manual_mapping.get(dicom_point, "N/A")
                                
                                try:
                                    current_index = clinical_point_names.index(current_mapping)
                                except ValueError:
                                    current_index = 0

                                # The selectbox's value is automatically managed by Streamlit via its key
                                st.selectbox(
                                    f"Map '{dicom_point}' to:",
                                    options=clinical_point_names,
                                    index=current_index,
                                    key=f"map_{dicom_point}", # The key links this widget to session state
                                    label_visibility="collapsed"
                                )
                                
                                # Update our manual_mapping dict from the widget's state
                                st.session_state.manual_mapping[dicom_point] = st.session_state[f"map_{dicom_point}"]

            if rtstruct_file_path:
                from src.dicom_parser import get_structure_data, load_dicom_file
                rtstruct_dataset = load_dicom_file(rtstruct_file_path)
                structure_data = get_structure_data(rtstruct_dataset)
                structure_names = list(structure_data.keys())

                with st.expander("Structure Mapping"):
                    if 'structure_mapping' not in st.session_state:
                        st.session_state.structure_mapping = {}

                    for structure_name in structure_names:
                        # Auto-map based on name
                        if structure_name.lower() in ['gtv', 'ctv', 'hr-ctv']:
                            default_mapping = "TARGET"
                        else:
                            default_mapping = "OAR"

                        mapping = st.selectbox(
                            f"Map '{structure_name}' to:",
                            options=["TARGET", "OAR", "IGNORE"],
                            index=["TARGET", "OAR", "IGNORE"].index(st.session_state.structure_mapping.get(structure_name, default_mapping)),
                            key=f"map_{structure_name}"
                        )
                        st.session_state.structure_mapping[structure_name] = mapping
            else:
                st.session_state.available_point_names = []

    # Point selection UI
    if st.session_state.available_point_names:
        st.session_state.selected_point_names = st.multiselect(
            "Select Points to Display in Report",
            options=st.session_state.available_point_names,
            default=st.session_state.available_point_names
        )
    else:
        st.session_state.selected_point_names = []

    if st.button("Generate Dwell Time Sheet"):
        if 'mosaiq_schedule_file' in locals() and mosaiq_schedule_file and uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_excel_file:
                tmp_excel_file.write(mosaiq_schedule_file.getbuffer())
                mosaiq_schedule_path = tmp_excel_file.name

            with tempfile.TemporaryDirectory() as tmpdir:
                rtplan_file_path = None
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(tmpdir, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    ds = pydicom.dcmread(file_path)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan Storage
                        rtplan_file_path = file_path


                output_excel_path = os.path.join(tmpdir, "populated_dwell_time_sheet.xlsx")

                # This function will be created in main.py
                from src.main import generate_dwell_time_sheet
                generate_dwell_time_sheet(
                    mosaiq_schedule_path=mosaiq_schedule_path,
                    rtplan_file=rtplan_file_path,
                    output_excel_path=output_excel_path,
                )

                with open(output_excel_path, "rb") as f:
                    st.download_button(
                        label="Download Dwell Time Sheet",
                        data=f,
                        file_name="dwell_time_sheet.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
        else:
            st.warning("Please upload both the Mosaiq schedule and the DICOM files.")


    ab_ratios = st.session_state.get("ab_ratios", templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"].copy())


    if st.button("Run Analysis"):
        if uploaded_files:

            if uploaded_files:
                # Create the final mapping list from session state RIGHT BEFORE analysis
                manual_dose_point_mapping = [(k, v) for k, v in st.session_state.get('manual_mapping', {}).items() if v != "N/A"]

                # st.write([file.name for file in uploaded_files])
            
            with tempfile.TemporaryDirectory() as tmpdir_analysis:
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(tmpdir_analysis, uploaded_file.name)
                    uploaded_file.seek(0)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                rtdose_dir_analysis = os.path.join(tmpdir_analysis, "RTDOSE")
                rtstruct_dir_analysis = os.path.join(tmpdir_analysis, "RTst")
                rtplan_dir_analysis = os.path.join(tmpdir_analysis, "RTPLAN")

                os.makedirs(rtdose_dir_analysis, exist_ok=True)
                os.makedirs(rtstruct_dir_analysis, exist_ok=True)
                os.makedirs(rtplan_dir_analysis, exist_ok=True)

                rtdose_path = None
                rtstruct_path = None
                rtplan_path = None

                for uploaded_file in uploaded_files:
                    file_path = os.path.join(tmpdir_analysis, uploaded_file.name)
                    uploaded_file.seek(0)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    try:
                        ds = pydicom.dcmread(file_path)
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2':
                            rtdose_path = os.path.join(rtdose_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtdose_path)
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3':
                            rtstruct_path = os.path.join(rtstruct_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtstruct_path)
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5':
                            rtplan_path = os.path.join(rtplan_dir_analysis, uploaded_file.name)
                            os.rename(file_path, rtplan_path)
                    except Exception as e:
                        st.warning(f"Could not read DICOM file {uploaded_file.name}: {e}")

                if rtdose_path and rtstruct_path and rtplan_path:
                    previous_brachy_data = {}
                    if previous_brachy_data_file:
                        file_extension = os.path.splitext(previous_brachy_data_file.name)[1].lower()
                        if file_extension == ".html":
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_html_file:
                                tmp_html_file.write(previous_brachy_data_file.getbuffer())
                                previous_brachy_html_path = tmp_html_file.name
                            previous_brachy_data = previous_brachy_html_path
                        elif file_extension == ".json":
                            previous_brachy_data_file.seek(0)
                            json_content = json.loads(previous_brachy_data_file.read().decode("utf-8"))
                            previous_brachy_bed_data = {}
                            for organ, data in json_content.get("dvh_results", {}).items():
                                previous_brachy_bed_data[organ] = {
                                    "d2cc": data.get("bed_brachy_d2cc", 0.0),
                                    "d1cc": data.get("bed_brachy_d1cc", 0.0),
                                    "d0_1cc": data.get("bed_brachy_d0_1cc", 0.0)
                                }
                            for point_data in json_content.get("point_dose_results", {}):
                                previous_brachy_bed_data[point_data["name"]] = point_data.get("BED_this_plan", 0.0)
                            previous_brachy_data = previous_brachy_bed_data
                            previous_brachy_data_file.seek(0)

                    args = argparse.Namespace(
                        data_dir=tmpdir_analysis,
                        ebrt_dose=st.session_state.ebrt_total_dose,
                        ebrt_fractions=st.session_state.ebrt_num_fractions,
                        previous_brachy_data=previous_brachy_data,
                        output_html=os.path.join(tmpdir_analysis, "report.html"),
                        alpha_beta_ratios=ab_ratios,
                        selected_point_names=st.session_state.selected_point_names,
                        custom_constraints=templates[st.session_state.current_template_name],
                    )

                    results = run_analysis(args, structure_data, plan_data, selected_point_names=st.session_state.selected_point_names, dose_point_mapping=manual_dose_point_mapping, custom_constraints=args.custom_constraints, num_fractions_delivered=num_fractions_delivered, ebrt_fractions=args.ebrt_fractions, structure_mapping=st.session_state.structure_mapping, confirmed_structure_mapping=st.session_state.confirmed_structure_mapping)

                    # *** FIX STARTS HERE: Add error handling for the GUI ***
                    if results and 'error' in results:
                        st.error(results['error'])
                    else:
                        print(f"Selected template: {selected_template_name}")
                        # --- Start Channel Mapping Validation ---
                        if selected_template_name in ["Cervix HDR - EMBRACE II", "Cervix HDR - ABS/GEC-Estro"]:
                            channel_mapping_data = results.get('channel_mapping', [])
                            num_channels = len(channel_mapping_data)

                            if num_channels == 3: # Tandem and Ovoid
                                expected_mapping = { '1': '1', '2': '3', '3': '5' }
                                all_mappings_correct = True
                                for ch_num, tt_num in expected_mapping.items():
                                    if not any(channel.get('channel_number') == ch_num and channel.get('transfer_tube_number') == tt_num for channel in channel_mapping_data):
                                        all_mappings_correct = False
                                        break
                                if not all_mappings_correct:
                                    st.warning("Warning: Incorrect channel mapping for Tandem and Ovoid plan. Expected: Channel 1 to Transfer Tube 1, Channel 2 to Transfer Tube 3, Channel 3 to Transfer Tube 5.")

                            elif num_channels == 2: # Tandem and Ring
                                expected_mapping = { '1': '1', '2': '5' }
                                all_mappings_correct = True
                                for ch_num, tt_num in expected_mapping.items():
                                    if not any(channel.get('channel_number') == ch_num and channel.get('transfer_tube_number') == tt_num for channel in channel_mapping_data):
                                        all_mappings_correct = False
                                        break
                                if not all_mappings_correct:
                                    st.warning("Warning: Incorrect channel mapping for Tandem and Ring plan. Expected: Channel 1 to Transfer Tube 1, Channel 2 to Transfer Tube 5.")

                        elif selected_template_name == "Cylinder HDR":
                            channel_mapping_data = results.get('channel_mapping', [])
                            is_catheter_1_mapped_to_channel_5 = False
                            for channel in channel_mapping_data:
                                if channel.get('channel_number') == '1' and channel.get('transfer_tube_number') == '5':
                                    is_catheter_1_mapped_to_channel_5 = True
                                    break
                            
                            if not is_catheter_1_mapped_to_channel_5:
                                st.warning("Warning: For 'Cylinder HDR' template, expected channel mapping is Catheter 1 to Channel 5. Please verify your channel mapping.")
                        # --- End Channel Mapping Validation ---

                        with st.container():
                            st.header("Results")

                            col_summary_left, col_summary_right = st.columns([0.7, 0.3])

                            with col_summary_left:
                                st.write(f"**Patient Name:** {results['patient_name']}")
                                st.write(f"**Patient MRN:** {results['patient_mrn']}")
                                st.write(f"**Plan Name:** {results['plan_name']}")
                                st.write(f"**Plan Date:** {results['plan_date']}")
                                st.write(f"**Plan Time:** {results['plan_time']}")
                                if results.get("plan_time_warning"):
                                    st.warning(results["plan_time_warning"])
                                st.write(f"**Brachytherapy Dose per Fraction:** {results['brachy_dose_per_fraction']:.2f} Gy")
                                st.write(f"**Number of Fractions Used for Calculations:** {results['calculation_number_of_fractions']}")
                                st.write(f"**Number of Planned Fractions:** {results['planned_number_of_fractions']}")
                                
                                # --- ADDED WARNING ---
                                if results['calculation_number_of_fractions'] != results['planned_number_of_fractions']:
                                    st.warning("Warning: The planned number of fractions and the number of fractions used for EQD2 calculations differ.")
                                # --- END WARNING ---

                            with col_summary_right:
                                st.subheader("Channel Mapping")
                                if results.get('channel_mapping'):
                                    # Group channels by ChannelNumber (for Cath) and TransferTubeNumber (for Chan)
                                    channel_info_display = {}
                                    for channel in results['channel_mapping']:
                                        cath_num = channel.get('channel_number', 'N/A')
                                        chan_num = channel.get('transfer_tube_number', 'N/A')
                                        
                                        if cath_num not in channel_info_display:
                                            channel_info_display[cath_num] = []
                                        channel_info_display[cath_num].append(chan_num)
                                    
                                    for cath_num, chan_nums in channel_info_display.items():
                                        st.write(f"**Cath {cath_num}** - Chan {', '.join(map(str, sorted(chan_nums)))}")
                                else:
                                    st.info("No channel mapping data available.")

                            tab1, tab2, tab3 = st.tabs(["DVH Results", "Point Dose Results", "Report"])

                            with tab1:
                                st.subheader("Target Volume DVH Results")
                                target_dvh_data = []
                                oar_dvh_data = []

                                # Create a case-insensitive version of the alpha/beta ratios dictionary
                                ab_ratios_lower = {k.lower(): v for k, v in ab_ratios.items()}

                                for organ, data in results["dvh_results"].items():
                                    # Use the lowercase version for lookup
                                    alpha_beta = ab_ratios_lower.get(organ.lower(), ab_ratios.get("Default"))
                                    
                                    # Use structure_mapping if available, otherwise fall back to old logic
                                    if 'structure_mapping' in st.session_state and organ in st.session_state.structure_mapping:
                                        is_target = st.session_state.structure_mapping[organ] == "TARGET"
                                    else:
                                        is_target = "ctv" in organ.lower() or "gtv" in organ.lower() or alpha_beta == 10

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
                                            "Dose to Meet Constraint (Gy)": "",
                                            "Constraint Status": constraint_status
                                        })
                                        # D1cc row
                                        oar_dvh_data.append({
                                            "Organ": organ,
                                            "Volume (cc)": None,
                                            "Dose Metric": "D1cc",
                                            "Dose (Gy)": data["d1cc_gy_per_fraction"],
                                            "BED (Gy)": data["bed_d1cc"],
                                            "EQD2 (Gy)": data["eqd2_d1cc"],
                                            "Dose to Meet Constraint (Gy)": "",
                                            "Constraint Status": constraint_status
                                        })
                                        # D2cc row
                                        oar_dvh_data.append({
                                            "Organ": organ,
                                            "Volume (cc)": None,
                                            "Dose Metric": "D2cc",
                                            "Dose (Gy)": data["d2cc_gy_per_fraction"],
                                            "BED (Gy)": data["bed_d2cc"],
                                            "EQD2 (Gy)": data["eqd2_d2cc"],
                                            "Dose to Meet Constraint (Gy)": dose_to_meet,
                                            "Constraint Status": constraint_status
                                        })
                                
                                if target_dvh_data:
                                    st.dataframe(pd.DataFrame(target_dvh_data), column_config={
                                        "Volume (cc)": st.column_config.NumberColumn(format="%.2f"),
                                        "D98 (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                        "D90 (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                        "Max Dose (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                        "Mean Dose (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                        "Min Dose (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                    })
                                else:
                                    st.info("No target volume DVH data available.")

                                st.subheader("OAR DVH Results")
                                if oar_dvh_data:
                                    temp_oar_df = pd.DataFrame(oar_dvh_data)
                                    
                                    previous_brachy_data = {}
                                    if previous_brachy_data_file and previous_brachy_data_file.name.endswith('.json'):
                                        previous_brachy_data_file.seek(0)
                                        previous_brachy_data = json.loads(previous_brachy_data_file.read().decode("utf-8"))

                                    # Get the number of fractions from the JSON file
                                    num_json_fractions = 0
                                    if previous_brachy_data:
                                        first_organ_dvh = next(iter(previous_brachy_data.get("dvh_results", {}).values()), {})
                                        d2cc_doses = first_organ_dvh.get("dose_fx", {}).get("d2cc_gy_per_fraction", [])
                                        if isinstance(d2cc_doses, list):
                                            num_json_fractions = len(d2cc_doses)
                                        else:
                                            num_json_fractions = 1

                                    # Get the number of fractions for the current analysis
                                    num_current_fractions = results.get('calculation_number_of_fractions', 1)
                                    
                                    # Create all fraction columns that will be needed
                                    all_columns = ["Organ", "Volume (cc)", "Dose Metric"]
                                    for i in range(num_json_fractions + num_current_fractions):
                                        all_columns.append(f"Fx {i+1} Dose (Gy)")
                                    all_columns.extend(["BED (Gy)", "EQD2 (Gy)", "Dose to Meet Constraint (Gy)", "Constraint Status"])

                                    restructured_data = []
                                    for organ_name in temp_oar_df['Organ'].unique():
                                        organ_group = temp_oar_df[temp_oar_df['Organ'] == organ_name]
                                        
                                        for dose_metric in ['D0.1cc', 'D1cc', 'D2cc']:
                                            metric_row_df = organ_group[organ_group['Dose Metric'] == dose_metric]
                                            if not metric_row_df.empty:
                                                row_data = metric_row_df.iloc[0].to_dict()
                                                
                                                new_row = {
                                                    "Organ": organ_name,
                                                    "Volume (cc)": row_data["Volume (cc)"] if dose_metric == 'D0.1cc' else None,
                                                    "Dose Metric": dose_metric,
                                                    "BED (Gy)": row_data["BED (Gy)"],
                                                    "EQD2 (Gy)": row_data["EQD2 (Gy)"],
                                                    "Dose to Meet Constraint (Gy)": row_data["Dose to Meet Constraint (Gy)"] if dose_metric == 'D2cc' else "",
                                                    "Constraint Status": row_data["Constraint Status"]
                                                }

                                                # Get doses from JSON
                                                json_doses = []
                                                if previous_brachy_data:
                                                    # Find the correct organ name in JSON data using confirmed mapping
                                                    mapped_organ_name = organ_name
                                                    if 'confirmed_structure_mapping' in st.session_state:
                                                        for key, value in st.session_state.confirmed_structure_mapping.items():
                                                            if key == organ_name:
                                                                mapped_organ_name = value
                                                                break
                                                    
                                                    json_doses_raw = previous_brachy_data.get("dvh_results", {}).get(mapped_organ_name, {}).get("dose_fx", {}).get(f"{dose_metric.lower()}_gy_per_fraction", [])
                                                    if isinstance(json_doses_raw, list):
                                                        json_doses = json_doses_raw
                                                    else:
                                                        json_doses = [json_doses_raw]

                                                for i, dose in enumerate(json_doses):
                                                    new_row[f"Fx {i+1} Dose (Gy)"] = dose
                                                
                                                # Get doses from current analysis
                                                current_dose = row_data["Dose (Gy)"]
                                                for i in range(num_current_fractions):
                                                    new_row[f"Fx {num_json_fractions + i + 1} Dose (Gy)"] = current_dose

                                                restructured_data.append(new_row)

                                    if restructured_data:
                                        final_oar_df = pd.DataFrame(restructured_data, columns=all_columns)

                                        def style_oar_rows(df):
                                            styles = pd.DataFrame('', index=df.index, columns=df.columns)
                                            organ_groups = df['Organ'].ffill()
                                            current_constraints = st.session_state.custom_constraints

                                            for organ_name in organ_groups.unique():
                                                group_indices = df[organ_groups == organ_name].index
                                                d2cc_row_df = df.loc[group_indices]
                                                d2cc_row_df = d2cc_row_df[d2cc_row_df['Dose Metric'] == 'D2cc']
                                                
                                                if not d2cc_row_df.empty:
                                                    d2cc_index = d2cc_row_df.index[0]
                                                    eqd2_value = d2cc_row_df['EQD2 (Gy)'].iloc[0]

                                                    oar_constraints = current_constraints.get('oar_constraints', {})
                                                    if pd.notna(eqd2_value) and organ_name in oar_constraints and "D2cc" in oar_constraints[organ_name]:
                                                        constraint_data = oar_constraints[organ_name]['D2cc']
                                                        max_val = constraint_data['max']
                                                        warn_val = constraint_data.get('warning')
                                                        
                                                        style_str = ''
                                                        if eqd2_value > max_val:
                                                            style_str = 'background-color: #dc3545; color: white'
                                                        elif warn_val is not None and eqd2_value >= warn_val:
                                                            style_str = 'background-color: #ffc107; color: black'
                                                        else:
                                                            style_str = 'background-color: #28a745; color: white'
                                                        
                                                        styles.loc[d2cc_index] = style_str
                                            return styles

                                        # *** FIX STARTS HERE: Dynamically configure column formatting for OAR DVH table ***
                                        oar_column_config = {
                                            "Volume (cc)": st.column_config.NumberColumn(format="%.2f"),
                                            "BED (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                            "EQD2 (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                            "Dose to Meet Constraint (Gy)": st.column_config.NumberColumn(format="%.2f"),
                                        }
                                        # Add formatting for all dynamically created fraction columns
                                        for col in final_oar_df.columns:
                                            if col.startswith("Fx ") and col.endswith(" Dose (Gy)"):
                                                oar_column_config[col] = st.column_config.NumberColumn(format="%.2f")
                                        
                                        st.dataframe(final_oar_df.style.apply(style_oar_rows, axis=None), column_config=oar_column_config)
                                        # *** FIX ENDS HERE ***

                                else:
                                    st.info("No OAR DVH data available.")

                            with tab2:
                                st.subheader("Point Dose Results")
                                
                                # Get the number of fractions from the JSON file
                                num_json_fractions = 0
                                if previous_brachy_data:
                                    first_point = next(iter(previous_brachy_data.get("point_dose_results", [])), {})
                                    dose_fx = first_point.get("dose_fx", [])
                                    if isinstance(dose_fx, list):
                                        num_json_fractions = len(dose_fx)
                                    else:
                                        num_json_fractions = 1
                                # Get the number of fractions for the current analysis
                                num_current_fractions = results.get('calculation_number_of_fractions', 1)
                                
                                # Create all fraction columns that will be needed
                                all_columns = ["name"]
                                for i in range(num_json_fractions + num_current_fractions):
                                    all_columns.append(f"Fx {i+1} Dose (Gy)")
                                all_columns.extend(["total_dose", "BED_this_plan", "BED_previous_brachy", "BED_EBRT", "EQD2", "Constraint Status"])

                                point_dose_data = []
                                for point_result in results["point_dose_results"]:
                                    new_row = {
                                        "name": point_result["name"],
                                        "total_dose": point_result["total_dose"],
                                        "BED_this_plan": point_result["BED_this_plan"],
                                        "BED_previous_brachy": point_result["BED_previous_brachy"],
                                        "BED_EBRT": point_result["BED_EBRT"],
                                        "EQD2": point_result["EQD2"],
                                        "Constraint Status": point_result["Constraint Status"]
                                    }

                                    # Get doses from JSON
                                    json_doses = []
                                    if previous_brachy_data:
                                        for prev_point in previous_brachy_data.get("point_dose_results", []):
                                            if prev_point["name"] == point_result["name"]:
                                                json_doses_raw = prev_point.get("dose_fx", [])
                                                if isinstance(json_doses_raw, list):
                                                    json_doses = json_doses_raw
                                                else:
                                                    json_doses = [json_doses_raw]
                                                break
                                    
                                    for i, dose in enumerate(json_doses):
                                        new_row[f"Fx {i+1} Dose (Gy)"] = dose

                                    # Get dose from current analysis
                                    current_dose = point_result["dose"]
                                    for i in range(num_current_fractions):
                                        new_row[f"Fx {num_json_fractions + i + 1} Dose (Gy)"] = current_dose

                                    point_dose_data.append(new_row)

                                if point_dose_data:
                                    point_dose_df = pd.DataFrame(point_dose_data, columns=all_columns)

                                    def style_point_dose_rows(row):
                                        style = [''] * len(row)
                                        if 'Constraint Status' in row and row['Constraint Status'] == 'Pass':
                                            style = ['background-color: #28a745; color: white'] * len(row)
                                        elif 'Constraint Status' in row and row['Constraint Status'] == 'Fail':
                                            style = ['background-color: #dc3545; color: white'] * len(row)
                                        return style

                                    # *** FIX STARTS HERE: Dynamically configure column formatting for Point Dose table ***
                                    point_dose_column_config = {
                                        "total_dose": st.column_config.NumberColumn(format="%.2f"),
                                        "BED_this_plan": st.column_config.NumberColumn(format="%.2f"),
                                        "BED_previous_brachy": st.column_config.NumberColumn(format="%.2f"),
                                        "BED_EBRT": st.column_config.NumberColumn(format="%.2f"),
                                        "EQD2": st.column_config.NumberColumn(format="%.2f"),
                                    }
                                    # Add formatting for all dynamically created fraction columns
                                    for col in point_dose_df.columns:
                                        if col.startswith("Fx ") and col.endswith(" Dose (Gy)"):
                                            point_dose_column_config[col] = st.column_config.NumberColumn(format="%.2f")

                                    st.dataframe(point_dose_df.style.apply(style_point_dose_rows, axis=1), column_config=point_dose_column_config)
                                    # *** FIX ENDS HERE ***

                                else:
                                    st.info("No point dose data available.")
                            
                            with tab3:
                                st.subheader("Report")
                                html_report = results.get('html_report', '')
                                if html_report:
                                    st.components.v1.html(html_report, height=600, scrolling=True)
                                    
                                    dvh_export_data = {}
                                    for k, v in results["dvh_results"].items():
                                        dvh_export_data[k] = {
                                            'bed_brachy_d2cc': v.get('bed_brachy_d2cc', 0),
                                            'bed_brachy_d1cc': v.get('bed_brachy_d1cc', 0),
                                            'bed_brachy_d0_1cc': v.get('bed_brachy_d0_1cc', 0),
                                            'dose_fx': {
                                                'd2cc_gy_per_fraction': [v.get('d2cc_gy_per_fraction', 0)] * results.get('calculation_number_of_fractions', 1),
                                                'd1cc_gy_per_fraction': [v.get('d1cc_gy_per_fraction', 0)] * results.get('calculation_number_of_fractions', 1),
                                                'd0_1cc_gy_per_fraction': [v.get('d0_1cc_gy_per_fraction', 0)] * results.get('calculation_number_of_fractions', 1),
                                            }
                                        }

                                    point_dose_export_data = []
                                    for point in results["point_dose_results"]:
                                        point_dose_export_data.append({
                                            "name": point["name"],
                                            "dose_fx": [point["dose"]] * results.get('calculation_number_of_fractions', 1),
                                            "BED_this_plan": point["BED_this_plan"]
                                        })

                                    export_data = {
                                        "patient_name": results["patient_name"],
                                        "patient_mrn": results["patient_mrn"],
                                        "plan_date": results["plan_date"],
                                        "plan_time": results["plan_time"],
                                        "source_info": results["source_info"],
                                        "ebrt_summary": {
                                            "total_dose": st.session_state.ebrt_total_dose,
                                            "number_of_fractions": st.session_state.ebrt_num_fractions,
                                            "dose_per_fraction": st.session_state.ebrt_fraction_dose
                                        },
                                        "dvh_results": dvh_export_data,
                                        "point_dose_results": point_dose_export_data
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
                                        convert_html_to_pdf(html_report, pdf_path)

                                        with open(pdf_path, "rb") as f:
                                            pdf_bytes = f.read()
                                        
                                        st.download_button(
                                            label="Download PDF",
                                            data=pdf_bytes,
                                            file_name="report.pdf",
                                            mime="application/pdf"
                                        )
                                    except IOError as e:
                                        st.error(f"Could not generate PDF. {e}")
                                else:
                                    st.warning("Could not generate HTML report.")

                else:
                    st.error("Please upload all required DICOM files (RTDOSE, RTSTRUCT, RTPLAN).")
        else:
            st.error("Please upload DICOM files.")

if __name__ == "__main__":
    main()