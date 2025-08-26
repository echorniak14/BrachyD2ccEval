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
    wkhtmltopdf_path = ""
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
            target_constraints = {organ: const for organ, const in st.session_state.custom_constraints.items() if "D2cc" not in const}
            oar_constraints = {organ: const for organ, const in st.session_state.custom_constraints.items() if "D2cc" in const}

            # Display and update constraints for Custom template
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Target Volumes")
                for organ, organ_constraints in target_constraints.items():
                    st.write(f"**{organ}**")
                    if "D90" in organ_constraints:
                        st.session_state.custom_constraints[organ]["D90"] = st.number_input(
                            f"D90 (Gy)",
                            value=float(organ_constraints["D90"]),
                            key=f"constraint_{organ}_D90_{st.session_state.widget_key_suffix}"
                        )
                    if "D98" in organ_constraints:
                        st.session_state.custom_constraints[organ]["D98"] = st.number_input(
                            f"D98 (Gy)",
                            value=float(organ_constraints["D98"]),
                            key=f"constraint_{organ}_D98_{st.session_state.widget_key_suffix}"
                        )

            with col2:
                st.subheader("Organs at Risk")
                for organ, organ_constraints in oar_constraints.items():
                    st.write(f"**{organ}**")
                    if "warning" in organ_constraints["D2cc"]:
                        st.session_state.custom_constraints[organ]["D2cc"]["warning"] = st.number_input(
                            f"D2cc Warning (Gy)",
                            value=float(organ_constraints["D2cc"]["warning"]),
                            key=f"constraint_{organ}_D2cc_warning_{st.session_state.widget_key_suffix}"
                        )
                    st.session_state.custom_constraints[organ]["D2cc"]["max"] = st.number_input(
                        f"D2cc Max (Gy)",
                        value=float(organ_constraints["D2cc"]["max"]),
                        key=f"constraint_{organ}_D2cc_max_{st.session_state.widget_key_suffix}"
                    )
    
    st.sidebar.header("Loaded EQD2 Constraints")
    target_constraints = {organ: const for organ, const in st.session_state.custom_constraints.items() if "D2cc" not in const}
    oar_constraints = {organ: const for organ, const in st.session_state.custom_constraints.items() if "D2cc" in const}
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

    # Logic to handle uploaded files and extract dose references
    rtplan_file_path = None
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

            num_fractions_delivered = st.number_input(
                "Number of Fractions to be Delivered",
                value=default_num_fractions,
                min_value=1,
                step=1,
                key="num_fractions_delivered_input"
            )

            ebrt_dose = st.number_input("EBRT Dose (Gy)", value=0.0)

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
                    previous_brachy_data_file.seek(0)
                except Exception as e:
                    st.error(f"Error reading patient info from JSON file: {e}")
            wkhtmltopdf_path = st.text_input("Path to wkhtmltopdf.exe (optional)")

        st.sidebar.subheader("EBRT Dose")
        st.sidebar.write(f"{ebrt_dose} Gy")

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
            else:
                st.session_state.available_point_names = []
    else:
        st.session_state.available_point_names = []
        st.session_state.selected_point_names = []

    # Point selection UI
    if st.session_state.available_point_names:
        st.session_state.selected_point_names = st.multiselect(
            "Select Points to Display in Report",
            options=st.session_state.available_point_names,
            default=st.session_state.available_point_names
        )
    else:
        st.session_state.selected_point_names = []

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
                                    "d2cc": data.get("bed_d2cc", 0.0),
                                    "d1cc": data.get("bed_d1cc", 0.0),
                                    "d0_1cc": data.get("bed_d0_1cc", 0.0)
                                }
                            for point_data in json_content.get("point_dose_results", {}):
                                previous_brachy_bed_data[point_data["name"]] = point_data.get("BED_this_plan", 0.0)
                            previous_brachy_data = previous_brachy_bed_data
                            previous_brachy_data_file.seek(0)

                    args = argparse.Namespace(
                        data_dir=tmpdir_analysis,
                        ebrt_dose=ebrt_dose,
                        previous_brachy_data=previous_brachy_data,
                        output_html=os.path.join(tmpdir_analysis, "report.html"),
                        alpha_beta_ratios=ab_ratios,
                        selected_point_names=st.session_state.selected_point_names,
                        custom_constraints=templates[st.session_state.current_template_name],
                    )

                    results = run_analysis(args, selected_point_names=st.session_state.selected_point_names, dose_point_mapping=manual_dose_point_mapping, custom_constraints=args.custom_constraints, num_fractions_delivered=num_fractions_delivered)

                    # --- Start Channel Mapping Validation ---
                    if selected_template_name == "Cylinder HDR":
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
                                st.dataframe(pd.DataFrame(target_dvh_data))
                            else:
                                st.info("No target volume DVH data available.")

                            st.subheader("OAR DVH Results")
                            if oar_dvh_data:
                                # Create a new list with the desired structure (spanning effect)
                                restructured_data = []
                                # Initial DataFrame to make grouping easier
                                temp_oar_df = pd.DataFrame(oar_dvh_data)
                                
                                for organ_name in temp_oar_df['Organ'].unique():
                                    organ_group = temp_oar_df[temp_oar_df['Organ'] == organ_name]
                                    
                                    # Row 1 (D0.1cc)
                                    d0_1cc_row = organ_group[organ_group['Dose Metric'] == 'D0.1cc']
                                    if not d0_1cc_row.empty:
                                        restructured_data.append(d0_1cc_row.iloc[0].to_dict())
                                    
                                    # Row 2 (D1cc)
                                    d1cc_row = organ_group[organ_group['Dose Metric'] == 'D1cc']
                                    if not d1cc_row.empty:
                                        row_data = d1cc_row.iloc[0].to_dict()
                                        row_data['Organ'] = organ_name
                                        row_data['Volume (cc)'] = None
                                        restructured_data.append(row_data)

                                    # Row 3 (D2cc)
                                    d2cc_row = organ_group[organ_group['Dose Metric'] == 'D2cc']
                                    if not d2cc_row.empty:
                                        row_data = d2cc_row.iloc[0].to_dict()
                                        row_data['Organ'] = organ_name
                                        row_data['Volume (cc)'] = None
                                        restructured_data.append(row_data)

                                if restructured_data:
                                    final_oar_df = pd.DataFrame(restructured_data)

                                    # This styling function works on the whole table at once (axis=None)
                                    def style_oar_rows(df):
                                        styles = pd.DataFrame('', index=df.index, columns=df.columns)
                                        organ_groups = df['Organ'].ffill()
                                        current_constraints = st.session_state.custom_constraints

                                        for organ_name in organ_groups.unique():
                                            group_indices = df[organ_groups == organ_name].index
                                            d2cc_row_df = df.loc[group_indices]
                                            d2cc_row_df = d2cc_row_df[d2cc_row_df['Dose Metric'] == 'D2cc']
                                            
                                            if not d2cc_row_df.empty:
                                                # Get the specific index of the D2cc row
                                                d2cc_index = d2cc_row_df.index[0]
                                                eqd2_value = d2cc_row_df['EQD2 (Gy)'].iloc[0]

                                                if pd.notna(eqd2_value) and organ_name in current_constraints and "D2cc" in current_constraints[organ_name]:
                                                    constraint_data = current_constraints[organ_name]['D2cc']
                                                    max_val = constraint_data['max']
                                                    warn_val = constraint_data.get('warning')
                                                    
                                                    style_str = ''
                                                    if eqd2_value > max_val:
                                                        style_str = 'background-color: #dc3545; color: white'
                                                    elif warn_val is not None and eqd2_value >= warn_val:
                                                        style_str = 'background-color: #ffc107; color: black'
                                                    else:
                                                        style_str = 'background-color: #28a745; color: white'
                                                    
                                                    # Apply the style ONLY to the D2cc row's index
                                                    styles.loc[d2cc_index] = style_str
                                        return styles

                                    st.dataframe(final_oar_df.style.apply(style_oar_rows, axis=None))
                            else:
                                st.info("No OAR DVH data available.")

                        with tab2:
                            st.subheader("Point Dose Results")
                            point_dose_df = pd.DataFrame(results["point_dose_results"])

                            def style_point_dose_rows(row):
                                style = [''] * len(row)
                                if 'Constraint Status' in row and row['Constraint Status'] == 'Pass':
                                    style = ['background-color: #28a745; color: white'] * len(row)
                                elif 'Constraint Status' in row and row['Constraint Status'] == 'Fail':
                                    style = ['background-color: #dc3545; color: white'] * len(row)
                                return style

                            if not point_dose_df.empty:
                                st.dataframe(point_dose_df.style.apply(style_point_dose_rows, axis=1))
                            else:
                                st.info("No point dose data available.")
                        
                        with tab3:
                            st.subheader("Report")
                            html_report = results.get('html_report', '')
                            if html_report:
                                st.components.v1.html(html_report, height=600, scrolling=True)
                                
                                export_data = {
                                    "patient_name": results["patient_name"],
                                    "patient_mrn": results["patient_mrn"],
                                    "plan_date": results["plan_date"],
                                    "plan_time": results["plan_time"],
                                    "source_info": results["source_info"],
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
                                    st.error(f"Could not generate PDF. {e}")
                            else:
                                st.warning("Could not generate HTML report.")

                else:
                    st.error("Please upload all required DICOM files (RTDOSE, RTSTRUCT, RTPLAN).")
        else:
            st.error("Please upload DICOM files.")

if __name__ == "__main__":
    main()
