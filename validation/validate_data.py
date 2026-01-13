
import os
import argparse
import pandas as pd
import pydicom
import json
import warnings
from pathlib import Path
import numpy as np
# Import project modules
import sys
# Add parent directory to path to access backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.src.core import calculations
from backend.src.services.parser_service import ParserService
from backend.src.config import templates

# Suppress Warnings
warnings.filterwarnings("ignore")

def get_excel_ground_truth(excel_path):
    """
    Parses 'ABS Spreadsheet 2.xls' using user-provided fixed coordinates.
    Bladder: J65, Rectum: J77, Sigmoid: J85, Bowel: J106
    EBRT Total Dose: C9 (row 8, col 2)
    """
    cells = {
        'Bladder': (64, 9),
        'Rectum': (76, 9),
        'Sigmoid': (84, 9),
        'Bowel': (105, 9)
    }
    
    # EBRT Cell C9 -> Row 8, Col 2
    ebrt_cell = (8, 2)
    
    try:
        # Read without header
        df = pd.read_excel(excel_path, header=None)
        
        truth_data = {}
        for organ, (r, c) in cells.items():
            if r < len(df) and c < df.shape[1]:
                val = df.iloc[r, c]
                try:
                    truth_data[organ] = float(val)
                except:
                    print(f"  Warning: Could not parse float for {organ} at {r},{c} (Value: {val})")
        
        # Read EBRT
        ebrt_dose = 0.0
        if ebrt_cell[0] < len(df) and ebrt_cell[1] < df.shape[1]:
            val = df.iloc[ebrt_cell[0], ebrt_cell[1]]
            try:
                ebrt_dose = float(val)
            except:
                pass
        
        truth_data['_EBRT_DOSE'] = ebrt_dose
        print(f"  DEBUG: Read EBRT Dose from Excel: {ebrt_dose}")
        
        return truth_data

    except Exception as e:
        print(f"Error reading Excel {excel_path}: {e}")
        return {}

def process_patient(patient_dir, parser, ab_ratios):
    """Processes a single patient directory using dvh.txt for input."""
    print(f"\nProcessing: {patient_dir.name}")
    
    fractions = []
    excel_file = None
    
    for item in patient_dir.iterdir():
        if item.is_dir() and item.name.lower().startswith("fx"):
            fractions.append(item)
        elif item.suffix.lower() in ['.xls', '.xlsx'] and "abs" in item.name.lower():
            excel_file = item
    
    fractions.sort(key=lambda x: x.name) 
    
    if not fractions:
        print("  No fraction folders found. Skipping.")
        return None
        
    if not excel_file:
         print("  Warning: No Excel file found. Skipping.")
         return None

    print(f"  Found Excel: {excel_file.name}")
    
    # Get Ground Truth first to get EBRT dose
    truth = get_excel_ground_truth(excel_file)
    if not truth:
        print("  Warning: Excel parsing returned empty truth data.")
    else:
        print(f"  Excel Truth Loaded. EBRT: {truth.get('_EBRT_DOSE', 'N/A')}")

    ebrt_total_dose = truth.get('_EBRT_DOSE', 0.0)
    
    # Estimate EBRT fractions (Standard 1.8 Gy/fx)
    ebrt_fractions = 0
    if ebrt_total_dose > 0:
        ebrt_fractions = int(round(ebrt_total_dose / 1.8))
        if ebrt_fractions == 0: ebrt_fractions = 1 

    prev_json_data = {} 
    final_output = {"dvh_results": {}}
    
    patient_ids = set()
    
    for i, fx_dir in enumerate(fractions):
        print(f"  Calculating {fx_dir.name} using dvh.txt...")
        
        dvh_file = list(fx_dir.glob("dvh.txt"))
        if not dvh_file:
             print(f"  Missing dvh.txt in {fx_dir.name}. Skipping.")
             return None
        
        # Parse RTPLAN for Number of Fractions
        rtplan_files = list(fx_dir.glob("*.dcm"))
        num_fractions = 1
        
        rtplan_path = None
        for f in rtplan_files:
            try:
                if pydicom.dcmread(f, force=True, stop_before_pixels=True).SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.5':
                    rtplan_path = f
                    break
            except Exception as e:
                print(f"    - Debug: Failed to read {f.name}: {e}")

        if rtplan_path:
            try:
                ds_plan = pydicom.dcmread(rtplan_path)
                patient_ids.add(str(ds_plan.PatientID))
                if hasattr(ds_plan, 'FractionGroupSequence') and ds_plan.FractionGroupSequence:
                    num_fractions = int(ds_plan.FractionGroupSequence[0].NumberOfFractionsPlanned)
                    print(f"    - Found Plan: {ds_plan.RTPlanLabel}, Fractions Planned: {num_fractions}")
            except Exception as e:
                print(f"    - Warning: Could not parse RTPLAN for fractions: {e}")
        else:
             print("    - Warning: No RTPLAN found. Defaulting to 1 fraction.")

             print("    - Warning: No RTPLAN found. Defaulting to 1 fraction.")

        content = ""
        try:
            with open(dvh_file[0], 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(dvh_file[0], 'r', encoding='latin-1') as f:
                    content = f.read()
                    print(f"    - Info: Read dvh.txt with latin-1 encoding.")
            except Exception as e:
                 print(f"    - Error reading dvh.txt: {e}")
                 return None

            
        # Parse DVH Text
        try:
            parsed_dvh, meta = parser.parse_dvh_text_file(content)
            if not parsed_dvh:
                 print("    - Warning: DVH parsing returned no structures.")
        except Exception as e:
            print(f"    - Error parsing dvh.txt: {e}")
            return None
        
        mapping = {}
        for k in parsed_dvh.keys():
            k_lower = k.lower()
            if 'bladder' in k_lower: mapping[k] = 'Bladder'
            elif 'rectum' in k_lower: mapping[k] = 'Rectum'
            elif 'sigmoid' in k_lower: mapping[k] = 'Sigmoid'
            elif 'bowel' in k_lower: mapping[k] = 'Bowel'
            else: mapping[k] = 'Ignore'

        dvh_res = parser.get_dvh_metrics_from_text(
            parsed_dvh, mapping, 
            num_fractions, 
            previous_brachy_bed_per_organ=prev_json_data.get("dvh_results", {})
        )
        
        # Accumulate Dose History 
        current_step_json = {"dvh_results": {}}
        target_organs = ['Bladder', 'Rectum', 'Sigmoid', 'Bowel']
        
        for std_organ in target_organs:
            if std_organ not in dvh_res: continue
            
            metrics = dvh_res[std_organ]
            prev_organ_data = prev_json_data.get("dvh_results", {}).get(std_organ, {})
            prev_doses = prev_organ_data.get("doses_per_fraction", {})
            new_doses = {}
            
            curr_val = metrics.get('d2cc_gy_per_fraction', 0.0)
            
            # Append this fraction's dose N times (where N is fractions planned for this insertion)
            hist = prev_doses.get('d2cc', [])
            new_chunk = [curr_val] * num_fractions
            new_hist = hist + new_chunk
            new_doses['d2cc'] = new_hist
            
            current_step_json["dvh_results"][std_organ] = {
                "doses_per_fraction": new_doses
            }
            
        prev_json_data = current_step_json
        final_output = current_step_json

    # Final EQD2 Calculation
    compare_results = {}
    for organ, data in final_output["dvh_results"].items():
        d2cc_hist = data["doses_per_fraction"].get("d2cc", [])
        alpha_beta = ab_ratios.get(organ, 3.0)
        
        # Brachy BED
        total_bed = sum(d * (1 + d / alpha_beta) for d in d2cc_hist)
        
        # Add EBRT Component
        if ebrt_total_dose > 0:
            ebrt_d_per_fx = ebrt_total_dose / ebrt_fractions
            ebrt_bed = ebrt_total_dose * (1 + ebrt_d_per_fx / alpha_beta)
            total_bed += ebrt_bed

        total_eqd2 = total_bed / (1 + (2 / alpha_beta))
        compare_results[organ] = total_eqd2

    # Clean up truth
    truth.pop('_EBRT_DOSE', None)
    
    print(f"  Finished {patient_dir.name}. Echo Results: {list(compare_results.keys())}")

    return {
        "id": patient_dir.name,
        "echo": compare_results,
        "truth": truth
    }

def main():
    parser = argparse.ArgumentParser(description="Validate ECHO against Ground Truth Excel")
    parser.add_argument("--data_dir", required=True, help="Path to validation data folder")
    args = parser.parse_args()
    
    data_path = Path(args.data_dir)
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
        return

    parser_service = ParserService()
    # Use default ratios
    ab_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]

    results = []
    
    for item in data_path.iterdir():
        if item.is_dir():
            # Skip filtered patients if user deleted them, or just let them fail gracefully
            try:
                res = process_patient(item, parser_service, ab_ratios)
                if res and res.get('truth'):
                    p_id = res['id']
                    print(f"  Comparing ECHO vs Truth for {p_id}...")
                    
                    added_count = 0
                    for organ, echo_val in res['echo'].items():
                        # Only compare if we have ground truth
                        # Fuzzy match organ name
                        truth_val = None
                        lbl = organ
                        
                        # Try to find matching key in truth
                        for t_k, t_v in res['truth'].items():
                            if t_k.lower() in organ.lower():
                                truth_val = t_v
                                lbl = t_k
                                break
                        
                        if truth_val is not None:
                            diff = echo_val - truth_val
                            pct = (diff / truth_val) * 100 if truth_val != 0 else 0
                            status = "PASS" if abs(pct) < 2.0 else "FAIL" # 2% Tolerance
                            
                            results.append({
                                "PatientID": p_id,
                                "Structure": lbl,
                                "ECHO_EQD2": round(echo_val, 2),
                                "Excel_EQD2": round(truth_val, 2),
                                "Diff_Pct": round(pct, 2),
                                "Status": status
                            })
                            print(f"    + Added result: {p_id} - {lbl} - {status}")
                            added_count += 1
                        else:
                            print(f"    - Warning: No truth value found for {organ}")
                    if added_count == 0:
                        print(f"    - Warning: No organs matched for {p_id}")
                elif res:
                     print(f"  Warning: No valid ground truth found for {item.name} (truth dict empty or None)")
            except Exception as e:
                print(f"  CRITICAL ERROR processing {item.name}: {e}")
                import traceback
                traceback.print_exc()
    
    if results:
        df = pd.DataFrame(results)
        print("\n--- Validation Report ---")
        print(df.to_string())
        df.to_csv("validation_report.csv", index=False)
        print("\nReport saved to validation_report.csv")
    else:
        print("No results generated.")

if __name__ == "__main__":
    main()
