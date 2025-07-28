from dicom_parser import load_dicom_file, get_structure_names
import argparse

def main():
    parser = argparse.ArgumentParser(description="Brachytherapy Plan Evaluator")
    parser.add_argument("--dose_dicom_file", type=str, required=True, help="Path to the exported DICOM RT Dose file.")
    parser.add_argument("--struct_dicom_file", type=str, required=True, help="Path to the exported DICOM RT Structure Set file.")
    parser.add_argument("--ebrt_received", type=bool, default=False, help="Specify True if the patient has received external beam radiation therapy.")
    parser.add_argument("--ebrt_dose", type=float, default=45, help="The prescription dose of the external beam radiation therapy in Gray (Gy).")
    parser.add_argument("--output_csv", type=str, help="If provided, the results will be saved to this CSV file.")

    args = parser.parse_args()

    # Load the RT Dose DICOM file
    rt_dose_dataset = load_dicom_file(args.dose_dicom_file)
    if rt_dose_dataset:
        print(f"Patient Name from RT Dose: {rt_dose_dataset.PatientName}")
        print(f"Modality from RT Dose: {rt_dose_dataset.Modality}")

    # Load the RT Structure Set DICOM file
    rt_struct_dataset = load_dicom_file(args.struct_dicom_file)
    if rt_struct_dataset:
        print(f"Patient Name from RT Struct: {rt_struct_dataset.PatientName}")
        print(f"Modality from RT Struct: {rt_struct_dataset.Modality}")
        
        structure_names = get_structure_names(rt_struct_dataset)
        if structure_names:
            print("Found the following structures:")
            for name in structure_names:
                print(f"- {name}")
        else:
            print("No structures found in the RT Structure Set file.")

    # Further processing will go here

if __name__ == "__main__":
    main()