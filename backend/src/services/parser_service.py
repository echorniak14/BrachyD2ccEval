import pydicom
import pandas as pd
import numpy as np
import re
import io
from io import StringIO
from pathlib import Path
from bs4 import BeautifulSoup
from ..core import calculations  # Import core math logic

class ParserService:
    def __init__(self):
        pass

    # --- DICOM Parsing Functions ---
    def find_dicom_file(self, directory: str):
        files = list(Path(directory).rglob("*.dcm"))
        if files: return str(files[0])
        return None

    def load_dicom_file(self, file_path: str):
        try: return pydicom.dcmread(file_path)
        except Exception as e: print(f"Error loading DICOM file {file_path}: {e}"); return None

    def get_dicom_files(self, directory: str):
        return list(Path(directory).rglob("*.dcm"))

    def verify_patient_consistency(self, dicom_files):
        if not dicom_files: return True, None
        first_patient_id = pydicom.dcmread(dicom_files[0]).PatientID
        for f in dicom_files[1:]:
            patient_id = pydicom.dcmread(f).PatientID
            if patient_id != first_patient_id: return False, (first_patient_id, patient_id)
        return True, first_patient_id

    def sort_dicom_files(self, dicom_files):
        sorted_files = {"RTDOSE": None, "RTPLAN": None, "RTSTRUCT": None}
        for f in dicom_files:
            modality = pydicom.dcmread(f).Modality
            if modality in sorted_files: sorted_files[modality] = f
        return sorted_files

    def get_structure_data(self, rtstruct_dataset):
        if not rtstruct_dataset: return {}
        try:
            if not hasattr(rtstruct_dataset, 'ROIContourSequence') or not hasattr(rtstruct_dataset, 'StructureSetROISequence') or len(rtstruct_dataset.ROIContourSequence) == 0:
                print("Warning: RTSTRUCT file is missing or has empty structure sequences.")
                return {}
            structures = {}
            for roi_contour, structure_set_roi in zip(rtstruct_dataset.ROIContourSequence, rtstruct_dataset.StructureSetROISequence):
                contour_data = [contour.ContourData for contour in getattr(roi_contour, 'ContourSequence', [])]
                structures[structure_set_roi.ROIName] = {"ROINumber": structure_set_roi.ROINumber, "ContourData": contour_data}
            return structures
        except (AttributeError, KeyError, Exception) as e:
            print(f"Error processing RTSTRUCT file: {e}")
            return {}

    def get_dose_data(self, rtdose_file):
        if not rtdose_file: return None, None, None, None, None, None
        try:
            ds = pydicom.dcmread(rtdose_file) if isinstance(rtdose_file, str) else rtdose_file
            if 'PixelData' not in ds:
                print(f"Warning: RTDOSE file is missing the PixelData tag.")
                return None, None, None, None, None, None
            return ds.pixel_array, ds.DoseGridScaling, ds.ImagePositionPatient, ds.PixelSpacing, ds.GridFrameOffsetVector, ds.ImageOrientationPatient
        except (AttributeError, KeyError, Exception) as e:
            print(f"Error processing RTDOSE file: {e}")
            return None, None, None, None, None, None

    def get_plan_data(self, rtplan_file):
        if not rtplan_file: return {}
        ds = pydicom.dcmread(rtplan_file) if isinstance(rtplan_file, str) else rtplan_file
        plan_data = {}
        plan_name = 'N/A'
        if hasattr(ds, 'RTPlanLabel') and ds.RTPlanLabel: plan_name = ds.RTPlanLabel
        elif hasattr(ds, 'RTPlanName') and ds.RTPlanName: plan_name = ds.RTPlanName
        elif hasattr(ds, 'SeriesDescription') and ds.SeriesDescription: plan_name = ds.SeriesDescription
        plan_data['plan_name'] = plan_name
        plan_data['plan_date'] = getattr(ds, 'RTPlanDate', 'N/A')
        plan_data['plan_time'] = getattr(ds, 'RTPlanTime', 'N/A')
        
        plan_data['source_info'] = 'N/A'; plan_data['rakr'] = 0.0
        plan_data['source_strength_ref_date'] = 'N/A'; plan_data['source_strength_ref_time'] = 'N/A'
        if hasattr(ds, 'SourceSequence') and len(ds.SourceSequence) > 0:
            source = ds.SourceSequence[0]
            if hasattr(source, 'ReferenceAirKermaRate'):
                rakr = float(source.ReferenceAirKermaRate)
                plan_data['source_info'] = f"{rakr:.2f} cGy cm^2/hr"
                plan_data['rakr'] = rakr
            plan_data['source_strength_ref_date'] = getattr(source, 'SourceStrengthReferenceDate', 'N/A')
            plan_data['source_strength_ref_time'] = getattr(source, 'SourceStrengthReferenceTime', 'N/A')

        if hasattr(ds, 'FractionGroupSequence') and len(ds.FractionGroupSequence) > 0:
            fraction_group = ds.FractionGroupSequence[0]
            plan_data['number_of_fractions'] = int(getattr(fraction_group, 'NumberOfFractionsPlanned', 1))
            if hasattr(fraction_group, 'ReferencedBrachyApplicationSetupSequence') and len(fraction_group.ReferencedBrachyApplicationSetupSequence) > 0:
                brachy_setup = fraction_group.ReferencedBrachyApplicationSetupSequence[0]
                plan_data['brachy_dose_per_fraction'] = float(getattr(brachy_setup, 'BrachyApplicationSetupDose', 0.0))
            else: plan_data['brachy_dose_per_fraction'] = 0.0
        else:
            plan_data['number_of_fractions'] = 1
            plan_data['brachy_dose_per_fraction'] = 0.0

        plan_data['dose_references'] = []
        if hasattr(ds, 'DoseReferenceSequence'):
            unnamed_point_counter = 1
            for dr in ds.DoseReferenceSequence:
                point_name = getattr(dr, 'DoseReferenceDescription', '').strip()
                if not point_name or point_name == '-':
                    point_name = f"Unnamed Point {unnamed_point_counter}"
                    unnamed_point_counter += 1
                plan_data['dose_references'].append({'name': point_name, 'dose': dr.TargetPrescriptionDose})

        plan_data['prescription_points'] = []
        if hasattr(ds, 'BrachyApplicationSetupSequence') and len(ds.BrachyApplicationSetupSequence) > 0:
            if getattr(ds.BrachyApplicationSetupSequence[0], 'ApplicationSetupType', '') == 'VAGINAL':
                if hasattr(ds, 'DoseReferenceSequence'):
                    for dr in ds.DoseReferenceSequence:
                        point_name = dr.DoseReferenceDescription.lower()
                        if any(name in point_name for name in ['tip', 'shoulder', '3cm', '3.5cm', '2cm', '2.5cm']):
                            plan_data['prescription_points'].append({'name': dr.DoseReferenceDescription, 'coordinates': dr.DoseReferencePointCoordinates})

        plan_data['channel_mapping'] = []
        brachy_app_setup_sequence = ds.get((0x300a, 0x0230))
        if brachy_app_setup_sequence:
            for app_setup in brachy_app_setup_sequence:
                if hasattr(app_setup, 'ChannelSequence'):
                    for channel_item in app_setup.ChannelSequence:
                        channel_info = {
                            'channel_number': getattr(channel_item, 'ChannelNumber', 'N/A'),
                            'transfer_tube_number': getattr(channel_item, 'TransferTubeNumber', 'N/A'),
                        }
                        plan_data['channel_mapping'].append(channel_info)
        return plan_data

    def get_dose_point_mapping(self, rtplan_file, point_dose_constraints):
        ds = pydicom.dcmread(rtplan_file)
        mapping = {}
        if "DoseReferenceSequence" not in ds: return mapping
        for dose_ref in ds.DoseReferenceSequence:
            if "DoseReferenceDescription" in dose_ref:
                dicom_point_name = dose_ref.DoseReferenceDescription.lower()
                cylinder_point_keywords = ['tip', 'shoulder', '3cm', '3.5cm', '2cm', '2.5cm']
                if any(keyword in dicom_point_name for keyword in cylinder_point_keywords):
                    mapping[dose_ref.DoseReferenceDescription] = "Prescription Point"
                    continue
                rv_point_keywords = ['rv', 'rv point', 'rv pt']
                if any(keyword in dicom_point_name for keyword in rv_point_keywords):
                    mapping[dose_ref.DoseReferenceDescription] = "RV Point"
                    continue
                point_a_keywords = ['a_rt', 'a_lt']
                if any(keyword in dicom_point_name for keyword in point_a_keywords):
                    mapping[dose_ref.DoseReferenceDescription] = "Point A"
                    continue
                exact_match_found = False
                for constraint_name in point_dose_constraints.keys():
                    if dicom_point_name == constraint_name.lower():
                        mapping[dose_ref.DoseReferenceDescription] = constraint_name
                        exact_match_found = True
                        break
                if not exact_match_found:
                    for constraint_name in point_dose_constraints.keys():
                        if constraint_name.lower() in dicom_point_name:
                            mapping[dose_ref.DoseReferenceDescription] = constraint_name
                            break
        return mapping

    def get_control_point_data(self, rtplan_file):
        if not rtplan_file: return []
        ds = pydicom.dcmread(rtplan_file)
        control_points = []
        if hasattr(ds, 'BrachyApplicationSetupSequence'):
            for app_setup in ds.BrachyApplicationSetupSequence:
                if hasattr(app_setup, 'BrachyControlPointSequence'):
                    for cp in app_setup.BrachyControlPointSequence:
                        control_points.append({'position': cp.ControlPoint3DPosition, 'dose': cp.ControlPointCumulativeTimeWeight})
        return control_points

    def get_dwell_times_and_positions(self, rtplan_file):
        plan = pydicom.dcmread(rtplan_file) if isinstance(rtplan_file, (str, Path, io.BytesIO)) else rtplan_file
        dwell_data = []
        brachy_app_setup_sequence = plan.get((0x300a, 0x0230))
        if not brachy_app_setup_sequence or not hasattr(brachy_app_setup_sequence[0], 'ChannelSequence'): return dwell_data
        for channel in brachy_app_setup_sequence[0].ChannelSequence:
            channel_total_time = float(channel.ChannelTotalTime)
            final_cumulative_time_weight = float(channel.FinalCumulativeTimeWeight)
            if final_cumulative_time_weight == 0: continue
            control_points = channel.BrachyControlPointSequence
            for i in range(1, len(control_points)):
                dwell_time_weight = float(control_points[i].CumulativeTimeWeight) - float(control_points[i-1].CumulativeTimeWeight)
                if dwell_time_weight > 0:
                    dwell_time = dwell_time_weight * channel_total_time / final_cumulative_time_weight
                    position = float(control_points[i].ControlPointRelativePosition)
                    dwell_data.append({"position": position, "dwell_time": dwell_time})
        return dwell_data

    # --- DVH Text Parsing ---
    def parse_dvh_text_file(self, file_content: str):
        if isinstance(file_content, bytes): file_content = file_content.decode('utf-8')
        structures = {}; metadata = {}
        header_lines = file_content.splitlines()[:20]
        header_text = "\n".join(header_lines)
        
        pat_name_match = re.search(r"Patient[:\s]+(.*?)(?:\r|\n|$)", header_text, re.IGNORECASE)
        pat_id_match = re.search(r"Patient Id[:\s]+(.*?)(?:\r|\n|$)", header_text, re.IGNORECASE)
        if pat_name_match: metadata['patient_name'] = pat_name_match.group(1).strip()
        if pat_id_match: metadata['patient_id'] = pat_id_match.group(1).strip()

        roi_blocks = re.split(r'ROI[:\s]+', file_content)
        if len(roi_blocks) < 2: return structures, metadata

        for block in roi_blocks[1:]:
            lines = block.strip().splitlines()
            if not lines: continue
            roi_name = lines[0].strip()
            header_idx = -1
            for i, line in enumerate(lines):
                if "Bin" in line and "Dose" in line: header_idx = i; break
            if header_idx == -1: continue
            
            try:
                data_string = "\n".join(lines[header_idx+1:])
                df = pd.read_csv(StringIO(data_string), sep=r'\t| {2,}', engine='python', header=None).dropna(axis=1, how='all').dropna(axis=0, how='all')
                if df.shape[1] < 2: continue
                if df.shape[1] >= 3: doses_cgy = df.iloc[:, 1].values.astype(float); volumes_cc = df.iloc[:, 2].values.astype(float)
                else: doses_cgy = df.iloc[:, 0].values.astype(float); volumes_cc = df.iloc[:, 1].values.astype(float)

                doses_gy = doses_cgy
                if np.max(doses_cgy) > 100: doses_gy = doses_cgy / 100.0
                sort_idx = np.argsort(doses_gy)
                structures[roi_name] = {"volume_cc": np.max(volumes_cc), "dose_axis": doses_gy[sort_idx], "vol_axis": volumes_cc[sort_idx], "dose_unit": "Gy"}
            except Exception: continue
        return structures, metadata

    def get_dvh_metrics_from_text(self, parsed_dvh_data, structure_mapping, number_of_fractions, previous_brachy_bed_per_organ=None):
        """
        Calculates DVH metrics using parsed text data and Core math functions.
        Refactored to Service layer.
        """
        if previous_brachy_bed_per_organ is None: previous_brachy_bed_per_organ = {}
        dvh_results = {}

        for struct_name, data in parsed_dvh_data.items():
            normalized_name = calculations.normalize_structure_name(struct_name)
            standardized_name = normalized_name 
            
            if structure_mapping:
                for map_key, map_val in structure_mapping.items():
                    if map_key.lower() == struct_name.lower():
                        standardized_name = map_val
                        break

            # DELEGATE TO CORE MATH (imported from backend.src.core.calculations)
            d2cc = calculations.get_dose_at_volume(data, 2.0)
            d1cc = calculations.get_dose_at_volume(data, 1.0)
            d0_1cc = calculations.get_dose_at_volume(data, 0.1)
            d90 = calculations.get_dose_at_percent_volume(data, 90.0)
            d98 = calculations.get_dose_at_percent_volume(data, 98.0)
            d95 = calculations.get_dose_at_percent_volume(data, 95.0)
            max_dose = float(np.max(data["dose_axis"]))
            min_dose = float(np.min(data["dose_axis"]))
            
            previous_bed_data = {}
            if standardized_name and standardized_name != "Ignore":
                 for history_key, history_value in previous_brachy_bed_per_organ.items():
                    if history_key.lower() == standardized_name.lower():
                        previous_bed_data = history_value
                        break

            dvh_results[standardized_name] = {
                'volume_cc': data['volume_cc'],
                'd2cc_gy_per_fraction': d2cc, 'd1cc_gy_per_fraction': d1cc, 'd0_1cc_gy_per_fraction': d0_1cc,
                'max_dose_gy_per_fraction': max_dose, 'mean_dose_gy_per_fraction': 0.0, 'min_dose_gy_per_fraction': min_dose,
                'd95_gy_per_fraction': d95, 'd98_gy_per_fraction': d98, 'd90_gy_per_fraction': d90,
                'previous_brachy_bed': previous_bed_data,
                'dose_axis': data['dose_axis'],
                'vol_axis': data['vol_axis']
            }
        return dvh_results

    def parse_html_report(self, file_content: str):
        eqd2_results = {}
        try:
            soup = BeautifulSoup(file_content, 'html.parser')
            table = soup.find('h2', string='Dose Volume Histogram (DVH) Results').find_next_sibling('table')
            if not table: return eqd2_results
            headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]
            try: organ_col_idx = headers.index('Organ'); eqd2_col_idx = headers.index('EQD2 (Gy)')
            except ValueError: return eqd2_results
            for row in table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                if len(cols) > max(organ_col_idx, eqd2_col_idx):
                    organ_name = cols[organ_col_idx].get_text(strip=True)
                    try: eqd2_results[organ_name] = float(cols[eqd2_col_idx].get_text(strip=True))
                    except ValueError: pass
        except Exception: pass
        return eqd2_results