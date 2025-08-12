import streamlit as st
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import main as run_analysis
import tempfile
import os

def main():
    st.title("Brachytherapy Plan Evaluator")

    st.header("Upload DICOM Files")
    rtdose_file = st.file_uploader("Upload RTDOSE file", type=["dcm"])
    rtstruct_file = st.file_uploader("Upload RTSTRUCT file", type=["dcm"])
    rtplan_file = st.file_uploader("Upload RTPLAN file", type=["dcm"])

    st.header("Enter Parameters")
    ebrt_dose = st.number_input("EBRT Dose (Gy)", value=0.0)
    previous_brachy_html = st.file_uploader("Upload previous brachytherapy report (optional)", type=["html"])

    if st.button("Run Analysis"):
        if rtdose_file and rtstruct_file and rtplan_file:
            with tempfile.TemporaryDirectory() as tmpdir:
                rtdose_path = os.path.join(tmpdir, rtdose_file.name)
                rtstruct_path = os.path.join(tmpdir, rtstruct_file.name)
                rtplan_path = os.path.join(tmpdir, rtplan_file.name)

                with open(rtdose_path, "wb") as f:
                    f.write(rtdose_file.getbuffer())
                with open(rtstruct_path, "wb") as f:
                    f.write(rtstruct_file.getbuffer())
                with open(rtplan_path, "wb") as f:
                    f.write(rtplan_file.getbuffer())

                args = argparse.Namespace(
                    data_dir=tmpdir,
                    ebrt_dose=ebrt_dose,
                    previous_brachy_html=previous_brachy_html,
                    output_html=os.path.join(tmpdir, "report.html")
                )

                results = run_analysis(args)

                st.header("Results")
                st.json(results)
        else:
            st.error("Please upload all required DICOM files.")

if __name__ == "__main__":
    main()
