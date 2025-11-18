import streamlit as st
import argparse
import sys
import os
import pydicom
import pandas as pd
import json
import tempfile

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.main import generate_html_report, convert_html_to_pdf
from src.dicom_parser import get_plan_data, get_dose_point_mapping, get_structure_data
from src.main import main as run_analysis
from src.config import templates
from src.calculations import calculate_optimization_goal

def main():
    st.set_page_config(layout="wide")
    
    # --- 👇 PASTE THE CSS BLOCK HERE 👇 ---
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
    # ------------------------------------

    # --- Callback Functions ---
    def update_optimization_goals():
        """Calculates and updates the optimization goals in the session state."""
        st.session_state.optimization_goals = []
        oar_constraints = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
        
        previous_brachy_bed_per_organ = {}
        if 'json_content' in st.session_state:
            json_content = st.session_state.json_content
            for organ, data in json_content.get("dvh_results", {}).items():
                alpha_beta = st.session_state.ab_ratios.get(organ, 3.0)
                dose_fx_list = data.get("dose_fx", {}).get("d2cc_gy_per_fraction", [])
                total_prev_bed = sum([fx * (1 + fx / alpha_beta) for fx in dose_fx_list])
                previous_brachy_bed_per_organ[organ] = total_prev_bed
        
        for organ, constraints in oar_constraints.items():
            total_eqd2_constraint = constraints.get("D2cc", {}).get("max")
            alpha_beta = st.session_state.ab_ratios.get(organ, 3.0)
            previous_brachy_bed = previous_brachy_bed_per_organ.get(organ, 0.0)
            if total_eqd2_constraint is not None:
                goal = calculate_optimization_goal(
                    total_eqd2_constraint=total_eqd2_constraint, alpha_beta=alpha_beta,
                    ebrt_dose=st.session_state.ebrt_total_dose, ebrt_fractions=st.session_state.ebrt_num_fractions,
                    previous_brachy_bed=previous_brachy_bed, num_new_brachy_fractions=st.session_state.proposed_brachy_num_fx
                )
                st.session_state.optimization_goals.append({
                    "Organ": organ, "Total EQD2 Constraint (Gy)": total_eqd2_constraint,
                    "Max D2cc per Fraction (Gy)": goal
                })
    
    def process_json_upload():
        prev_brachy_file = st.session_state.get('prev_brachy_uploader')
        if prev_brachy_file:
            try:
                prev_brachy_file.seek(0)
                st.session_state.json_content = json.loads(prev_brachy_file.read().decode("utf-8"))
            except Exception as e:
                st.error(f"Error reading uploaded JSON file: {e}")
                if 'json_content' in st.session_state:
                    del st.session_state.json_content
        else:
            if 'json_content' in st.session_state:
                del st.session_state.json_content
                update_optimization_goals() # Trigger calculation after processing
    
    def clear_uploads():
        st.session_state.widget_key_suffix += 1
        keys_to_delete = ['results', 'structure_mapping', 'manual_mapping', 'optimization_goals']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]

    def clear_results():
        if 'results' in st.session_state:
            del st.session_state['results']

    def calculate_dose_per_fraction():
        if st.session_state.ebrt_num_fractions > 0:
            st.session_state.ebrt_fraction_dose = st.session_state.ebrt_total_dose / st.session_state.ebrt_num_fractions
        else:
            st.session_state.ebrt_fraction_dose = 0.0
        update_optimization_goals()

    def calculate_total_dose():
        st.session_state.ebrt_total_dose = st.session_state.ebrt_fraction_dose * st.session_state.ebrt_num_fractions
        update_optimization_goals()

    def reset_doses_to_default():
        template_name = st.session_state.get("template_selector", st.session_state.current_template_name)
        if "Cylinder" in template_name:
            st.session_state.proposed_brachy_dose_fx = 5.0
            st.session_state.proposed_brachy_num_fx = 5
        else:
            st.session_state.proposed_brachy_dose_fx = 7.0
            st.session_state.proposed_brachy_num_fx = 4
        st.session_state.ebrt_total_dose = 45.0
        st.session_state.ebrt_num_fractions = 25
        st.session_state.ebrt_fraction_dose = 1.8
        if 'optimization_goals' in st.session_state:
            del st.session_state.optimization_goals

    def on_template_change():
        st.session_state.current_template_name = st.session_state.template_selector
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
        st.session_state.custom_constraints = templates[st.session_state.current_template_name].copy()
        reset_doses_to_default()
        clear_results()

    # --- Session State Initialization ---
    if "current_template_name" not in st.session_state:
        st.session_state.current_template_name = "Cervix HDR - EMBRACE II"
    if "ab_ratios" not in st.session_state:
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
    if "custom_constraints" not in st.session_state:
        st.session_state.custom_constraints = templates[st.session_state.current_template_name].copy()
    if 'ebrt_total_dose' not in st.session_state:
        st.session_state.ebrt_total_dose = 45.0
    if 'ebrt_num_fractions' not in st.session_state:
        st.session_state.ebrt_num_fractions = 25
    if 'ebrt_fraction_dose' not in st.session_state:
        st.session_state.ebrt_fraction_dose = 1.8
    if 'proposed_brachy_dose_fx' not in st.session_state:
        st.session_state.proposed_brachy_dose_fx = 7.0
    if 'proposed_brachy_num_fx' not in st.session_state:
        st.session_state.proposed_brachy_num_fx = 4
    if 'widget_key_suffix' not in st.session_state:
        st.session_state.widget_key_suffix = 0

    # --- Sidebar ---
    with st.sidebar:
        st.header("Treatment Parameters")
        st.write(f"**Template:** {st.session_state.current_template_name}")
        st.markdown("---")
        st.subheader("EBRT Dose")
        st.number_input("Total Dose (Gy)", key='ebrt_total_dose', on_change=calculate_dose_per_fraction)
        st.number_input("Number of Fractions", min_value=1, step=1, key='ebrt_num_fractions', on_change=calculate_dose_per_fraction)
        st.number_input("Dose per Fraction (Gy)", key='ebrt_fraction_dose', on_change=calculate_total_dose, format="%.2f")
        st.markdown("---")
        st.subheader("Proposed Brachytherapy")
        st.number_input("Dose per Fraction (Gy)", min_value=0.0, step=0.5, key='proposed_brachy_dose_fx', on_change=update_optimization_goals())
        st.number_input("Number of Fractions", min_value=1, step=1, key='proposed_brachy_num_fx', on_change=update_optimization_goals())
        st.markdown("---")
        st.button("Reset Doses to Default", on_click=reset_doses_to_default, use_container_width=True)
        st.button("Clear Uploads", on_click=clear_uploads, use_container_width=True)
        st.button("Clear Results", on_click=clear_results, use_container_width=True)

    # --- Main Page Content ---
    st.title("Brachytherapy Evaluation and Analysis Module")

    pre_planning_tab, plan_analysis_tab, print_plan_tab = st.tabs([
        "📝 Pre-Planning", "🔬 Plan Analysis", "📄 Print Plan"
    ])

    # ==============================================================================
    # TAB 1: PRE-PLANNING
    # ==============================================================================
    with pre_planning_tab:
        st.header("Step 1: Define Treatment Parameters")
        st.markdown("Use this section to calculate OAR dose limits **before** creating a plan to set clear optimization goals.")
        st.subheader("Constraint Template")
        template_names = list(templates.keys())
        st.selectbox("Select Template", options=template_names, index=template_names.index(st.session_state.current_template_name), key="template_selector", on_change=on_template_change)
        with st.expander("View Current Constraints"):
            target_constraints = st.session_state.custom_constraints.get("constraints", {}).get("target_constraints", {})
            oar_constraints = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
            t_col, o_col = st.columns(2)
            with t_col:
                st.subheader("Target Volumes")
                if not target_constraints:
                    st.write("No target constraints defined.")
                else:
                    for organ, constraints in target_constraints.items():
                        st.markdown(f"**{organ}**")
                        for key, value in constraints.items():
                            if key != 'unit':
                                st.markdown(f"- {key}: **{value}** Gy")
            with o_col:
                st.subheader("Organs at Risk")
                if not oar_constraints:
                    st.write("No OAR constraints defined.")
                else:
                    for organ, constraints in oar_constraints.items():
                        st.markdown(f"**{organ}**")
                        for d_metric, d_values in constraints.items():
                            st.markdown(f"  - **{d_metric}**")
                            for key, value in d_values.items():
                                if key != 'unit':
                                    st.markdown(f"    - {key}: **{value}** Gy")
        if st.session_state.current_template_name == "Custom":
            with st.expander("Customize Template", expanded=True):
                st.header("Alpha/Beta Ratios")
                for organ, val in st.session_state.ab_ratios.items():
                    st.session_state.ab_ratios[organ] = st.number_input(f"{organ}", value=float(val), key=f"ab_{organ}_{st.session_state.widget_key_suffix}")
                st.header("Constraints")
                target_constraints = st.session_state.custom_constraints.get("constraints", {}).get("target_constraints", {})
                oar_constraints = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
                t_col, o_col = st.columns(2)
                with t_col:
                    st.subheader("Target Volumes")
                    for organ, constraints in target_constraints.items():
                        st.write(f"**{organ}**")
                        for key, value in constraints.items():
                            if key != 'unit':
                                st.session_state.custom_constraints["constraints"]["target_constraints"][organ][key] = st.number_input(f"{key} (Gy)", value=float(value), key=f"con_{organ}_{key}_{st.session_state.widget_key_suffix}")
                with o_col:
                    st.subheader("Organs at Risk")
                    for organ, constraints in oar_constraints.items():
                        st.write(f"**{organ}**")
                        for d_metric, d_values in constraints.items():
                            for key, value in d_values.items():
                                if key != 'unit':
                                    st.session_state.custom_constraints["constraints"]["oar_constraints"][organ][d_metric][key] = st.number_input(f"{d_metric} {key} (Gy)", value=float(value), key=f"con_{organ}_{d_metric}_{key}_{st.session_state.widget_key_suffix}")
        st.subheader("Previous Brachytherapy Data")
        st.file_uploader("Upload previous brachy data (optional .json)", type=["json"], key="prev_brachy_uploader", on_change=process_json_upload)
        
        # --- START: Corrected Expander Logic ---
        # This expander will now appear as soon as both the JSON and structure data are processed and ready.
        if 'json_content' in st.session_state and 'structure_data' in st.session_state:
            with st.expander("Confirm Structure Mapping for Dose Accumulation", expanded=True):
                st.info("Match structures from the **current plan** to the standardized names from the **uploaded JSON**.")
                
                if 'confirmed_structure_mapping' not in st.session_state:
                    st.session_state.confirmed_structure_mapping = {}

                try:
                    # 1. Get structure names from the processed JSON content in session state
                    json_structure_names = [name.upper() for name in st.session_state.json_content.get("dvh_results", {}).keys()]

                    # 2. Get structure names from the session state
                    current_dicom_structure_names = list(st.session_state['structure_data'].keys())

                    # 3. Propose an automatic mapping using fuzzy matching
                    from fuzzywuzzy import process
                    proposed_mapping = {}
                    for current_name in current_dicom_structure_names:
                        best_match, score = process.extractOne(current_name, json_structure_names)
                        if score > 70:
                            proposed_mapping[current_name] = best_match
                        else:
                            proposed_mapping[current_name] = None

                    # 4. Create the dropdowns for user confirmation
                    for current_name in current_dicom_structure_names:
                        default_selection = st.session_state.confirmed_structure_mapping.get(current_name, proposed_mapping.get(current_name))
                        
                        options = ["Ignore"] + json_structure_names
                        try:
                            default_index = options.index(default_selection)
                        except ValueError:
                            default_index = 0 # Default to "Ignore"

                        st.session_state.confirmed_structure_mapping[current_name] = st.selectbox(
                            f"'{current_name}' maps to:",
                            options=options,
                            index=default_index,
                            key=f"confirm_map_{current_name}"
                        )

                except Exception as e:
                    st.error(f"Could not process structure mapping: {e}")
        # --- END: Corrected Expander Logic ---

        # --- START: ADD THIS NEW ELIF BLOCK ---
        elif 'json_content' in st.session_state and 'structure_data' not in st.session_state:
            st.info("Previous treatment data loaded. See the new plan goals below or go to the '🔬 Plan Analysis' tab and upload the new DICOM files to map structures for dose accumulation.")
        # --- END: NEW ELIF BLOCK ---

        st.markdown("---")
        if 'optimization_goals' in st.session_state and st.session_state.optimization_goals:
            st.subheader("Optimization Goals")
            st.markdown(f"The following D2cc limits are calculated for a plan with **{st.session_state.proposed_brachy_num_fx}** new brachytherapy fraction(s).")
            df_goals = pd.DataFrame(st.session_state.optimization_goals)
            st.dataframe(df_goals.style.format({"Total EQD2 Constraint (Gy)": "{:.1f}", "Max D2cc per Fraction (Gy)": "{:.2f}"}), use_container_width=True)

    # ==============================================================================
    # TAB 2: PLAN ANALYSIS
    # ==============================================================================
    with plan_analysis_tab:
        st.header("Step 2: Upload and Analyze a Completed Plan")
        st.markdown("Upload the DICOM files from a completed brachytherapy plan to evaluate DVH metrics against the defined constraints.")
        st.markdown("Be sure to update the proposed brachytherapy parameters in the sidebar before running the analysis.")
        st.subheader("Upload DICOM Files")
        uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, and RTPLAN files", type=["dcm", "DCM"], accept_multiple_files=True, key=f"dicom_uploader_{st.session_state.widget_key_suffix}", on_change=clear_results)
        
        # --- START: New Early RTSTRUCT Processing ---
        # This block runs as soon as files are uploaded on this tab.
        if uploaded_files:
            # Find the RTSTRUCT file among the uploads
            rtstruct_file = None
            for up_file in uploaded_files:
                up_file.seek(0)
                try:
                    ds = pydicom.dcmread(up_file, stop_before_pixels=True, force=True)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure Set Storage
                        rtstruct_file = up_file
                        break
                except Exception:
                    continue # Not a valid DICOM, or not the one we want

            # If we found it, parse it and save the data to the session state
            if rtstruct_file:
                rtstruct_file.seek(0)
                st.session_state['structure_data'] = get_structure_data(pydicom.dcmread(rtstruct_file))
        # --- END: New Early RTSTRUCT Processing ---

        structure_data, plan_data_from_dicom = {}, {}
        if uploaded_files:
            with tempfile.TemporaryDirectory() as tmpdir:
                rtstruct_file_path, rtplan_file_path = None, None
                for up_file in uploaded_files:
                    file_path = os.path.join(tmpdir, up_file.name)
                    up_file.seek(0)
                    with open(file_path, "wb") as f: f.write(up_file.getbuffer())
                    try:
                        ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': rtstruct_file_path = file_path
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': rtplan_file_path = file_path
                    except Exception: pass
                
                with st.expander("Structure & Dose Point Mapping", expanded=True):
                    if rtstruct_file_path:
                        structure_data = get_structure_data(pydicom.dcmread(rtstruct_file_path))
                        st.markdown("**Structure Mapping**")
                        if 'structure_mapping' not in st.session_state: st.session_state.structure_mapping = {}
                        mapping_options = ["Ignore", "Bladder", "Rectum", "Sigmoid", "Bowel", "GTV", "HRCTV"]
                        def get_default_mapping(structure_name):
                            name_lower = structure_name.lower()
                            if 'blad' in name_lower: return "Bladder"
                            if 'rect' in name_lower: return "Rectum"
                            if 'sigm' in name_lower: return "Sigmoid"
                            if 'bowel' in name_lower: return "Bowel"
                            if 'gtv' in name_lower: return "GTV"
                            if 'hrctv' in name_lower or 'hr-ctv' in name_lower: return "HRCTV"
                            return "Ignore"
                        for s_name in structure_data.keys():
                            default_map = st.session_state.structure_mapping.get(s_name, get_default_mapping(s_name))
                            st.session_state.structure_mapping[s_name] = st.selectbox(
                                f"Map '{s_name}' to constraint:", options=mapping_options, 
                                index=mapping_options.index(default_map), key=f"map_{s_name}"
                            )
                    if rtplan_file_path:
                        plan_data_from_dicom = get_plan_data(rtplan_file_path)
                        constraints = st.session_state.custom_constraints.get("point_dose_constraints", {})
                        auto_map = get_dose_point_mapping(rtplan_file_path, constraints)
                        st.markdown("**Dose Point Mapping**")
                        if 'manual_mapping' not in st.session_state: st.session_state.manual_mapping = {}
                        st.session_state.manual_mapping = {**auto_map, **st.session_state.manual_mapping}
                        for p_name in [dr['name'] for dr in plan_data_from_dicom.get('dose_references', [])]:
                            c_points = ["N/A"] + list(constraints.keys())
                            current_map = st.session_state.manual_mapping.get(p_name, "N/A")
                            if current_map not in c_points: current_map = "N/A"
                            st.session_state.manual_mapping[p_name] = st.selectbox(f"Map '{p_name}':", c_points, index=c_points.index(current_map), key=f"map_point_{p_name}")

        if st.button("Run Analysis", type="primary", use_container_width=True):
            if uploaded_files:
                with tempfile.TemporaryDirectory() as tmpdir_analysis:
                    files_to_sort, patient_ids = {}, set()
                    has_rtplan, has_rtstruct, has_rtdose = False, False, False
                    for up_file in uploaded_files:
                        file_path = os.path.join(tmpdir_analysis, up_file.name)
                        with open(file_path, "wb") as f:
                            up_file.seek(0)
                            f.write(up_file.getbuffer())
                        try:
                            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                            patient_ids.add(ds.PatientID)
                            if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2':
                                files_to_sort[file_path] = "RTDOSE"; has_rtdose = True
                            elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3':
                                files_to_sort[file_path] = "RTst"; has_rtstruct = True
                            elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5':
                                files_to_sort[file_path] = "RTPLAN"; has_rtplan = True
                        except Exception as e:
                            st.warning(f"Could not read or classify file {up_file.name}: {e}")
                    proceed = True
                    if not (has_rtplan and has_rtstruct and has_rtdose):
                        st.error("Error: Please upload all three required DICOM files (RT Plan, RT Structure Set, and RT Dose).")
                        proceed = False
                    if len(patient_ids) > 1:
                        st.error(f"Error: Mismatched Patient IDs found across files: {list(patient_ids)}. Please upload files for a single patient.")
                        proceed = False
                    if proceed:
                        for path, dir_name in files_to_sort.items():
                            target_dir = os.path.join(tmpdir_analysis, dir_name)
                            os.makedirs(target_dir, exist_ok=True)
                            os.rename(path, os.path.join(target_dir, os.path.basename(path)))
                        prev_brachy_data_main = {}
                        prev_brachy_file = st.session_state.get('prev_brachy_uploader')
                        if prev_brachy_file:
                            prev_brachy_file.seek(0)
                            prev_brachy_data_main = json.loads(prev_brachy_file.read().decode("utf-8"))
                            if 'point_dose_results' in prev_brachy_data_main and isinstance(prev_brachy_data_main['point_dose_results'], list):
                                transformed_points = {item.get('name', f'point_{i}'): item for i, item in enumerate(prev_brachy_data_main['point_dose_results'])}
                                prev_brachy_data_main['point_dose_results'] = transformed_points
                        args = argparse.Namespace(
                            data_dir=tmpdir_analysis, ebrt_dose=st.session_state.ebrt_total_dose,
                            ebrt_fractions=st.session_state.ebrt_num_fractions, previous_brachy_data=prev_brachy_data_main,
                            output_html=None, alpha_beta_ratios=st.session_state.ab_ratios,
                            custom_constraints=st.session_state.custom_constraints
                        )
                        with st.spinner("Analyzing plan... this may take a moment."):
                            st.session_state.results = run_analysis(
                                args, structure_data, plan_data_from_dicom,
                                dose_point_mapping=[(k, v) for k, v in st.session_state.get('manual_mapping', {}).items() if v != "N/A"],
                                custom_constraints=st.session_state.custom_constraints,
                                num_fractions_delivered=st.session_state.proposed_brachy_num_fx,
                                ebrt_fractions=st.session_state.ebrt_num_fractions,
                                structure_mapping=st.session_state.get('structure_mapping', {}),
                                confirmed_structure_mapping=st.session_state.get('confirmed_structure_mapping', {}) # ADD THIS LINE
                            )
            else:
                st.error("Please upload DICOM files to run the analysis.")

        st.markdown("---")

        if 'results' in st.session_state:
            results = st.session_state.results
            if not results:
                 st.warning("Analysis returned empty results. Please check the DICOM files and mappings.")
            elif 'error' in results:
                st.error(f"Analysis Failed: {results['error']}")
            else:
                st.header("Analysis Results")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Patient Name", results.get('patient_name', 'N/A').replace('^', ' '))
                col2.metric("Patient ID", results.get('patient_mrn', 'N/A'))
                col3.metric("Plan Name", results.get('plan_name', 'N/A'))
                col4, col5, _ = st.columns(3)
                col4.metric("Plan Date", results.get('plan_date', 'N/A'))
                col5.metric("Plan Time", results.get('plan_time', 'N/A'))
                if results.get("plan_time_warning"): st.warning(results["plan_time_warning"])
                if results.get('calculation_number_of_fractions') != results.get('planned_number_of_fractions'):
                    st.warning("Warning: Planned fractions and calculation fractions differ.")
                st.markdown("---")
                
                dvh_results = results.get('dvh_results', {})
                point_dose_results = results.get('point_dose_results', [])
                
                OAR_NAMES = ["Bladder", "Rectum", "Sigmoid", "Bowel"]
                TARGET_NAMES = ["GTV", "HRCTV"]
                
                st.markdown("##### **Organs at Risk (OAR) DVH Results**")
                oars_to_display = {k: v for k, v in dvh_results.items() if k in OAR_NAMES}
                
                if oars_to_display:
                    previous_brachy_data = st.session_state.get('json_content', {})
                    num_new_fractions = st.session_state.proposed_brachy_num_fx
                    
                    # 1. Calculate previous fractions
                    previous_fractions = 0
                    if previous_brachy_data:
                        max_len = 0
                        if previous_brachy_data.get("dvh_results"):
                            for organ_data in previous_brachy_data["dvh_results"].values():
                                for dose_list in organ_data.get("dose_fx", {}).values():
                                    if isinstance(dose_list, list):
                                        max_len = max(max_len, len(dose_list))
                        previous_fractions = max_len

                    # 2. Determine total fractions for display
                    total_display_fractions = previous_fractions + num_new_fractions
                    fraction_headers = [f"Fx {i+1} Dose (Gy)" for i in range(total_display_fractions)]

                    restructured_data = []
                    
                    # Helper to get historical doses for a specific organ and metric
                    def get_historical_doses(organ_name, metric_key):
                         if not previous_brachy_data: return []
                         # Try to find the organ in the JSON data (case-insensitive search)
                         json_dvh = previous_brachy_data.get("dvh_results", {})
                         for key, val in json_dvh.items():
                             if key.lower() == organ_name.lower():
                                 return val.get("dose_fx", {}).get(metric_key, [])
                         return []

                    for organ, metrics in oars_to_display.items():
                         # Prepare rows
                         base_row = {'Organ': organ, 'Volume (cc)': f"{metrics.get('volume_cc', 0):.2f}"}
                         
                         metric_map = [
                             ('D0.1cc', 'd0_1cc_gy_per_fraction', 'eqd2_d0_1cc'),
                             ('D1cc',   'd1cc_gy_per_fraction',   'eqd2_d1cc'),
                             ('D2cc',   'd2cc_gy_per_fraction',   'eqd2_d2cc')
                         ]

                         for i, (m_name, m_key, m_eqd2) in enumerate(metric_map):
                             # Create the row structure
                             row = base_row.copy() if i == 0 else {'Organ': '', 'Volume (cc)': ''}
                             row['Dose Metric'] = m_name
                             
                             # Get dose data
                             hist_doses = get_historical_doses(organ, m_key)
                             current_dose = metrics.get(m_key, 0)
                             
                             # Combine: Historical + [Current * New Fractions]
                             full_dose_list = hist_doses + ([current_dose] * num_new_fractions)
                             
                             # Populate fraction columns
                             for idx, header in enumerate(fraction_headers):
                                 if idx < len(full_dose_list):
                                     val = full_dose_list[idx]
                                     row[header] = f"{val:.2f}" if val is not None else "-"
                                 else:
                                     row[header] = "-"

                             # Add EQD2 and Constraint Status
                             row['EQD2 (Gy)'] = f"{metrics.get(m_eqd2, 0):.2f}"
                             
                             if m_name == 'D2cc':
                                 is_met_str = results.get('constraint_evaluation', {}).get(organ, {}).get('EQD2_met', 'False')
                                 row['Constraint Status'] = "Met" if str(is_met_str).lower() == 'true' else "NOT Met"
                                 dose_to_meet = metrics.get('dose_to_meet_constraint', 'N/A')
                                 row['Dose to Meet Constraint (Gy)'] = f"{dose_to_meet:.2f}" if isinstance(dose_to_meet, (int, float)) else "N/A"
                             else:
                                 row['Constraint Status'] = 'N/A'
                                 row['Dose to Meet Constraint (Gy)'] = ''
                             
                             restructured_data.append(row)

                    final_oar_df = pd.DataFrame(restructured_data)
                    
                    # Apply styling
                    def style_oar_rows(row):
                        if row['Constraint Status'] == 'Met':
                            return ['background-color: rgba(40, 167, 69, 0.2)'] * len(row)
                        elif row['Constraint Status'] == 'NOT Met':
                            return ['background-color: rgba(220, 53, 69, 0.2)'] * len(row)
                        return [''] * len(row)

                    # Reorder columns to ensure fractions are in the middle
                    cols = ['Organ', 'Volume (cc)', 'Dose Metric'] + fraction_headers + ['EQD2 (Gy)', 'Constraint Status', 'Dose to Meet Constraint (Gy)']
                    final_oar_df = final_oar_df[cols]
                    
                    st.dataframe(final_oar_df.style.apply(style_oar_rows, axis=1), use_container_width=True, hide_index=True)
                else:
                    st.info("No OAR DVH data to display. Check structure mappings.")

                st.markdown("---")

                st.markdown("##### **Target Volume DVH Results**")
                
                targets_to_display = {k: v for k, v in dvh_results.items() if k in TARGET_NAMES}

                if targets_to_display:
                    # --- Re-calculate total fractions for display ---
                    previous_brachy_data = st.session_state.get('json_content', {})
                    num_new_fractions = st.session_state.proposed_brachy_num_fx
                    
                    previous_fractions = 0
                    if previous_brachy_data:
                        max_len = 0
                        if previous_brachy_data.get("dvh_results"):
                            for organ_data in previous_brachy_data["dvh_results"].values():
                                for dose_list in organ_data.get("dose_fx", {}).values():
                                    if isinstance(dose_list, list):
                                        max_len = max(max_len, len(dose_list))
                        previous_fractions = max_len
                    
                    total_display_fractions = previous_fractions + num_new_fractions
                    fraction_headers = [f"Fx {i+1} Dose (Gy)" for i in range(total_display_fractions)]
                    # -------------------------------------------------------------------

                    restructured_target_data = []
                    constraint_eval = results.get('constraint_evaluation', {})
                    
                    # Retrieve the confirmed mapping from session state (the one that fixed the calc)
                    confirmed_map = st.session_state.get('confirmed_structure_mapping', {})

                    # Helper to normalize name for constraint lookup (HRCTV -> Hrctv)
                    def normalize_for_lookup(name):
                        return name.strip().lower().capitalize()

                    # --- ROBUST LOOKUP HELPER ---
                    def get_historical_doses(organ_name, metric_key):
                         if not previous_brachy_data: return []
                         json_dvh = previous_brachy_data.get("dvh_results", {})
                         target_json_name = None

                         # 1. Priority: Use the explicit user mapping if available
                         if organ_name in confirmed_map:
                             mapped = confirmed_map[organ_name]
                             if mapped and mapped != "Ignore":
                                 target_json_name = mapped

                         # 2. Fallback: Fuzzy match (lowercase, no hyphens)
                         if not target_json_name:
                             search_term = organ_name.lower().replace("-", "").replace("_", "")
                             for key in json_dvh.keys():
                                 if key.lower().replace("-", "").replace("_", "") == search_term:
                                     target_json_name = key
                                     break
                        
                         # 3. Retrieve data if key found
                         if target_json_name and target_json_name in json_dvh:
                             return json_dvh[target_json_name].get("dose_fx", {}).get(metric_key, [])
                         
                         return []
                    # ------------------------------

                    for organ, metrics in targets_to_display.items():
                        base_row = {'Structure': organ, 'Volume (cc)': f"{metrics.get('volume_cc', 0):.2f}"}
                        norm_organ = normalize_for_lookup(organ)

                        # --- Process D90 ---
                        row_d90 = {**base_row, 'Dose Metric': 'D90'}
                        
                        hist_d90 = get_historical_doses(organ, 'd90_gy_per_fraction')
                        curr_d90 = metrics.get('d90_gy_per_fraction', 0)
                        
                        # Pad historical list
                        padding_len = max(0, previous_fractions - len(hist_d90))
                        full_d90 = hist_d90 + ([None] * padding_len) + ([curr_d90] * num_new_fractions)
                        
                        for idx, header in enumerate(fraction_headers):
                            if idx < len(full_d90):
                                val = full_d90[idx]
                                row_d90[header] = f"{val:.2f}" if val is not None else "-"
                            else:
                                row_d90[header] = "-"
                        
                        row_d90['EQD2 (Gy)'] = f"{metrics.get('eqd2_d90', 0):.2f}"
                        
                        eval_key_d90 = f"{norm_organ} D90"
                        row_d90['Constraint Status'] = constraint_eval.get(eval_key_d90, {}).get("EQD2_status_D90", "N/A")
                        restructured_target_data.append(row_d90)

                        # --- Process D98 ---
                        row_d98 = {**base_row, 'Dose Metric': 'D98', 'Structure': '', 'Volume (cc)': ''}
                        
                        hist_d98 = get_historical_doses(organ, 'd98_gy_per_fraction')
                        curr_d98 = metrics.get('d98_gy_per_fraction', 0)
                        
                        padding_len = max(0, previous_fractions - len(hist_d98))
                        full_d98 = hist_d98 + ([None] * padding_len) + ([curr_d98] * num_new_fractions)

                        for idx, header in enumerate(fraction_headers):
                            if idx < len(full_d98):
                                val = full_d98[idx]
                                row_d98[header] = f"{val:.2f}" if val is not None else "-"
                            else:
                                row_d98[header] = "-"

                        row_d98['EQD2 (Gy)'] = f"{metrics.get('eqd2_d98', 0):.2f}"

                        eval_key_d98 = f"{norm_organ} D98"
                        if eval_key_d98 in constraint_eval:
                            status_d98 = constraint_eval[eval_key_d98].get("EQD2_status_D98", "N/A")
                        else:
                            status_d98 = "N/A"
                        row_d98['Constraint Status'] = status_d98

                        restructured_target_data.append(row_d98)

                    final_target_df = pd.DataFrame(restructured_target_data)
                    
                    # Reorder columns
                    cols = ['Structure', 'Volume (cc)', 'Dose Metric'] + fraction_headers + ['EQD2 (Gy)', 'Constraint Status']
                    final_target_df = final_target_df[cols]

                    # Style function
                    def style_target_rows(row):
                        status = row['Constraint Status']
                        if status == 'Met':
                            return ['background-color: rgba(40, 167, 69, 0.2)'] * len(row)
                        elif status == 'NOT Met':
                            return ['background-color: rgba(220, 53, 69, 0.2)'] * len(row)
                        return [''] * len(row)

                    st.dataframe(final_target_df.style.apply(style_target_rows, axis=1), use_container_width=True, hide_index=True)
                else:
                    st.info("No Target DVH data to display. Check structure mappings.")

                st.markdown("---")
                
                st.markdown("##### **Point Dose Results**")
                if point_dose_results:
                    st.dataframe(pd.DataFrame(point_dose_results), use_container_width=True, hide_index=True)
                else:
                    st.info("No Dose Point data to display.")
    
    # ==============================================================================
    # TAB 3: PRINT PLAN
    # ==============================================================================
    with print_plan_tab:
        st.header("Step 3: Generate and Download Reports")

        if 'results' not in st.session_state:
            st.info("Please run an analysis on the 'Plan Analysis' tab to generate reports.")
        else:
            results = st.session_state.results
            patient_name = results.get('patient_name', 'N/A').replace('^', '_')
            plan_name = results.get('plan_name', 'plan')
            
            st.markdown("---")
            st.subheader("Download Dose Summary (PDF)")
            st.markdown("This will generate a clean, printable PDF of the dose summary, suitable for export.")
            
            # --- PDF Download Button ---
            try:
                # 1. Re-generate the HTML content using the function from main.py
                # We use the data stored in session_state from the analysis run
                html_content = generate_html_report(
                    patient_name=results.get('patient_name', 'N/A'),
                    patient_mrn=results.get('patient_mrn', 'N/A'),
                    plan_name=results.get('plan_name', 'N/A'),
                    plan_date=results.get('plan_date', 'N/A'),
                    plan_time=results.get('plan_time', 'N/A'),
                    source_info=results.get('source_info', 'N/A'),
                    brachy_dose_per_fraction=results.get('brachy_dose_per_fraction', 0),
                    number_of_fractions=results.get('calculation_number_of_fractions', 1),
                    ebrt_dose=st.session_state.ebrt_total_dose,
                    ebrt_fractions=st.session_state.ebrt_num_fractions,
                    dvh_results=results.get('dvh_results', {}),
                    constraint_evaluation=results.get('constraint_evaluation', {}),
                    dose_references=[], # Not needed for this report
                    point_dose_results=results.get('point_dose_results', []),
                    output_path=None, # We're not saving it to a file here
                    alpha_beta_ratios=st.session_state.ab_ratios,
                    previous_brachy_data=st.session_state.get('json_content', {})
                )

                # 2. Convert the HTML string to a PDF in a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    convert_html_to_pdf(html_content, tmp_pdf.name)
                    
                    # 3. Read the generated PDF back into memory
                    with open(tmp_pdf.name, "rb") as f:
                        pdf_bytes = f.read()
                
                # 4. Offer the PDF bytes via the download button
                st.download_button(
                    label="Download PDF Report",
                    data=pdf_bytes,
                    file_name=f"Dose_Summary_{patient_name}_{plan_name}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
            except Exception as e:
                st.error(f"Could not generate PDF: {e}")
                st.error("Please ensure 'wkhtmltopdf' is correctly installed and accessible by the application.")

            
            st.markdown("---")
            st.subheader("Download Cumulative Brachy Data (JSON)")
            st.markdown("Save the cumulative dose data (previous fractions + this plan) to a new JSON file. This file can be uploaded for future treatment analysis.")

            # --- Cumulative JSON Download Button ---
            def create_cumulative_json():
                try:
                    # 1. Get old JSON and new results
                    old_json = st.session_state.get('json_content', {})
                    new_results = st.session_state.results
                    
                    # Create a deep copy to avoid modifying session state
                    new_cumulative_data = json.loads(json.dumps(old_json))
                    if "dvh_results" not in new_cumulative_data:
                        new_cumulative_data["dvh_results"] = {}
                    if "point_dose_results" not in new_cumulative_data:
                        new_cumulative_data["point_dose_results"] = {}

                    new_dvh = new_results.get('dvh_results', {})
                    num_new_fractions = new_results.get('calculation_number_of_fractions', 1)

                    # 2. Process DVH Results
                    for organ_name, new_data in new_dvh.items():
                        # Find matching organ key in the cumulative data (case/hyphen insensitive)
                        target_key = None
                        search_term = organ_name.lower().replace("-", "").replace("_", "")
                        for key in new_cumulative_data['dvh_results'].keys():
                            if key.lower().replace("-", "").replace("_", "") == search_term:
                                target_key = key
                                break
                        
                        if not target_key: # Organ wasn't in the old file, add it
                            target_key = organ_name 
                        
                        if target_key not in new_cumulative_data['dvh_results']:
                            new_cumulative_data['dvh_results'][target_key] = {"dose_fx": {}}
                        if "dose_fx" not in new_cumulative_data['dvh_results'][target_key]:
                             new_cumulative_data['dvh_results'][target_key]["dose_fx"] = {}
                        
                        dose_fx_map = new_cumulative_data['dvh_results'][target_key]["dose_fx"]

                        # Define all metrics to update
                        metric_keys = ['d0_1cc_gy_per_fraction', 'd1cc_gy_per_fraction', 'd2cc_gy_per_fraction',
                                       'd90_gy_per_fraction', 'd98_gy_per_fraction', 'd95_gy_per_fraction',
                                       'max_dose_gy_per_fraction', 'mean_dose_gy_per_fraction', 'min_dose_gy_per_fraction']
                        
                        for key in metric_keys:
                            old_list = dose_fx_map.get(key, [])
                            new_dose = new_data.get(key, 0.0) # Get the new dose from results
                            dose_fx_map[key] = old_list + ([new_dose] * num_new_fractions)
                    
                    # 3. Process Point Dose Results
                    new_points = new_results.get('point_dose_results', [])
                    for point in new_points:
                        point_name = point.get('name')
                        if not point_name: continue

                        if point_name not in new_cumulative_data['point_dose_results']:
                            new_cumulative_data['point_dose_results'][point_name] = {"dose_fx": []}
                        
                        old_list = new_cumulative_data['point_dose_results'][point_name].get('dose_fx', [])
                        new_dose = point.get('dose', 0.0) # This is dose_per_fraction
                        new_cumulative_data['point_dose_results'][point_name]['dose_fx'] = old_list + ([new_dose] * num_new_fractions)

                    # 4. Convert to string
                    return json.dumps(new_cumulative_data, indent=2)
                
                except Exception as e:
                    st.error(f"Error creating cumulative JSON: {e}")
                    return "{}"

            cumulative_json_str = create_cumulative_json()
            
            st.download_button(
                label="Download Cumulative JSON",
                data=cumulative_json_str,
                file_name=f"Cumulative_Brachy_Data_{patient_name}.json",
                mime="application/json",
                use_container_width=True,
                type="primary"
            )
if __name__ == "__main__":
    main()