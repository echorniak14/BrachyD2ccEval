
import pandas as pd

def analyze_d2cc_differences(csv_path):
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: The file '{csv_path}' was not found.")
        return

    # Filter for D2cc metric and specified structures
    structures = ['Rectum', 'Sigmoid', 'Bowel', 'Bladder']
    d2cc_df = df[(df['Metric'] == 'D2cc (Gy)') & (df['Structure'].isin(structures))]

    if d2cc_df.empty:
        print("No D2cc data found for the specified structures.")
        return

    # Calculate absolute dose difference
    d2cc_df['Abs_Diff'] = (d2cc_df['TPS_Text'] - d2cc_df['Calc_DICOM']).abs()

    # Group by structure and calculate the mean of the differences
    results = d2cc_df.groupby('Structure').agg(
        Avg_Pct_Diff=('Pct_Diff', 'mean'),
        Avg_Abs_Dose_Diff=('Abs_Diff', 'mean')
    ).reset_index()

    print("D2cc Calculation Differences for Cylinder Cases:")
    print(results.to_string(index=False))

if __name__ == "__main__":
    analyze_d2cc_differences('feasibility_study.csv')
