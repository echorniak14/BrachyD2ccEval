import streamlit as st
import argparse
import sys
import os
import pydicom

# Add the project root to the Python path
# This is necessary for the 'src' module to be found
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.dicom_parser import get_plan_data
from src.main import main as run_analysis, convert_html_to_pdf
from src.config import alpha_beta_ratios
import tempfile

def main():
    st.title("Brachytherapy Plan Evaluator")

    st.header("Upload DICOM Files")
    uploaded_files = st.file_uploader("Upload RTDOSE, RTSTRUCT, and RTPLAN files", type=["dcm", "DCM"], accept_multiple_files=True)

    st.sidebar.header("Parameters")
    ebrt_dose = st.sidebar.number_input("EBRT Dose (Gy)", value=0.0)
    previous_brachy_html = st.sidebar.file_uploader("Upload previous brachytherapy report (optional)", type=["html"])
    wkhtmltopdf_path = st.sidebar.text_input("Path to wkhtmltopdf.exe (optional)")

    st.sidebar.header("Alpha/Beta Ratios")

    # Initialize session state from defaults if not already present
    for organ, val in alpha_beta_ratios.items():
        if f"ab_{organ}" not in st.session_state:
            st.session_state[f"ab_{organ}"] = val

    # Reset button
    if st.sidebar.button("Reset to Default"):
        for organ, val in alpha_beta_ratios.items():
            st.session_state[f"ab_{organ}"] = val

    # Display and update alpha/beta ratios
    for organ, val in alpha_beta_ratios.items():
        st.sidebar.number_input(f"{organ}", key=f"ab_{organ}")

    # Collect the ab_ratios from session state before running analysis
    ab_ratios = {}
    for organ, val in alpha_beta_ratios.items():
        ab_ratios[organ] = st.session_state[f"ab_{organ}"]

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
                    args = argparse.Namespace(
                        data_dir=tmpdir_analysis, # Use the new tmpdir for analysis
                        ebrt_dose=ebrt_dose,
                        previous_brachy_html=previous_brachy_html,
                        output_html=os.path.join(tmpdir_analysis, "report.html"),
                        alpha_beta_ratios=ab_ratios,
                        selected_point_names=st.session_state.selected_point_names # Pass selected points
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
                            alpha_beta = ab_ratios.get(organ, alpha_beta_ratios["Default"])
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
                                oar_dvh_data.append({
                                    "Organ": organ,
                                    "Volume (cc)": data["volume_cc"],
                                    "D0.1cc (Gy)": data["d0_1cc_gy_per_fraction"],
                                    "D1cc (Gy)": data["d1cc_gy_per_fraction"],
                                    "D2cc (Gy)": data["d2cc_gy_per_fraction"],
                                    "BED_D0.1cc (Gy)": data["bed_d0_1cc"],
                                    "EQD2_D0.1cc (Gy)": data["eqd2_d0_1cc"],
                                    "BED_D1cc (Gy)": data["bed_d1cc"],
                                    "EQD2_D1cc (Gy)": data["eqd2_d1cc"],
                                    "BED_D2cc (Gy)": data["bed_d2cc"],
                                    "EQD2_D2cc (Gy)": data["eqd2_d2cc"],
                                })
                        
                        if target_dvh_data:
                            st.table(target_dvh_data)
                        else:
                            st.info("No target volume DVH data available.")

                        st.subheader("OAR DVH Results")
                        if oar_dvh_data:
                            st.table(oar_dvh_data)
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
