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

from src.dicom_parser import get_plan_data, get_dose_point_mapping, get_structure_data
from src.main import main as run_analysis, convert_html_to_pdf, generate_dwell_time_sheet
from src.config import templates
from src.calculations import calculate_optimization_goal

def main():
    st.set_page_config(layout="wide")

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

        # --- Sidebar for Settings Display ---
    with st.sidebar:
        st.header("Current Settings")
        st.write(f"**Template:** {st.session_state.current_template_name}")
        st.markdown("---")
        
        st.subheader("EBRT Summary")
        st.metric("Total Dose (Gy)", f"{st.session_state.ebrt_total_dose:.2f}")
        st.metric("Number of Fractions", f"{st.session_state.ebrt_num_fractions}")
        st.metric("Dose per Fraction (Gy)", f"{st.session_state.ebrt_fraction_dose:.2f}")
        st.markdown("---")
        
        st.subheader("Proposed Brachytherapy")
        st.metric("Dose per Fraction (Gy)", f"{st.session_state.proposed_brachy_dose_fx:.2f}")
        st.metric("Number of Fractions", f"{st.session_state.proposed_brachy_num_fx}")

    def clear_results():
        if 'results' in st.session_state:
            del st.session_state.results

    # --- Injected CSS and Title ---
    st.markdown("""
    <style>
        [data-testid="stHeader"] {display: none;}
        h1, h2, h3, h4, h5, h6, summary { color: #FF5733 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("Brachytherapy Evaluation and Analysis Module")

    # --- Main Tab Structure ---
    pre_planning_tab, plan_analysis_tab, print_plan_tab = st.tabs([
        "📝 Pre-Planning", "🔬 Plan Analysis", "📄 Print Plan"
    ])

    # ==============================================================================
    # TAB 1: PRE-PLANNING
    # ==============================================================================
    with pre_planning_tab:
        st.header("Step 1: Define Treatment Parameters")
        st.markdown("Use this section to calculate OAR dose limits **before** creating a plan to set clear optimization goals.")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Constraint Template")
            template_names = list(templates.keys())
            
            def on_template_change():
                st.session_state.current_template_name = st.session_state.template_selector
                st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
                st.session_state.custom_constraints = templates[st.session_state.current_template_name].copy()
                
                template_name = st.session_state.current_template_name
                if "Cylinder" in template_name:
                    st.session_state.proposed_brachy_dose_fx = 5.0
                    st.session_state.proposed_brachy_num_fx = 5
                else:
                    st.session_state.proposed_brachy_dose_fx = 7.0
                    st.session_state.proposed_brachy_num_fx = 4
                
                if 'optimization_goals' in st.session_state:
                    del st.session_state.optimization_goals
                clear_results()

            st.selectbox("Select Template", options=template_names, index=template_names.index(st.session_state.current_template_name), key="template_selector", on_change=on_template_change)

            st.subheader("Proposed Brachytherapy Prescription")
            st.number_input("Proposed Dose per Fraction (Gy)", min_value=0.0, step=0.5, key='proposed_brachy_dose_fx')
            st.number_input("Proposed Number of Fractions", min_value=1, step=1, key='proposed_brachy_num_fx')

        with col2:
            st.subheader("EBRT Dose (Gy)")
            
            def calculate_dose_per_fraction():
                if st.session_state.ebrt_num_fractions > 0:
                    st.session_state.ebrt_fraction_dose = st.session_state.ebrt_total_dose / st.session_state.ebrt_num_fractions
                else:
                    st.session_state.ebrt_fraction_dose = 0.0

            def calculate_total_dose():
                st.session_state.ebrt_total_dose = st.session_state.ebrt_fraction_dose * st.session_state.ebrt_num_fractions
            
            st.number_input("Total Dose (Gy)", key='ebrt_total_dose', on_change=calculate_dose_per_fraction)
            st.number_input("Number of Fractions", min_value=0, step=1, key='ebrt_num_fractions', on_change=calculate_dose_per_fraction)
            st.number_input("Dose per Fraction (Gy)", key='ebrt_fraction_dose', on_change=calculate_total_dose, format="%.2f")

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
        st.file_uploader("Upload previous brachy data (optional .json)", type=["json"], key="prev_brachy_uploader")
        st.markdown("---")
        
        def reset_doses_to_default():
            template_name = st.session_state.template_selector
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
        
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            if st.button("Calculate Optimization Goals", type="primary", use_container_width=True):
                st.session_state.optimization_goals = []
                oar_constraints = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
                previous_brachy_bed_per_organ = {}
                prev_brachy_file = st.session_state.get('prev_brachy_uploader')

                if prev_brachy_file:
                    try:
                        prev_brachy_file.seek(0)
                        json_content = json.loads(prev_brachy_file.read().decode("utf-8"))
                        for organ, data in json_content.get("dvh_results", {}).items():
                            alpha_beta = st.session_state.ab_ratios.get(organ, 3.0)
                            dose_fx_list = data.get("dose_fx", {}).get("d2cc_gy_per_fraction", [])
                            total_prev_bed = sum([fx * (1 + fx / alpha_beta) for fx in dose_fx_list])
                            previous_brachy_bed_per_organ[organ] = total_prev_bed
                    except Exception as e:
                        st.error(f"Error parsing previous brachytherapy JSON: {e}")

                for organ, constraints in oar_constraints.items():
                    total_eqd2_constraint = constraints.get("D2cc", {}).get("max")
                    alpha_beta = st.session_state.ab_ratios.get(organ, 3.0)
                    previous_brachy_bed = previous_brachy_bed_per_organ.get(organ, 0.0)

                    if total_eqd2_constraint is not None:
                        goal = calculate_optimization_goal(
                            total_eqd2_constraint=total_eqd2_constraint,
                            alpha_beta=alpha_beta,
                            ebrt_dose=st.session_state.ebrt_total_dose,
                            ebrt_fractions=st.session_state.ebrt_num_fractions,
                            previous_brachy_bed=previous_brachy_bed,
                            num_new_brachy_fractions=st.session_state.proposed_brachy_num_fx
                        )
                        st.session_state.optimization_goals.append({
                            "Organ": organ,
                            "Total EQD2 Constraint (Gy)": total_eqd2_constraint,
                            "Max D2cc per Fraction (Gy)": goal
                        })
        with b_col2:
            st.button("Reset Doses to Default", on_click=reset_doses_to_default, use_container_width=True)

        if 'optimization_goals' in st.session_state and st.session_state.optimization_goals:
            st.subheader("🎯 Optimization Goals")
            st.markdown(f"The following D2cc limits are calculated for a plan with **{st.session_state.proposed_brachy_num_fx}** new brachytherapy fraction(s).")
            df_goals = pd.DataFrame(st.session_state.optimization_goals)
            st.dataframe(df_goals.style.format({"Total EQD2 Constraint (Gy)": "{:.1f}", "Max D2cc per Fraction (Gy)": "{:.2f}"}), use_container_width=True)

    # ==============================================================================
    # TAB 2: PLAN ANALYSIS
    # ==============================================================================
    with plan_analysis_tab:
        st.header("Step 2: Upload and Analyze a Completed Plan")

        st.subheader("Upload DICOM Files")
        uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, and RTPLAN files", type=["dcm", "DCM"], accept_multiple_files=True, key="dicom_uploader", on_change=clear_results)
        
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
                
                with st.expander("Structure & Dose Point Mapping"):
                    if rtstruct_file_path:
                        structure_data = get_structure_data(pydicom.dcmread(rtstruct_file_path))
                        st.markdown("**Structure Mapping**")
                        if 'structure_mapping' not in st.session_state: st.session_state.structure_mapping = {}
                        for s_name in structure_data.keys():
                            default_map = "TARGET" if any(x in s_name.lower() for x in ['gtv', 'ctv', 'hrctv']) else "OAR"
                            st.session_state.structure_mapping[s_name] = st.selectbox(f"Map '{s_name}':", ["TARGET", "OAR"], index=["TARGET", "OAR"].index(st.session_state.structure_mapping.get(s_name, default_map)), key=f"map_{s_name}")
                    
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
                    # --- CORRECTED: Combined validation and sorting logic ---
                    files_to_sort = {}
                    patient_ids = set()
                    has_rtplan, has_rtstruct, has_rtdose = False, False, False

                    # First, loop through to validate files and gather info
                    for up_file in uploaded_files:
                        file_path = os.path.join(tmpdir_analysis, up_file.name)
                        with open(file_path, "wb") as f:
                            up_file.seek(0)
                            f.write(up_file.getbuffer())
                        try:
                            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                            patient_ids.add(ds.PatientID)
                            if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': # RT Dose
                                files_to_sort[file_path] = "RTDOSE"
                                has_rtdose = True
                            elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RT Structure
                                files_to_sort[file_path] = "RTst"
                                has_rtstruct = True
                            elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RT Plan
                                files_to_sort[file_path] = "RTPLAN"
                                has_rtplan = True
                        except Exception as e:
                            st.warning(f"Could not read or classify file {up_file.name}: {e}")

                    # Now, run the safety checks
                    proceed = True
                    if not (has_rtplan and has_rtstruct and has_rtdose):
                        st.error("Error: Please upload all three required DICOM files (RT Plan, RT Structure Set, and RT Dose).")
                        proceed = False
                    
                    if len(patient_ids) > 1:
                        st.error(f"Error: Mismatched Patient IDs found across files: {list(patient_ids)}. Please upload files for a single patient.")
                        proceed = False

                    # --- CORRECTED: Analysis now runs ONLY if proceed is True ---
                    if proceed:
                        # Move files to their respective subdirectories
                        for path, dir_name in files_to_sort.items():
                            target_dir = os.path.join(tmpdir_analysis, dir_name)
                            os.makedirs(target_dir, exist_ok=True)
                            os.rename(path, os.path.join(target_dir, os.path.basename(path)))

                        # Handle previous brachytherapy data
                        prev_brachy_data_main = {}
                        prev_brachy_file = st.session_state.get('prev_brachy_uploader')
                        if prev_brachy_file:
                            prev_brachy_file.seek(0)
                            prev_brachy_data_main = json.loads(prev_brachy_file.read().decode("utf-8"))

                        args = argparse.Namespace(
                            data_dir=tmpdir_analysis,
                            ebrt_dose=st.session_state.ebrt_total_dose,
                            ebrt_fractions=st.session_state.ebrt_num_fractions,
                            previous_brachy_data=prev_brachy_data_main,
                            output_html=None,
                            alpha_beta_ratios=st.session_state.ab_ratios,
                            custom_constraints=st.session_state.custom_constraints
                        )
                        
                        with st.spinner("Analyzing plan... this may take a moment."):
                            st.session_state.results = run_analysis(
                                args,
                                structure_data,
                                plan_data_from_dicom,
                                dose_point_mapping=[(k, v) for k, v in st.session_state.get('manual_mapping', {}).items() if v != "N/A"],
                                custom_constraints=st.session_state.custom_constraints,
                                num_fractions_delivered=st.session_state.proposed_brachy_num_fx,
                                structure_mapping=st.session_state.get('structure_mapping', {})
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
                
                # --- FIX: Get patient/plan info from top level of results dict ---
                col1, col2, col3 = st.columns(3)
                col1.metric("Patient Name", results.get('patient_name', 'N/A').replace('^', ' '))
                col2.metric("Patient ID", results.get('patient_mrn', 'N/A'))
                col3.metric("Plan Name", results.get('plan_name', 'N/A'))

                # Second row for plan date and time
                col4, col5, col6 = st.columns(3)
                col4.metric("Plan Date", results.get('plan_date', 'N/A'))
                col5.metric("Plan Time", results.get('plan_time', 'N/A'))
                # An empty column (col6) is used to keep the layout clean and spaced out.
                
                # Time and Fraction warnings
                if results.get("plan_time_warning"):
                    st.warning(results["plan_time_warning"])

                if results.get('calculation_number_of_fractions') != results.get('planned_number_of_fractions'):
                    st.warning("Warning: The planned number of fractions and the number of fractions used for EQD2 calculations differ.")
                
                st.markdown("---")
                
                dvh_results = results.get('dvh_results', {})
                point_dose_results = results.get('point_dose_results', [])
                
                # Make sorting logic case-insensitive ---
                oar_dvh_raw = {}
                target_dvh_raw = {}
                structure_mapping = st.session_state.get('structure_mapping', {})
                # Create a version of the mapping with lowercase keys for robust matching
                mapping_lower = {k.lower(): v for k, v in structure_mapping.items()}

                for organ, metrics in dvh_results.items():
                    # Check the lowercase version of the organ name against the lowercase mapping
                    if mapping_lower.get(organ.lower()) == 'OAR':
                        oar_dvh_raw[organ] = metrics
                    elif mapping_lower.get(organ.lower()) == 'TARGET':
                        target_dvh_raw[organ] = metrics

                # --- OAR DVH Results Table (with updated keys) ---
                st.markdown("##### **Organs at Risk (OAR) DVH Results**")
                oar_dvh_data = []
                for organ, metrics in oar_dvh_raw.items():
                    oar_dvh_data.append({'Organ': organ, 'Volume (cc)': f"{metrics.get('volume_cc', 0):.2f}", 'Dose Metric': 'D0.1cc', 'EQD2 (Gy)': f"{metrics.get('eqd2_d0_1cc', metrics.get('bed_d0_1cc', 0)):.2f}", 'Constraint Met': 'N/A'})
                    oar_dvh_data.append({'Organ': '', 'Volume (cc)': '', 'Dose Metric': 'D1cc', 'EQD2 (Gy)': f"{metrics.get('eqd2_d1cc', metrics.get('bed_d1cc', 0)):.2f}", 'Constraint Met': 'N/A'})
                    is_met_str = results.get('constraint_evaluation', {}).get(organ, {}).get('EQD2_met', 'False')
                    is_met = str(is_met_str).lower() == 'true'
                    constraint_met_status = "Met" if is_met else "NOT Met"
                    oar_dvh_data.append({'Organ': '', 'Volume (cc)': '', 'Dose Metric': 'D2cc', 'EQD2 (Gy)': f"{metrics.get('eqd2_d2cc', metrics.get('bed_d2cc', 0)):.2f}", 'Constraint Met': constraint_met_status})

                if oar_dvh_data:
                    oar_df = pd.DataFrame(oar_dvh_data)
                    def style_oar_rows(row):
                        if row['Constraint Met'] == 'Met': return ['background-color: rgba(40, 167, 69, 0.2)'] * len(row)
                        elif row['Constraint Met'] == 'NOT Met': return ['background-color: rgba(220, 53, 69, 0.2)'] * len(row)
                        return [''] * len(row)
                    st.dataframe(oar_df.style.apply(style_oar_rows, axis=1), use_container_width=True, hide_index=True)
                else:
                    st.info("No OAR DVH data to display. Check structure mappings.")

                st.markdown("---")

                # --- Target Volume DVH Results Table (with updated keys) ---
                st.markdown("##### **Target Volume DVH Results**")
                target_dvh_data = []
                for organ, metrics in target_dvh_raw.items():
                    target_dvh_data.append({
                        'Structure': organ, 
                        'Volume (cc)': f"{metrics.get('volume_cc', 0):.2f}", 
                        'D90 EQD2 (Gy)': f"{metrics.get('eqd2_d90', 0):.2f}", 
                        'D98 EQD2 (Gy)': f"{metrics.get('eqd2_d98', 0):.2f}"
                    })
                
                if target_dvh_data:
                    st.dataframe(pd.DataFrame(target_dvh_data), use_container_width=True, hide_index=True)
                else:
                    st.info("No Target DVH data to display. Check structure mappings.")

                st.markdown("---")
                
                # --- Point Dose Results Table ---
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
        st.info("This is a placeholder. We will add the reporting components last.")
        pass

if __name__ == "__main__":
    main()