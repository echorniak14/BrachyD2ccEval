import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def analyze_feasibility(csv_path):
    """
    Reads the feasibility CSV and generates clinical validation charts.
    """
    if not os.path.exists(csv_path):
        print(f"Error: File not found at {csv_path}")
        print("Run the 'Plan Analysis' in the GUI and click 'Add to Feasibility Study' first.")
        return

    df = pd.read_csv(csv_path)
    
    # Filter out empty or zero-dose rows to avoid skewing stats
    df = df[df['TPS_Text'] > 0.01]
    
    print(f"Loaded {len(df)} data points from {csv_path}")
    print("-" * 60)

    # 1. SUMMARY STATISTICS
    # Group by Metric (D2cc, D90, etc.) and calculate mean error
    summary = df.groupby('Metric')['Pct_Diff'].agg(['mean', 'std', 'min', 'max', 'count'])
    summary = summary.rename(columns={'mean': 'Mean % Diff', 'std': 'Std Dev', 'count': 'N'})
    print("\n--- Summary Statistics by Metric ---")
    print(summary.round(2))
    print("-" * 60)

    # 2. CREATE CHARTS
    # Set style
    sns.set_theme(style="whitegrid")
    
    # Chart A: Regression Plot (TPS vs. Calculated)
    # Ideally, all points should lie on the y=x diagonal line.
    plt.figure(figsize=(10, 6))
    scatter = sns.scatterplot(
        data=df, 
        x='TPS_Text', 
        y='Calc_DICOM', 
        hue='Structure', 
        style='Metric', 
        s=100, 
        alpha=0.8
    )
    
    # Add a perfect reference line (y=x)
    max_val = max(df['TPS_Text'].max(), df['Calc_DICOM'].max())
    plt.plot([0, max_val], [0, max_val], color='red', linestyle='--', label='Ideal Match (y=x)')
    
    plt.title("Correlation: Planning System vs. Independent Calculation", fontsize=14)
    plt.xlabel("TPS Reported Dose (Gy)", fontsize=12)
    plt.ylabel("Calculated Dose (Gy)", fontsize=12)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    
    # Save Chart A
    output_dir = os.path.dirname(csv_path)
    chart_a_path = os.path.join(output_dir, "Feasibility_Correlation_Plot.png")
    plt.savefig(chart_a_path)
    print(f"Generated Correlation Plot: {chart_a_path}")

    # Chart B: Error Distribution (Histogram)
    # Shows if we are consistently over/under estimating
    plt.figure(figsize=(10, 6))
    sns.histplot(data=df, x='Pct_Diff', hue='Metric', kde=True, element="step")
    
    plt.axvline(0, color='black', linestyle='--')
    plt.title("Distribution of % Differences (Calc - TPS)", fontsize=14)
    plt.xlabel("% Difference", fontsize=12)
    plt.ylabel("Count", fontsize=12)
    plt.tight_layout()
    
    # Save Chart B
    chart_b_path = os.path.join(output_dir, "Feasibility_Error_Histogram.png")
    plt.savefig(chart_b_path)
    print(f"Generated Histogram: {chart_b_path}")
    
    # 3. PASS/FAIL CHECK
    # Define clinical tolerance (e.g., +/- 5%)
    TOLERANCE_PERCENT = 5.0
    passing = df[abs(df['Pct_Diff']) <= TOLERANCE_PERCENT]
    pass_rate = (len(passing) / len(df)) * 100.0
    
    print("\n" + "="*30)
    print(f"FEASIBILITY RESULT: {pass_rate:.1f}% of points are within {TOLERANCE_PERCENT}% tolerance.")
    print("="*30)

if __name__ == "__main__":
    # Assumes the csv is in the project root
    csv_location = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feasibility_study.csv")
    analyze_feasibility(csv_location)