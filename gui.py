import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import json

class BrachyApp:
    def __init__(self, master):
        self.master = master
        master.title("Brachytherapy Plan Evaluator")

        # Data Directory Input
        self.data_dir_label = tk.Label(master, text="DICOM Data Directory:")
        self.data_dir_label.grid(row=0, column=0, sticky="w")
        self.data_dir_entry = tk.Entry(master, width=50)
        self.data_dir_entry.grid(row=0, column=1, padx=5, pady=5)
        self.data_dir_button = tk.Button(master, text="Browse", command=self.browse_data_dir)
        self.data_dir_button.grid(row=0, column=2, padx=5, pady=5)

        # EBRT Input
        self.ebrt_frame = tk.LabelFrame(master, text="External Beam Radiation Therapy (EBRT)")
        self.ebrt_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

        self.ebrt_dose_label = tk.Label(self.ebrt_frame, text="EBRT Dose (Gy):")
        self.ebrt_dose_label.grid(row=0, column=0, sticky="w")
        self.ebrt_dose_entry = tk.Entry(self.ebrt_frame, width=10) # Always enabled
        self.ebrt_dose_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ebrt_dose_entry.insert(0, "0.0") # Default value to 0.0

        # Previous Brachytherapy Input (Placeholder for now)
        self.prev_brachy_frame = tk.LabelFrame(master, text="Previous Brachytherapy Treatments")
        self.prev_brachy_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        self.prev_brachy_label = tk.Label(self.prev_brachy_frame, text="(Input for previous brachytherapy will go here)")
        self.prev_brachy_label.grid(row=0, column=0, padx=5, pady=5)

        # Run Button
        self.run_button = tk.Button(master, text="Run Evaluation", command=self.run_evaluation)
        self.run_button.grid(row=3, column=0, columnspan=3, pady=10)

        # Plan Name Display
        self.plan_name_label = tk.Label(master, text="", font=("Arial", 10, "italic"))
        self.plan_name_label.grid(row=4, column=0, columnspan=3, pady=5)

        self.output_html_path = "Brachytherapy_Report.html" # Store as instance variable

    def browse_data_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.data_dir_entry.delete(0, tk.END)
            self.data_dir_entry.insert(0, directory)

    def run_evaluation(self):
        data_dir = self.data_dir_entry.get()
        ebrt_dose_str = self.ebrt_dose_entry.get()

        if not data_dir:
            messagebox.showerror("Input Error", "Please select a DICOM Data Directory.")
            return

        try:
            ebrt_dose = float(ebrt_dose_str)
        except ValueError:
            messagebox.showerror("Input Error", "EBRT Dose must be a number.")
            return

        # Construct the command to run main.py
        command = ["python", "main.py", "--data_dir", data_dir, "--ebrt_dose", str(ebrt_dose), "--output_html", self.output_html_path]

        # Run the subprocess and handle its output
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            output_data = json.loads(result.stdout)

            if "error" in output_data:
                messagebox.showerror("Evaluation Error", output_data["error"])
            else:
                self.plan_name_label.config(text=f"Plan: {output_data.get('plan_name', 'N/A')}")
                messagebox.showinfo("Report Generated", f"HTML report saved to {self.output_html_path}")
                import webbrowser
                webbrowser.open(self.output_html_path) # Open the HTML report in browser

        except subprocess.CalledProcessError as e:
            messagebox.showerror("Evaluation Error", f"Error: {e.stderr}")
        except json.JSONDecodeError:
            messagebox.showerror("Input Error", "Could not parse JSON output from main.py. Check console for raw output.")
            print("Raw main.py output:", result.stdout) # For debugging
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def display_results(self, data):
        results_window = tk.Toplevel(self.master)
        results_window.title("Evaluation Results")

        tk.Label(results_window, text=f"Patient Name: {data['patient_name']}", font=("Arial", 12, "bold")).pack(pady=10)

        # Create a Treeview widget for structured display
        tree = ttk.Treeview(results_window, columns=("Volume", "D2cc/fx", "Total D2cc", "BED", "EQD2", "EQD2 Met"), show="headings tree headings")
        tree.pack(expand=True, fill="both", padx=10, pady=10)

        tree.heading("#0", text="Organ") # Heading for the tree column (organ name)
        tree.heading("Volume", text="Volume (cc)")
        tree.heading("D2cc/fx", text="D2cc/fx (Gy)")
        tree.heading("Total D2cc", text="Total D2cc (Gy)")
        tree.heading("BED", text="BED (Gy)")
        tree.heading("EQD2", text="EQD2 (Gy)")
        tree.heading("EQD2 Met", text="EQD2 Met")

        # Configure column widths
        tree.column("#0", width=100, anchor="w") # Width for the tree column
        tree.column("Volume", width=80, anchor="center")
        tree.column("D2cc/fx", width=100, anchor="center")
        tree.column("Total D2cc", width=100, anchor="center")
        tree.column("BED", width=80, anchor="center")
        tree.column("EQD2", width=80, anchor="center")
        tree.column("EQD2 Met", width=80, anchor="center")

        # Add tags for coloring
        tree.tag_configure("met", background="#D4EDDA", foreground="#155724") # Light green
        tree.tag_configure("not_met", background="#F8D7DA", foreground="#721C24") # Light red

        for organ, dvh_data in data['dvh_results'].items():
            eqd2_met_text = "N/A"
            eqd2_tag = ""

            if organ in data['constraint_evaluation']:
                constraints = data['constraint_evaluation'][organ]
                if "EQD2_met" in constraints:
                    eqd2_met_text = "Met" if constraints["EQD2_met"] == "True" else "NOT Met"
                    eqd2_tag = "met" if constraints["EQD2_met"] == "True" else "not_met"

            tree.insert("", "end", text=organ, values=(
                dvh_data["volume_cc"],
                dvh_data["d2cc_gy_per_fraction"],
                dvh_data["total_d2cc_gy"],
                dvh_data["bed"],
                dvh_data["eqd2"],
                eqd2_met_text
            ), tags=(eqd2_tag))

        

root = tk.Tk()
app = BrachyApp(root)
root.mainloop()