import pandas as pd
from datetime import datetime
from openpyxl import load_workbook

# --- Helper Function ---

def parse_mosaiq_schedule_for_hdr_tx(file_path):
    """
    Parses a Mosaiq schedule to find dates and times for HDR treatments.
    It filters for rows where 'Activity' contains 'HDR' and 'Description' contains 'tx',
    and excludes appointments with a cancelled status ('X').
    """
    try:
        # Use the default engine 'openpyxl' for .xlsx files
        df = pd.read_excel(file_path)
        
        # Filter for rows where 'Activity' contains 'HDR' and 'Description' contains 'tx' (case-insensitive)
        hdr_tx_schedule = df[
            df['Activity'].str.contains('HDR', case=False, na=False) & 
            df['Description'].str.contains('tx', case=False, na=False)
        ].copy()

        # --- NEW: Filter out cancelled appointments ---
        # Exclude rows where the 'Sts' column contains 'X'
        hdr_tx_schedule = hdr_tx_schedule[~hdr_tx_schedule['Sts'].str.contains('X', na=False)]
        # ---------------------------------------------

        # Convert 'Date' and 'Time' columns to datetime objects
        hdr_tx_schedule['Date'] = pd.to_datetime(hdr_tx_schedule['Date'], errors='coerce')
        hdr_tx_schedule['Time'] = hdr_tx_schedule['Time'].astype(str)
        hdr_tx_schedule.dropna(subset=['Date'], inplace=True)
        
        # Combine date and time into a single datetime column
        hdr_tx_schedule['datetime'] = pd.to_datetime(
            hdr_tx_schedule['Date'].dt.strftime('%Y-%m-%d') + ' ' + hdr_tx_schedule['Time']
        )
        
        # Sort and return the list of datetimes
        return sorted(hdr_tx_schedule['datetime'].tolist())

    except Exception as e:
        print(f"Error parsing Mosaiq schedule file: {e}")
        return []

# --- Main Script ---

def main():
    # --- Define File Paths ---
    mosaiq_schedule_path = r'C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\sample_data.xlsx'
    # IMPORTANT: The template file MUST be saved in the modern .xlsx format.
    template_excel_path = r'C:\Users\echorniak\GIT\BrachyD2ccEval\sample_data\Dwell time decay Worksheet Cylinder.xlsx'
    output_excel_path = r'C:\Users\echorniak\GIT\BrachyD2ccEval\temp_scripts\populated_dwell_time_sheet.xlsx'
    # -------------------------

    print("1. Parsing Mosaiq schedule for 'HDR: tx' activities...")
    fraction_datetimes = parse_mosaiq_schedule_for_hdr_tx(mosaiq_schedule_path)
    if not fraction_datetimes:
        print("No 'HDR: tx' activities found in the schedule. Exiting.")
        return
    print(f"Found {len(fraction_datetimes)} HDR treatment fractions.")

    print("\n2. Populating the Excel template...")
    try:
        wb = load_workbook(template_excel_path)
        ws = wb.active

        # --- Populate Header Info with Placeholders ---
        ws['B5'] = "Patient Name (from DICOM)"
        ws['B6'] = "Patient MRN (from DICOM)"
        ws['B7'] = "Plan Name (from DICOM)"

        # --- Populate Fraction Dates and Times from Parsed Schedule ---
        # Populate Planned Date/Time (from first fraction)
        if fraction_datetimes:
            ws['B11'] = fraction_datetimes[0].strftime('%Y-%m-%d %H:%M')

        # Populate Subsequent Fraction Dates/Times
        subsequent_fraction_cells = ['C11', 'D11', 'E11', 'F11']
        for i, dt in enumerate(fraction_datetimes[1:]): # Start from the second fraction
            if i < len(subsequent_fraction_cells):
                ws[subsequent_fraction_cells[i]] = dt.strftime('%Y-%m-%d %H:%M')

        # Populate Fraction Headers
        ws['B9'] = "Plan"
        header_cells = ['C9', 'D9', 'E9', 'F9', 'G9']
        for i in range(len(fraction_datetimes)):
             if i < len(header_cells):
                ws[header_cells[i]] = i + 1
        
        # --- Populate Source Strength and Dwell Times with Placeholders ---
        ws['B13'] = 0.0  # Placeholder for Strength in Ci
        
        dwell_time_start_row = 17
        for i in range(12): # Template has 12 rows for dwell times
            cell_ref = f'B{dwell_time_start_row + i}'
            ws[cell_ref] = 0.0 # Placeholder for dwell times

        wb.save(output_excel_path)
        print(f"\nSuccessfully created populated Excel sheet at: {output_excel_path}")

    except FileNotFoundError:
        print(f"Error: The template file was not found at '{template_excel_path}'.")
        print("Please ensure you have saved it as an .xlsx file and the path is correct.")
    except Exception as e:
        print(f"An error occurred while populating the Excel template: {e}")

if __name__ == "__main__":
    main()
