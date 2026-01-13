import sys
import os
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from datetime import datetime
import pydicom
import io
from .parser_service import ParserService

def parse_mosaiq_schedule_for_hdr_tx(file_path):
    """
    Parses the Mosaiq schedule Excel export to find HDR treatment dates.
    """
    try:
        df = pd.read_excel(file_path)
        
        # Filter for rows containing 'HDR' and 'tx' (case-insensitive)
        # We ensure the columns exist before filtering to avoid KeyErrors
        if 'Activity' not in df.columns or 'Description' not in df.columns or 'Sts' not in df.columns:
            return []

        hdr_tx_schedule = df[
            df['Activity'].str.contains('HDR', case=False, na=False) &
            df['Description'].str.contains('tx', case=False, na=False)
        ].copy()
        
        # Exclude cancelled/rescheduled appointments (Status 'X')
        hdr_tx_schedule = hdr_tx_schedule[~hdr_tx_schedule['Sts'].str.contains('X', na=False)]
        
        # Parse Dates and Times
        hdr_tx_schedule['Date'] = pd.to_datetime(hdr_tx_schedule['Date'], errors='coerce')
        hdr_tx_schedule['Time'] = hdr_tx_schedule['Time'].astype(str)
        hdr_tx_schedule.dropna(subset=['Date'], inplace=True)
        
        # Combine Date and Time
        hdr_tx_schedule['datetime'] = pd.to_datetime(
            hdr_tx_schedule['Date'].dt.strftime('%Y-%m-%d') + ' ' + hdr_tx_schedule['Time'],
            format='mixed'
        )
        
        return sorted(hdr_tx_schedule['datetime'].tolist())
    except Exception as e:
        print(f"Error parsing Mosaiq schedule file: {e}")
        return []

def generate_dwell_time_sheet(mosaiq_schedule_path, rtplan_file_content):
    """
    Generates an Excel sheet with dwell time information based on a Mosaiq schedule
    and an RTPLAN file. Returns the Excel file as bytes.
    """
    # 1. Locate the Template File
    # Relative path: backend/src/services -> backend/src -> src (frontend) -> templates
    # Adjust this path if your templates are stored elsewhere.
    # Assuming standard structure: project_root/src/templates/
    base_path = Path(__file__).parent.parent.parent.parent / 'src' 
    template_excel_path = base_path / 'templates' / 'Dwell time decay Worksheet Cylinder.xlsx'

    # 2. Parse Mosaiq Schedule
    fraction_datetimes = parse_mosaiq_schedule_for_hdr_tx(mosaiq_schedule_path)
    
    if not fraction_datetimes:
        print("No 'HDR: tx' activities found in the schedule.")
        # Proceeding might be useless, but we can return None or an empty-ish sheet
        # Returning None signals failure to the API
        return None

    # 3. Parse RTPLAN Data
    try:
        ds = pydicom.dcmread(io.BytesIO(rtplan_file_content))
        parser = ParserService()
        
        # Extract Plan Info
        patient_name = str(ds.PatientName)
        patient_mrn = str(ds.PatientID)
        plan_data = parser.get_plan_data(ds)
        plan_name = plan_data.get('plan_name', 'N/A')
        
        # Format Reference Date
        ref_date = plan_data.get('source_strength_ref_date', 'N/A')
        ref_time = plan_data.get('source_strength_ref_time', 'N/A')
        plan_date_str = "N/A"
        if ref_date != 'N/A' and ref_time != 'N/A':
            try:
                dt_obj = datetime.strptime(f"{ref_date}{ref_time.split('.')[0]}", "%Y%m%d%H%M%S")
                plan_date_str = dt_obj.strftime('%Y-%m-%d %H:%M')
            except ValueError:
                pass

        # Calculate Source Activity in Ci
        rakr = plan_data.get('rakr', 0.0)
        source_activity_ci = rakr / 4.0367 / 1000 # Conv factor for Ir-192 RAKR to Ci

        # Extract Dwell Times
        # Note: We need to use the method from ParserService, but it expects a file path usually.
        # Since we have the dataset 'ds', we can adapt the logic or pass a dummy path if it doesn't use it.
        # Looking at ParserService.get_dwell_times_and_positions, it calls pydicom.dcmread(rtplan_file).
        # We should modify ParserService to accept a dataset, or duplicate the logic here for bytes.
        # Duplicating small logic here for robustness with ByteStream:
        
        dwell_data = []
        brachy_app_setup = ds.get((0x300a, 0x0230))
        if brachy_app_setup and hasattr(brachy_app_setup[0], 'ChannelSequence'):
            for channel in brachy_app_setup[0].ChannelSequence:
                total_time = float(channel.ChannelTotalTime)
                final_weight = float(channel.FinalCumulativeTimeWeight)
                if final_weight > 0:
                    control_points = channel.BrachyControlPointSequence
                    for i in range(1, len(control_points)):
                        weight = float(control_points[i].CumulativeTimeWeight) - float(control_points[i-1].CumulativeTimeWeight)
                        if weight > 0:
                            time = weight * total_time / final_weight
                            pos = float(control_points[i].ControlPointRelativePosition)
                            dwell_data.append({"position": pos, "dwell_time": time})

    except Exception as e:
        print(f"Error parsing RTPLAN content: {e}")
        return None

    # 4. Populate Excel Template
    try:
        wb = load_workbook(template_excel_path)
        ws = wb.active
        
        # Patient Info
        ws['B5'] = patient_name
        ws['B6'] = patient_mrn
        ws['B7'] = plan_name
        ws['B11'] = plan_date_str
        ws['B13'] = source_activity_ci

        # Fractions Dates (Columns C, D, E, F, G...)
        fraction_cells = ['C11', 'D11', 'E11', 'F11', 'G11']
        for i, dt in enumerate(fraction_datetimes):
            if i < len(fraction_cells):
                ws[fraction_cells[i]] = dt.strftime('%Y-%m-%d %H:%M')
        
        # Fraction Numbers
        ws['B9'] = "Plan"
        header_cells = ['C9', 'D9', 'E9', 'F9', 'G9']
        for i in range(len(fraction_datetimes)):
             if i < len(header_cells):
                ws[header_cells[i]] = i + 1
        
        # Dwell Times
        # Map: Position (mm) -> Time (s)
        # Note: 300mm is typically the Tip for some applicators, logic from original script
        excel_dwell_map = {300 - int(item['position']): item['dwell_time'] for item in dwell_data}
        
        dwell_time_start_row = 17
        for i in range(12): # Iterate through the standard positions in the sheet
            position_cell = f'A{dwell_time_start_row + i}'
            dwell_time_cell = f'B{dwell_time_start_row + i}'
            
            position_val = ws[position_cell].value
            
            # Match based on position in Column A
            if position_val is not None and position_val in excel_dwell_map:
                ws[dwell_time_cell] = excel_dwell_map[position_val]
            else:
                ws[dwell_time_cell] = 0.0
        
        # Save to in-memory stream
        excel_bytes_io = io.BytesIO()
        wb.save(excel_bytes_io)
        excel_bytes_io.seek(0)
        return excel_bytes_io.getvalue()

    except FileNotFoundError:
        print(f"Error: The template file was not found at '{template_excel_path}'.")
        return None
    except Exception as e:
        print(f"An error occurred while populating the Excel template: {e}")
        return None