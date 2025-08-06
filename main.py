import sys
from html_parser import parse_html_report
from dicom_parser import find_dicom_file, load_dicom_file, get_structure_data, get_plan_data
from calculations import get_dvh, evaluate_constraints, calculate_dose_to_meet_constraint
import argparse
from pathlib import Path
import json

def generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, dvh_results, constraint_evaluation, output_path):
    # Determine the base path for data files
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in a normal Python environment
        base_path = Path(__file__).parent

    template_path = Path(base_path) / "report_template.html"

    with open(template_path, "r") as f:
        template = f.read()

    dvh_rows = ""
    for organ, data in dvh_results.items():
        eqd2_met_class = ""
        if organ in constraint_evaluation:
            constraints = constraint_evaluation[organ]
            if "EQD2_met" in constraints:
                eqd2_met_class = "met" if constraints["EQD2_met"] == "True" else "not-met"

        dvh_rows += f"""<tr>
            <td>{organ}</td>
            <td>{data["volume_cc"]}</td>
            <td>{data["d0_1cc_gy_per_fraction"]}</td>
            <td>{data["d1cc_gy_per_fraction"]}</td>
            <td>{data["d2cc_gy_per_fraction"]}</td>
            <td>{data["total_d2cc_gy"]}</td>
            <td>{data["bed_this_plan"]}</td>
            <td>{data["bed_previous_brachy"]}</td>
            <td>{data["bed_ebrt"]}</td>
            <td>{data["eqd2"]}</td>
            <td class="{eqd2_met_class}">{'Met' if eqd2_met_class == 'met' else 'NOT Met'}</td>
            <td>{data["dose_to_meet_constraint"]}</td>
        </tr>"""

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ plan_name }}", plan_name)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ dvh_results_rows }}", dvh_rows)

    with open(output_path, "w") as f:
        f.write(html_content)
    # print(f"HTML report saved to {output_path}") # Removed print statement

def main(args):
    data_dir = Path(args.data_dir)

    # Find the subdirectories
    subdirectories = [d for d in data_dir.iterdir() if d.is_dir()]
    dose_dir = next((d for d in subdirectories if "RTDOSE" in d.name), None)
    struct_dir = next((d for d in subdirectories if "RTst" in d.name), None)
    plan_dir = next((d for d in subdirectories if "RTPLAN" in d.name), None)

    if not all([dose_dir, struct_dir, plan_dir]):
        print(json.dumps({"error": "Could not find all required DICOM subdirectories (RTDOSE, RTst, RTPLAN)."}))
        return

    # Find the DICOM files
    dose_file = find_dicom_file(dose_dir)
    struct_file = find_dicom_file(struct_dir)
    plan_file = find_dicom_file(plan_dir)

    if not all([dose_file, struct_file, plan_file]):
        print(json.dumps({"error": "Could not find all DICOM files." }))
        return

    # Load the DICOM files
    rt_dose_dataset = load_dicom_file(dose_file)
    rt_struct_dataset = load_dicom_file(struct_file)
    rt_plan_dataset = load_dicom_file(plan_file)

    if not all([rt_dose_dataset, rt_struct_dataset, rt_plan_dataset]):
        print(json.dumps({"error": "Could not load all DICOM files." }))
        return

    # Verify patient consistency
    patient_ids = {rt_dose_dataset.PatientID, rt_struct_dataset.PatientID, rt_plan_dataset.PatientID}
    if len(patient_ids) > 1:
        print(json.dumps({"error": "DICOM files belong to different patients." }))
        return

    patient_name = str(rt_dose_dataset.PatientName)
    patient_mrn = str(rt_dose_dataset.PatientID)

    # Get plan data
    plan_data = get_plan_data(plan_file)
    number_of_fractions = plan_data.get('number_of_fractions', 1)
    plan_name = plan_data.get('plan_name', 'N/A')
    brachy_dose_per_fraction = plan_data.get('brachy_dose_per_fraction', 'N/A')
    

    # Get structure data
    structure_data = get_structure_data(rt_struct_dataset)

    # Parse previous brachytherapy HTML report if provided
    previous_brachy_eqd2_per_organ = {}
    if args.previous_brachy_html:
        previous_brachy_eqd2_per_organ = parse_html_report(args.previous_brachy_html)

    # Calculate DVH
    dvh_results = get_dvh(
        struct_file,
        dose_file,
        structure_data,
        number_of_fractions,
        ebrt_dose=args.ebrt_dose,
        previous_brachy_eqd2_per_organ=previous_brachy_eqd2_per_organ
    )

    # Evaluate constraints
    constraint_evaluation = evaluate_constraints(dvh_results)

    # Calculate dose to meet constraint for unmet EQD2 constraints
    for organ, data in dvh_results.items():
        if organ in constraint_evaluation:
            constraints = constraint_evaluation[organ]
            if "EQD2_met" in constraints and constraints["EQD2_met"] == "False":
                eqd2_constraint = constraints["EQD2_max"]
                dose_needed = calculate_dose_to_meet_constraint(
                    eqd2_constraint,
                    organ,
                    number_of_fractions,
                    args.ebrt_dose,
                    previous_brachy_eqd2=previous_brachy_eqd2_per_organ.get(organ, 0)
                )
                dvh_results[organ]["dose_to_meet_constraint"] = dose_needed
            else:
                dvh_results[organ]["dose_to_meet_constraint"] = "N/A"

    output_data = {
        "patient_name": patient_name,
        "patient_mrn": patient_mrn,
        "plan_name": plan_name,
        "brachy_dose_per_fraction": brachy_dose_per_fraction,
        "number_of_fractions": number_of_fractions,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation
    }

    if args.output_html:
        generate_html_report(patient_name, patient_mrn, plan_name, brachy_dose_per_fraction, number_of_fractions, args.ebrt_dose, dvh_results, constraint_evaluation, args.output_html)

    return output_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brachytherapy Plan Evaluator")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the directory containing the patient's DICOM files.")
    parser.add_argument("--ebrt_dose", type=float, default=0.0, help="The prescription dose of the external beam radiation therapy in Gray (Gy).")
    parser.add_argument("--previous_brachy_html", type=str, help="Path to a previous brachytherapy HTML report to incorporate its EQD2 values.")
    parser.add_argument("--output_html", type=str, help="If provided, the results will be saved to this HTML file.")

    args = parser.parse_args()
    main(args)
