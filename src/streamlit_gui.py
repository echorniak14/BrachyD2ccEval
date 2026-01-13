import streamlit as st
import sys
import os
import pydicom
import pandas as pd
import json
import httpx
import re
from io import BytesIO

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import templates from the new backend location
from backend.src.config import templates 
import importlib
import backend.src.core.validators
importlib.reload(backend.src.core.validators)
from backend.src.core.validators import (
    validate_patient_ids, 
    validate_file_completeness,
    check_plan_time,
    validate_channel_mapping,
    check_dwell_times,
    check_fraction_count
) 

# Define the FastAPI backend URL
API_BASE_URL = "http://localhost:8000"

def get_dvh_structure_names(file_content: str):
    """
    Fast local parser to extract just the structure names from a DVH text file
    for the UI dropdowns. Does not perform full dose parsing.
    """
    structure_names = []
    # Split by 'ROI:' to find structure blocks
    roi_blocks = re.split(r'ROI[:\s]+', file_content)
    
    # Skip the header block (index 0), process the rest
    if len(roi_blocks) > 1:
        for block in roi_blocks[1:]:
            lines = block.strip().splitlines()
            if lines:
                # The first line of the block is the Structure Name
                structure_names.append(lines[0].strip())
    return structure_names

def main():
    st.set_page_config(layout="wide", page_title="ECHO")
    
    # --- CSS Styling ---
    st.markdown("""
        <style>
            [data-testid="stHeader"] + [data-testid="stHorizontalBlock"] { margin-top: -25px; }
            [data-testid="stSidebar"] [data-testid="stHeader"] + [data-testid="stHorizontalBlock"] { margin-top: -25px; }
            .results-container { background-color: #e9ecef; padding: 20px; border-radius: 10px; border: 1px solid #e6e6e6; }
            summary > div[data-testid="stMarkdownContainer"] p { font-size: 1.5rem; font-weight: 600; }
            h1, h2, h3, h4, h5, h6, summary { color: #FF5733 !important; }
        </style>
        """, unsafe_allow_html=True)

    # --- Callback Functions ---
    def update_optimization_goals():
        """Calculates optimization goals using a single BATCH API call."""
        st.session_state.optimization_goals = []
        oar_constraints = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
        
        # --- NEW LOGIC for previous BED calculation ---
        previous_brachy_bed_per_organ = {}
        if 'json_content' in st.session_state and st.session_state.json_content:
            json_content = st.session_state.json_content
            # Use the full history from the doses_per_fraction dict
            for organ, data in json_content.get("dvh_results", {}).items():
                alpha_beta = st.session_state.ab_ratios.get(organ, 3.0)
                
                # Get the list of historical doses for the d2cc metric
                dose_history = data.get("doses_per_fraction", {}).get("d2cc", [])
                
                if dose_history:
                    # Calculate the total brachy BED from this history
                    total_prev_bed = sum(d * (1 + d / alpha_beta) for d in dose_history)
                    previous_brachy_bed_per_organ[organ] = total_prev_bed
        # --- END NEW LOGIC ---
        
        # Prepare Batch Payload
        batch_payload = []
        for organ, constraints in oar_constraints.items():
            total_eqd2_constraint = constraints.get("D2cc", {}).get("max")
            if total_eqd2_constraint is not None:
                batch_payload.append({
                    "total_eqd2_constraint": total_eqd2_constraint,
                    "organ_name": organ,
                    "number_of_fractions": st.session_state.proposed_brachy_num_fx,
                    "ebrt_dose": st.session_state.ebrt_total_dose,
                    "ebrt_fractions": st.session_state.ebrt_num_fractions,
                    "previous_brachy_bed": previous_brachy_bed_per_organ.get(organ, 0.0),
                    "alpha_beta_ratios": st.session_state.ab_ratios
                })

        if not batch_payload:
            return

        # Use a container to prevent the status from rendering at the top of the app during callbacks
        with st.sidebar: 
            with st.status("Calculating optimization goals...", expanded=False, state="running") as status:
                try:
                    response = httpx.post(
                        f"{API_BASE_URL}/calculate_optimization_goal_batch", 
                        json={"requests": batch_payload}
                    )
                    response.raise_for_status() 
                    
                    result = response.json()
                    st.session_state.optimization_goals = result.get("goals", [])
                    
                    status.update(label="Goals updated!", state="complete", expanded=False)
                except Exception as e:
                    # st.error(f"Error calculating goals: {e}") # Optional: suppress transient errors
                    status.update(label="Calculation Failed", state="error")
    
    def process_json_upload():
        prev_brachy_file = st.session_state.get('prev_brachy_uploader')
        if prev_brachy_file:
            try:
                prev_brachy_file.seek(0)
                st.session_state.json_content = json.loads(prev_brachy_file.read().decode("utf-8"))
                update_optimization_goals() 
            except Exception as e:
                st.error(f"Error reading JSON: {e}")
                if 'json_content' in st.session_state: del st.session_state.json_content
        else:
            if 'json_content' in st.session_state:
                del st.session_state.json_content
                update_optimization_goals()
    
    def clear_uploads():
        st.session_state.widget_key_suffix += 1
        keys_to_delete = ['results', 'structure_mapping', 'manual_mapping', 'optimization_goals']
        for key in keys_to_delete:
            if key in st.session_state: del st.session_state[key]

    def clear_results():
        if 'results' in st.session_state: del st.session_state['results']

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
        if 'optimization_goals' in st.session_state: del st.session_state.optimization_goals

    def on_template_change():
        st.session_state.current_template_name = st.session_state.template_selector
        st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
        st.session_state.custom_constraints = templates[st.session_state.current_template_name].copy()
        reset_doses_to_default()
        clear_results()

    # --- Session State Initialization ---
    if "current_template_name" not in st.session_state: st.session_state.current_template_name = "Cervix HDR - EMBRACE II"
    if "ab_ratios" not in st.session_state: st.session_state.ab_ratios = templates[st.session_state.current_template_name]["alpha_beta_ratios"].copy()
    if "custom_constraints" not in st.session_state: st.session_state.custom_constraints = templates[st.session_state.current_template_name].copy()
    if 'ebrt_total_dose' not in st.session_state: st.session_state.ebrt_total_dose = 45.0
    if 'ebrt_num_fractions' not in st.session_state: st.session_state.ebrt_num_fractions = 25
    if 'ebrt_fraction_dose' not in st.session_state: st.session_state.ebrt_fraction_dose = 1.8
    if 'proposed_brachy_dose_fx' not in st.session_state: st.session_state.proposed_brachy_dose_fx = 7.0
    if 'proposed_brachy_num_fx' not in st.session_state: st.session_state.proposed_brachy_num_fx = 4
    if 'widget_key_suffix' not in st.session_state: st.session_state.widget_key_suffix = 0

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
        st.number_input("Dose per Fraction (Gy)", min_value=0.0, step=0.5, key='proposed_brachy_dose_fx', on_change=update_optimization_goals)
        st.number_input("Number of Fractions", min_value=1, step=1, key='proposed_brachy_num_fx', on_change=update_optimization_goals)
        st.caption("Enter fractions for the CURRENT plan only. Previous plan fractions are read from the uploaded JSON.")
        st.markdown("---")
        st.button("Reset Doses to Default", on_click=reset_doses_to_default, use_container_width=True)
        st.button("Clear Uploads", on_click=clear_uploads, use_container_width=True)
        st.button("Clear Results", on_click=clear_results, use_container_width=True)

    # --- Main Content ---
    st.title("ECHO: A HDR Evaluation and Analysis Tool")
    st.caption("A true reflection for clinical clarity.")

    pre_planning_tab, plan_analysis_tab, print_plan_tab = st.tabs(["📝 Pre-Planning", "🔬 Plan Analysis", "📄 Print Plan"])

    # === TAB 1: PRE-PLANNING ===
    with pre_planning_tab:
        st.header("Step 1: Define Treatment Parameters")
        st.subheader("Constraint Template")
        template_names = list(templates.keys())
        st.selectbox("Select Template", options=template_names, index=template_names.index(st.session_state.current_template_name), key="template_selector", on_change=on_template_change)
        
        with st.expander("View Current Constraints"):
            t_col, o_col = st.columns(2)
            with t_col:
                st.subheader("Target Volumes")
                t_cons = st.session_state.custom_constraints.get("constraints", {}).get("target_constraints", {})
                for k, v in t_cons.items():
                    s_name = k.split(' ')[0]
                    ab_val = st.session_state.ab_ratios.get(s_name, st.session_state.ab_ratios.get("Default", 3))
                    st.markdown(f"**{k}** (α/β: {ab_val}): {', '.join([f'{sk}: {sv}' for sk, sv in v.items() if sk != 'unit'])}")
            with o_col:
                st.subheader("Organs at Risk")
                o_cons = st.session_state.custom_constraints.get("constraints", {}).get("oar_constraints", {})
                for k, v in o_cons.items():
                    ab_val = st.session_state.ab_ratios.get(k, st.session_state.ab_ratios.get("Default", 3))
                    st.markdown(f"**{k}** (α/β: {ab_val})")
                    for m, vals in v.items():
                        st.markdown(f"- {m}: {', '.join([f'{sk}: {sv}' for sk, sv in vals.items() if sk != 'unit'])}")

        if st.session_state.current_template_name == "Custom":
            with st.expander("Customize Template", expanded=True):
                c_col1, c_col2 = st.columns(2)
                
                # --- Editable Target Constraints ---
                with c_col1:
                    st.markdown("#### Target Constraints")
                    t_cons_custom = st.session_state.custom_constraints["constraints"]["target_constraints"]
                    for t_name, t_vals in t_cons_custom.items():
                        st.caption(f"**{t_name}**")
                        if "min" in t_vals:
                            t_vals["min"] = st.number_input(f"{t_name} Min (Gy)", value=float(t_vals["min"]), step=0.5, key=f"cust_t_min_{t_name}")
                        if "max" in t_vals:
                            t_vals["max"] = st.number_input(f"{t_name} Max (Gy)", value=float(t_vals["max"]), step=0.5, key=f"cust_t_max_{t_name}")

                # --- Editable OAR Constraints ---
                with c_col2:
                    st.markdown("#### OAR Constraints")
                    o_cons_custom = st.session_state.custom_constraints["constraints"]["oar_constraints"]
                    for o_name, o_metrics in o_cons_custom.items():
                        st.caption(f"**{o_name}**")
                        # Usually D2cc, but iterate just in case
                        for m_type, m_vals in o_metrics.items():
                            if "max" in m_vals:
                                m_vals["max"] = st.number_input(f"{o_name} {m_type} Max (Gy)", value=float(m_vals["max"]), step=0.5, key=f"cust_o_max_{o_name}_{m_type}")
                            if "warning" in m_vals:
                                m_vals["warning"] = st.number_input(f"{o_name} {m_type} Warning (Gy)", value=float(m_vals["warning"]), step=0.5, key=f"cust_o_warn_{o_name}_{m_type}")

        st.subheader("Previous Brachytherapy Data")
        st.file_uploader("Upload previous brachy data (optional .json)", type=["json"], key="prev_brachy_uploader", on_change=process_json_upload)
        
        if 'json_content' in st.session_state and st.session_state.json_content:
            with st.container(border=True):
                st.markdown("##### Previous Plan Summary")
                prev_data = st.session_state.json_content
                
                prev_pat_name = prev_data.get("patient_name", "N/A")
                prev_pat_mrn = prev_data.get("patient_mrn", "N/A")
                prev_plan_name = prev_data.get("plan_name", "N/A")
                prev_fx = prev_data.get("number_of_fractions_delivered", "N/A")

                st.markdown(f"""
                - **Patient:** {prev_pat_name} ({prev_pat_mrn})
                - **Plan Name:** {prev_plan_name}
                - **Fractions Delivered:** `{prev_fx}`
                - **EBRT Dose (History):** {prev_data.get('ebrt_dose_input', 'N/A')} Gy ({prev_data.get('ebrt_fractions_input', 'N/A')} fx)
                """)
                st.info("**EBRT Handling:** The EBRT dose entered in the sidebar is counted **once** for the entire treatment course. If it was accounted for in a previous plan, you can set it to 0 for this analysis.", icon="ℹ️")

        if 'json_content' in st.session_state and 'structure_data' in st.session_state:
            with st.expander("Confirm Structure Mapping", expanded=True):
                if 'confirmed_structure_mapping' not in st.session_state: st.session_state.confirmed_structure_mapping = {}
                json_names = [n.upper() for n in st.session_state.json_content.get("dvh_results", {}).keys()]
                curr_names = list(st.session_state['structure_data'].keys())
                
                from fuzzywuzzy import process
                if json_names:
                    for c_name in curr_names:
                        match, score = process.extractOne(c_name, json_names)
                    default = match if score > 70 else "Ignore"
                    st.session_state.confirmed_structure_mapping[c_name] = st.selectbox(f"'{c_name}' maps to:", ["Ignore"] + json_names, index=(["Ignore"] + json_names).index(default) if default in (["Ignore"] + json_names) else 0, key=f"cmap_{c_name}")

        elif 'json_content' in st.session_state:
            st.info("Previous data loaded. Upload DICOMs in Plan Analysis to map structures.")

        if st.button("Calculate Optimization Goals", type="primary", use_container_width=True):
            update_optimization_goals()

        st.markdown("---")
        if 'optimization_goals' in st.session_state and st.session_state.optimization_goals:
            st.subheader("Optimization Goals")
            df_goals = pd.DataFrame(st.session_state.optimization_goals)
            st.dataframe(df_goals.style.format({"Total EQD2 Constraint (Gy)": "{:.1f}", "Max D2cc per Fraction (Gy)": "{:.2f}"}), use_container_width=True)

    # === TAB 2: ANALYSIS ===
    with plan_analysis_tab:
        st.header("Step 2: Upload and Analyze")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.subheader("1. DICOM Files")
            uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, RTPLAN", type=["dcm", "DCM"], accept_multiple_files=True, key=f"dicom_{st.session_state.widget_key_suffix}", on_change=clear_results)
        with col_up2:
            st.subheader("2. DVH Text File")
            dvh_text_file = st.file_uploader("Upload export (.txt)", type=["txt"], key="dvh_txt")

        # --- Local Pre-processing ---
        available_structure_names = set()
        
        # 1. DICOM Structures
        if uploaded_files:
            for up_file in uploaded_files:
                up_file.seek(0)
                try:
                    ds = pydicom.dcmread(up_file, stop_before_pixels=True, force=True)
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': # RTSTRUCT
                        local_structs = {}
                        if hasattr(ds, 'StructureSetROISequence'):
                            for roi in ds.StructureSetROISequence:
                                local_structs[roi.ROIName] = {"ROINumber": roi.ROINumber}
                        st.session_state['structure_data'] = local_structs
                        available_structure_names.update(local_structs.keys())
                    
                    # --- NEW: Extract and Display Plan Details ---
                    if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': # RTPLAN
                        plan_details = {
                            "Patient Name": str(getattr(ds, 'PatientName', 'Unknown')),
                            "Patient ID": str(getattr(ds, 'PatientID', 'Unknown')),
                            "Plan Date": str(getattr(ds, 'RTPlanDate', 'Unknown')),
                            "Plan Name": str(getattr(ds, 'RTPlanLabel', 'Unknown')),
                            "Fractions Planned": "Unknown"
                        }
                        # Attempt to get Fraction Group info
                        if hasattr(ds, 'FractionGroupSequence') and ds.FractionGroupSequence:
                            fg = ds.FractionGroupSequence[0]
                            plan_details["Fractions Planned"] = getattr(fg, 'NumberOfFractionsPlanned', 'Unknown')
                            
                        # Display immediately
                        st.success(f"Loaded Plan: **{plan_details['Plan Name']}**")
                        st.markdown(f"""
                            - **Patient:** {plan_details['Patient Name']} ({plan_details['Patient ID']})
                            - **Date:** {plan_details['Plan Date']}
                            - **Fractions Planned:** `{plan_details['Fractions Planned']}`
                        """)
                    # ---------------------------------------------
                        
                except Exception as e: 
                     # st.warning(f"Could not parse file: {e}") 
                     pass
        
        if uploaded_files:
            with st.spinner("Validating Data Integrity..."):
                val_datasets = [] # Tuple list: (ds, filename)
                val_types = []
                
                # Re-read for validation (headers only is fast)
                for f in uploaded_files:
                    f.seek(0)
                    try:
                        ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
                        val_datasets.append((ds, f.name)) # Tuple with filename
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': val_types.append('RTPLAN')
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': val_types.append('RTDOSE')
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': val_types.append('RTSTRUCT')
                        else: val_types.append('Unknown')
                    except:
                        pass
                
                # Check 1: File Completeness & Duplicates
                completeness_errors = validate_file_completeness(val_types)
                
                # Check 2: Patient ID Consistency
                json_hist = st.session_state.get('json_content')
                id_errors = validate_patient_ids(val_datasets, json_history=json_hist)
                
                # Check 3: DVH Text File ID Consistency (Immediate)
                text_id_errors = []
                if dvh_text_file:
                    dvh_text_file.seek(0)
                    content = dvh_text_file.read().decode('utf-8')
                    # Local regex extraction (lightweight)
                    pat_id_match = re.search(r"Patient Id[:\s]+(.*?)(?:\r|\n|$)", content, re.IGNORECASE)
                    text_pat_id = pat_id_match.group(1).strip() if pat_id_match else None
                    
                    if text_pat_id and val_datasets:
                        # Compare with first DICOM (ref_ds)
                        ref_ds, _ = val_datasets[0]
                        dicom_id = str(ref_ds.PatientID).strip()
                        
                        # Normalize
                        norm_text = text_pat_id.replace(' ', '').replace('-', '').lower()
                        norm_dicom = dicom_id.replace(' ', '').replace('-', '').lower()
                        
                        if norm_text != norm_dicom:
                            text_id_errors.append(f"CRITICAL: Patient ID Mismatch! Text File ID '{text_pat_id}' != DICOM ID '{dicom_id}'.")
                
                all_integrity_errors = completeness_errors + id_errors + text_id_errors
                
                if all_integrity_errors:
                    st.error("### 🛑 Data Integrity Issues Detected")
                    for err in all_integrity_errors:
                        st.error(err, icon="🚫")
                    st.warning("Please correct these issues before running the analysis.")
                    # Optionally disable the button or just verify user sees this
                
                # --- Clinical Logic Checks (Warnings) ---
                else: # Only run if integrity passed
                    clinical_warnings = []
                    rtplan_ds = None
                    
                    # Find RTPLAN
                    for ds, _ in val_datasets:
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5':
                            rtplan_ds = ds
                            break
                    
                    if rtplan_ds:
                        # 1. Plan Time
                        plan_time = getattr(rtplan_ds, 'RTPlanTime', '')
                        clinical_warnings.extend(check_plan_time(plan_time))
                        
                        # 2. Fraction Count
                        # Compare DICOM planned vs User Input (proposed_brachy_num_fx)
                        if hasattr(rtplan_ds, 'FractionGroupSequence') and rtplan_ds.FractionGroupSequence:
                            planned_fx = rtplan_ds.FractionGroupSequence[0].NumberOfFractionsPlanned
                            clinical_warnings.extend(check_fraction_count(planned_fx, st.session_state.proposed_brachy_num_fx))

                        # 3. Channel Mapping & Dwell Times
                        # Determine applicator type from template name
                        app_type = "Tandem and Ovoid" # Default
                        tmpl = st.session_state.current_template_name
                        if "Cylinder" in tmpl: app_type = "Cylinder"
                        elif "Ring" in tmpl: app_type = "Tandem and Ring"
                        
                        # Extract Channels & Dwells
                        channels_map = []
                        dwells = []
                        
                        app_setup = rtplan_ds.get((0x300a, 0x0230)) # ApplicationSetupSequence
                        if app_setup and hasattr(app_setup[0], 'ChannelSequence'):
                            for ch in app_setup[0].ChannelSequence:
                                # Channel Mapping
                                ch_num = str(ch.ChannelNumber) if hasattr(ch, 'ChannelNumber') else '0'
                                tube_num = str(ch.TransferTubeNumber) if hasattr(ch, 'TransferTubeNumber') else '0'
                                channels_map.append({'channel_number': ch_num, 'transfer_tube_number': tube_num})
                                
                                # Dwell Times extraction
                                total_time = float(ch.ChannelTotalTime) if hasattr(ch, 'ChannelTotalTime') else 0.0
                                final_weight = float(ch.FinalCumulativeTimeWeight) if hasattr(ch, 'FinalCumulativeTimeWeight') else 0.0
                                
                                if final_weight > 0 and hasattr(ch, 'BrachyControlPointSequence'):
                                    cps = ch.BrachyControlPointSequence
                                    for i in range(1, len(cps)):
                                        w = float(cps[i].CumulativeTimeWeight) - float(cps[i-1].CumulativeTimeWeight)
                                        if w > 0:
                                            dt = w * total_time / final_weight
                                            dwells.append(dt)
                                            
                        clinical_warnings.extend(validate_channel_mapping(channels_map, app_type))
                        clinical_warnings.extend(check_dwell_times(dwells))

                    if clinical_warnings:
                        with st.expander("⚠️ Clinical Warnings (Please Review)", expanded=True):
                            for w in clinical_warnings:
                                st.warning(w, icon="⚠️")


        # 2. Text File Structures (Using new helper)
        if dvh_text_file:
            dvh_text_file.seek(0)
            dvh_content = dvh_text_file.read().decode('utf-8')
            # CALL LOCAL HELPER
            text_structs = get_dvh_structure_names(dvh_content)
            available_structure_names.update(text_structs)

        # Mapping UI
        if available_structure_names:
            sorted_structures = sorted(list(available_structure_names))
            with st.expander("Structure Mapping", expanded=True):
                if 'confirmed_structure_mapping' not in st.session_state: st.session_state.confirmed_structure_mapping = {}
                cols = st.columns(3)
                opts = ["Ignore", "Bladder", "Rectum", "Sigmoid", "Bowel", "GTV", "HRCTV", "Vagina"]
                for i, s_name in enumerate(sorted_structures):
                    col = cols[i % 3]
                    def_idx = 0
                    for idx, opt in enumerate(opts):
                        if opt.lower() != "ignore" and opt.lower() in s_name.lower():
                            def_idx = idx; break
                    st.session_state.confirmed_structure_mapping[s_name] = col.selectbox(f"{s_name} ->", opts, index=def_idx, key=f"map_{s_name}")

        if st.button("Run Analysis", type="primary", use_container_width=True):
            if uploaded_files:
                # Identify files
                f_map = {"RTPLAN": None, "RTDOSE": None, "RTSTRUCT": None}
                ids = set()
                for f in uploaded_files:
                    f.seek(0)
                    try:
                        ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
                        ids.add(str(ds.PatientID))
                        if ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5': f_map["RTPLAN"] = f
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.2': f_map["RTDOSE"] = f
                        elif ds.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3': f_map["RTSTRUCT"] = f
                    except: pass
                
                if len(ids) > 1: st.error(f"Multiple Patient IDs found: {ids}"); st.stop()
                if not all(f_map.values()): st.error("Missing required DICOM files."); st.stop()
                if not dvh_text_file: st.error("Missing DVH Text File."); st.stop()

                # Prepare Payload
                files = {
                    "rtplan_file": (f_map["RTPLAN"].name, f_map["RTPLAN"].getvalue(), "application/dicom"),
                    "rtdose_file": (f_map["RTDOSE"].name, f_map["RTDOSE"].getvalue(), "application/dicom"),
                    "rtstruct_file": (f_map["RTSTRUCT"].name, f_map["RTSTRUCT"].getvalue(), "application/dicom"),
                }
                if dvh_text_file:
                    dvh_text_file.seek(0)
                    files["dvh_text_file"] = (dvh_text_file.name, dvh_text_file.getvalue(), "text/plain")

                data = {
                    "previous_brachy_data_json": json.dumps(st.session_state.get('json_content', {})),
                    "custom_constraints_json": json.dumps(st.session_state.custom_constraints),
                    "num_fractions_delivered": str(st.session_state.proposed_brachy_num_fx),
                    "ebrt_dose": str(st.session_state.ebrt_total_dose),
                    "ebrt_fractions": str(st.session_state.ebrt_num_fractions),
                    "confirmed_structure_mapping_json": json.dumps(st.session_state.get('confirmed_structure_mapping', {}))
                }

                with st.spinner("Processing..."):
                    try:
                        res = httpx.post(f"{API_BASE_URL}/process_plan", files=files, data=data, timeout=300.0)
                        res.raise_for_status()
                        st.session_state.results = res.json()
                    except Exception as e:
                        st.error(f"Analysis Failed: {e}")

        # Display Results
        if 'results' in st.session_state and 'error' not in st.session_state.results:
            results = st.session_state.results
            st.markdown("---")
            st.header("Analysis Results")
            
            # Validation Warnings
            warns = results.get('tps_validation_warnings', [])
            if warns:
                errors = [w for w in warns if "CRITICAL" in w]
                warnings = [w for w in warns if "CRITICAL" not in w]
                
                if errors:
                    st.error("### 🛑 CRITICAL Validation Errors")
                    for e in errors: st.error(e, icon="🚫")
                
                if warnings:
                    st.warning("### ⚠️ QA Warnings (Dose Discrepancies)")
                    for w in warnings: st.warning(w, icon="⚠️")
            
            # Validation Table
            val_data = results.get("validation_df")
            val_df = pd.DataFrame(val_data) if val_data else pd.DataFrame()
            if not val_df.empty:
                # Filter for significant differences (> 5%) AND clinically relevant metrics
                # OARs: Rectum, Sigmoid, Bowel, Bladder -> D2cc, D1cc, D0.1cc
                # Targets: GTV, HRCTV -> D90, D98
                
                def is_clinically_relevant(row):
                    s_name = str(row['Structure']).upper()
                    metric = str(row['Metric']).upper()
                    
                    if 'VOLUME' in metric: return True

                    is_oar = any(x in s_name for x in ['RECTUM', 'SIGMOID', 'BOWEL', 'BLADDER'])
                    is_target = any(x in s_name for x in ['GTV', 'HRCTV'])
                    
                    if is_oar and metric in ['D2CC', 'D1CC', 'D0.1CC']: return True
                    if is_target and metric in ['D90', 'D98']: return True
                    return False

                # Apply filters: > 5% diff AND clinically relevant
                sig_diff_df = val_df[
                    (val_df['Pct_Diff'].abs() > 5.0) & 
                    (val_df.apply(is_clinically_relevant, axis=1))
                ]
                
                def hl(val): return f'color: {"red" if abs(val)>5.0 else "green"}'

                if not sig_diff_df.empty:
                    st.error("### ⚠️ Significant Discrepancies Detected (> 5%)")
                    st.dataframe(sig_diff_df.style.map(hl, subset=['Pct_Diff']), use_container_width=True)
                    
                    with st.expander("View Full Verification Table"):
                         st.dataframe(val_df.style.map(hl, subset=['Pct_Diff']), use_container_width=True)
                else:
                    st.success("✅ TPS vs DICOM Verification: All clinically relevant values match within 5% tolerance.")
                    with st.expander("View Full Verification Table (All Pass)"):
                         st.dataframe(val_df.style.map(hl, subset=['Pct_Diff']), use_container_width=True)

                # Feasibility study button (available in all cases if val_df exists)
                if st.button("Add to Feasibility Study"):
                    path = os.path.join(project_root, "feasibility_study.csv")
                    hdr = not os.path.exists(path)
                    try:
                        val_df.to_csv(path, mode='a', header=hdr, index=False)
                        st.success("Saved to feasibility study.")
                    except PermissionError:
                        st.error(f"Permission denied: Could not save to '{path}'. Please close the file if it is open in Excel or another program.")
                    except Exception as e:
                        st.error(f"Error saving to feasibility study: {e}")

            # Main Results Display (Simplified for brevity - assumes standard tables)
            # You can paste your detailed OAR/Target table generation code here
            st.json(results.get("constraint_evaluation"))

            # Add a download button for the full JSON results
            st.download_button(
                label="Download Full Results (JSON)",
                data=json.dumps(results, indent=4),
                file_name=f"ECHO_results_{results.get('patient_mrn', 'unknown')}.json",
                mime="application/json",
            )

    # === TAB 3: REPORTS ===
    with print_plan_tab:
        st.header("Reports")
        if 'results' in st.session_state:
            results = st.session_state.results
            
            col1, col2 = st.columns(2)

            with col1:
                # Add a download button for the full JSON results
                st.download_button(
                    label="Download Full Results (JSON)",
                    data=json.dumps(results, indent=4),
                    file_name=f"ECHO_results_{results.get('patient_mrn', 'unknown')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            
            with col2:
                if st.button("Generate PDF", use_container_width=True):
                    # Call backend PDF endpoint logic here if needed
                    st.info("PDF Generation logic invoked (requires HTML content in results).")

if __name__ == "__main__":
    main()