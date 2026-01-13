import unittest
import sys
import os

# 1. Add PROJECT ROOT to path (so we can import 'backend')
# This assumes the test file is in the project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 2. Import from the new location
from backend.src.core.calculations import calculate_bed_and_eqd2, calculate_optimization_goal

class TestDoseCalculations(unittest.TestCase):

    def setUp(self):
        # Define standard Alpha/Beta ratios for testing
        self.ab_ratios = {
            "Bladder": 3.0,
            "Rectum": 3.0,
            "HRCTV": 10.0,
            "Default": 3.0
        }

    def test_basic_eqd2_calculation(self):
        """
        Test Case 1: Simple single-fraction brachytherapy calculation.
        Verifies the core EQD2 formula: D * (1 + d/ab) / (1 + 2/ab)
        """
        organ = "Bladder" # alpha/beta = 3
        dose_per_fx = 5.0
        total_dose = 5.0 # 1 fraction
        
        # Manual Math:
        # BED = 5 * (1 + 5/3) = 5 * (2.6667) = 13.3333
        # EQD2 = 13.3333 / (1 + 2/3) = 13.3333 / 1.6667 = 8.0
        
        total_bed, eqd2, bed_brachy, bed_ebrt, prev_bed = calculate_bed_and_eqd2(
            total_dose=total_dose,
            dose_per_fraction=dose_per_fx,
            organ_name=organ,
            alpha_beta_ratios=self.ab_ratios
        )

        self.assertAlmostEqual(eqd2, 8.0, places=2, msg="Basic EQD2 calc failed")
        self.assertAlmostEqual(bed_brachy, 13.33, places=2, msg="Basic BED calc failed")

    def test_full_accumulation(self):
        """
        Test Case 2: The "Hybrid" Accumulation.
        Total EQD2 = Brachy (Current) + EBRT + History
        """
        organ = "Rectum" # alpha/beta = 3
        
        # 1. Current Brachy: 1 fx of 4 Gy
        # BED = 4 * (1 + 4/3) = 4 * 2.333 = 9.333
        current_dose_fx = 4.0
        current_total = 4.0
        
        # 2. EBRT: 45 Gy in 25 fx (1.8 Gy/fx)
        # BED = 45 * (1 + 1.8/3) = 45 * (1.6) = 72.0
        ebrt_dose = 45.0
        ebrt_fractions = 25
        
        # 3. History: 100 Gy BED (arbitrary value from JSON)
        history_bed = 100.0
        
        # Expected Total BED = 9.33 + 72.0 + 100.0 = 181.33
        # Expected Total EQD2 = 181.33 / 1.6667 = 108.8
        
        total_bed, eqd2, _, _, _ = calculate_bed_and_eqd2(
            total_dose=current_total,
            dose_per_fraction=current_dose_fx,
            organ_name=organ,
            ebrt_dose=ebrt_dose,
            ebrt_fractions=ebrt_fractions,
            previous_brachy_bed=history_bed,
            alpha_beta_ratios=self.ab_ratios
        )
        
        self.assertAlmostEqual(total_bed, 181.33, places=1, msg="Accumulated BED mismatch")
        self.assertAlmostEqual(eqd2, 108.80, places=1, msg="Accumulated EQD2 mismatch")

    def test_fraction_scaling(self):
        """
        Test Case 3: Verify that increasing fractions scales the BED correctly.
        Comparison: 1 fraction vs 3 fractions of the SAME dose per fraction.
        """
        organ = "HRCTV" # alpha/beta = 10
        dose_per_fx = 7.0
        
        # Run 1: Single Fraction
        _, _, bed_1fx, _, _ = calculate_bed_and_eqd2(
            total_dose=7.0, 
            dose_per_fraction=dose_per_fx, 
            organ_name=organ, 
            alpha_beta_ratios=self.ab_ratios
        )
        
        # Run 2: Three Fractions
        # Total dose triples (21 Gy), but dose_per_fraction stays 7.0
        _, _, bed_3fx, _, _ = calculate_bed_and_eqd2(
            total_dose=21.0, 
            dose_per_fraction=dose_per_fx, 
            organ_name=organ, 
            alpha_beta_ratios=self.ab_ratios
        )
        
        # The BED should exactly triple because d (dose per fraction) didn't change
        # BED = n * d * (1 + d/ab)
        self.assertAlmostEqual(bed_3fx, bed_1fx * 3, places=2, msg="Fraction scaling failed")

    def test_zero_history_handling(self):
        """
        Test Case 4: Zero History Check.
        Ensures the system doesn't crash or return Null if previous BED is 0.
        """
        organ = "Bladder"
        
        total_bed, eqd2, _, _, _ = calculate_bed_and_eqd2(
            total_dose=5.0,
            dose_per_fraction=5.0,
            organ_name=organ,
            previous_brachy_bed=0, # Explicitly zero
            alpha_beta_ratios=self.ab_ratios
        )
        
        # Should just be the Brachy BED (13.33 from Test 1)
        self.assertAlmostEqual(total_bed, 13.33, places=2, msg="Zero history handling failed")

    def test_optimization_goal(self):
        """
        Test Case 5: 'Dose to Meet Constraint' (ALARA Check).
        If we want to hit exactly 80 Gy EQD2 total, and we have 0 history,
        what physical dose do we need?
        """
        # Target EQD2 = 80 Gy
        # Alpha/Beta = 3
        # BED Target = 80 * (1 + 2/3) = 80 * 1.6667 = 133.33 Gy
        # Solve for d: d * (1 + d/3) = 133.33 (for 1 fraction)
        # 3d + d^2 = 400 -> d^2 + 3d - 400 = 0
        # d = (-3 + sqrt(9 - 4(1)(-400))) / 2 = (-3 + sqrt(1609)) / 2
        # d = (-3 + 40.11) / 2 = 18.55 Gy approx
        
        calculated_dose = calculate_optimization_goal(
            total_eqd2_constraint=80.0,
            alpha_beta=3.0,
            ebrt_dose=0,
            ebrt_fractions=1,
            previous_brachy_bed=0,
            num_new_brachy_fractions=1
        )
        
        self.assertAlmostEqual(calculated_dose, 18.55, places=1, msg="Optimization goal calc failed")

if __name__ == '__main__':
    print("Running Verification Suite for ECHO (Calculations Module)...")
    unittest.main()