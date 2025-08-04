from dicom_parser import find_dicom_file, load_dicom_file, get_structure_data
from calculations import get_dvh, evaluate_constraints
import argparse
from pathlib import Path
import json

def generate_html_report(patient_name, patient_mrn, treatment_site, brachy_dose_per_fraction, number_of_fractions, ebrt_dose, dvh_results, constraint_evaluation, output_path):
    with open("report_template.html", "r") as f:
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
            <td>{data["d2cc_gy_per_fraction"]}</td>
            <td>{data["total_d2cc_gy"]}</td>
            <td>{data["bed"]}</td>
            <td>{data["eqd2"]}</td>
            <td class=\"{eqd2_met_class}\">{'Met' if eqd2_met_class == 'met' else 'NOT Met'}</td>
        </tr>"""

    html_content = template.replace("{{ patient_name }}", patient_name)
    html_content = html_content.replace("{{ patient_mrn }}", patient_mrn)
    html_content = html_content.replace("{{ treatment_site }}", treatment_site)
    html_content = html_content.replace("{{ brachy_dose_per_fraction }}", str(brachy_dose_per_fraction))
    html_content = html_content.replace("{{ number_of_fractions }}", str(number_of_fractions))
    html_content = html_content.replace("{{ ebrt_dose }}", str(ebrt_dose))
    html_content = html_content.replace("{{ dvh_results_rows }}", dvh_rows)

    with open(output_path, "w") as f:
        f.write(html_content)
    # print(f"HTML report saved to {output_path}") # Removed print statement

def main():
    parser = argparse.ArgumentParser(description="Brachytherapy Plan Evaluator")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the directory containing the patient's DICOM files.")
    parser.add_argument("--ebrt_dose", type=float, default=0.0, help="The prescription dose of the external beam radiation therapy in Gray (Gy).")
    parser.add_argument("--previous_brachy_eqd2", type=float, default=0.0, help="The EQD2 dose from previous brachytherapy treatments in Gray (Gy).")
    parser.add_argument("--output_html", type=str, help="If provided, the results will be saved to this HTML file.")

    args = parser.parse_args()

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

    # Extract brachytherapy prescription details
    brachy_dose_per_fraction = "N/A"
    if hasattr(rt_plan_dataset, 'DoseReferenceSequence'):
        for dose_ref in rt_plan_dataset.DoseReferenceSequence:
            if hasattr(dose_ref, 'DeliveryPrescriptionDose'):
                brachy_dose_per_fraction = float(dose_ref.DeliveryPrescriptionDose)
                break

    # Placeholder for treatment site (can be made an input later)
    treatment_site = "Not Specified"

    # Get structure data
    structure_data = get_structure_data(rt_struct_dataset)
    if not structure_data:
        print(json.dumps({"error": "No structure data found." }))
        return

    # Get number of fractions
    number_of_fractions = rt_plan_dataset.FractionGroupSequence[0].NumberOfFractionsPlanned

    # Calculate DVH
    dvh_results = get_dvh(
        struct_file,
        dose_file,
        structure_data,
        number_of_fractions,
        ebrt_dose=args.ebrt_dose
    )

    # Evaluate constraints
    constraint_evaluation = evaluate_constraints(dvh_results)

    output_data = {
        "patient_name": patient_name,
        "patient_mrn": patient_mrn,
        "treatment_site": treatment_site,
        "brachy_dose_per_fraction": brachy_dose_per_fraction,
        "number_of_fractions": number_of_fractions,
        "ebrt_dose": args.ebrt_dose,
        "dvh_results": dvh_results,
        "constraint_evaluation": constraint_evaluation
    }

    print(json.dumps(output_data))

    # Write results to HTML if output_html argument is provided
    if args.output_html:
        generate_html_report(patient_name, patient_mrn, treatment_site, brachy_dose_per_fraction, number_of_fractions, args.ebrt_dose, dvh_results, constraint_evaluation, args.output_html)

if __name__ == "__main__":
    main()
