import unittest
import sys
import os
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.src.core.calculations import get_dose_at_volume, get_dose_at_percent_volume, get_dose_at_point
from backend.src.core.validators import validate_tps_import

class TestHybridFeatures(unittest.TestCase):

    def setUp(self):
        # Mock DVH Data (Text File Format)
        # Volume decreases as Dose increases
        self.mock_structure_data = {
            "volume_cc": 100.0,
            "dose_axis": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
            "vol_axis":  np.array([100.0, 80.0, 50.0, 20.0, 5.0, 0.0]),
            "dose_unit": "Gy"
        }

    # --- 1. TEST INTERPOLATION (New Source of Truth) ---
    def test_dose_at_volume_exact(self):
        """Test exact match in the array (20cc -> 30Gy)."""
        dose = get_dose_at_volume(self.mock_structure_data, 20.0)
        self.assertAlmostEqual(dose, 30.0, places=2)

    def test_dose_at_volume_interp(self):
        """Test linear interpolation (35cc is halfway between 20cc and 50cc)."""
        # 50cc = 20Gy, 20cc = 30Gy. 
        # 35cc is exactly halfway (15cc from each).
        # Expected Dose: Halfway between 20Gy and 30Gy = 25Gy.
        dose = get_dose_at_volume(self.mock_structure_data, 35.0)
        self.assertAlmostEqual(dose, 25.0, places=2)

    def test_dose_at_volume_out_of_bounds(self):
        """Test volume larger than total organ (should be 0 Gy)."""
        dose = get_dose_at_volume(self.mock_structure_data, 150.0)
        self.assertEqual(dose, 0.0)

    def test_dose_at_percent(self):
        """Test D50% (50cc). Should be 20 Gy."""
        dose = get_dose_at_percent_volume(self.mock_structure_data, 50.0)
        self.assertAlmostEqual(dose, 20.0, places=2)

    # --- 2. TEST TPS VALIDATION LOGIC ---
    def test_validation_flagging(self):
        """Test that a >5Gy difference triggers a warning."""
        
        # Scenario: DICOM calculates 80 Gy, TPS text says 86 Gy (Diff = 6)
        dicom_results = {
            "Bladder": {"d2cc_gy_per_fraction": 80.0}
        }
        text_results = {
            "Bladder": {"d2cc_gy_per_fraction": 86.0}
        }
        
        warnings = validate_tps_import(
            dicom_results, text_results, 
            dicom_patient_id="123", 
            text_metadata={"patient_id": "123"},
            tolerance_gy=5.0
        )
        
        self.assertEqual(len(warnings), 1)
        self.assertIn("QA Mismatch", warnings[0])
        self.assertIn("Diff: 6.00", warnings[0])

    def test_validation_passing(self):
        """Test that a small difference (2 Gy) passes silently."""
        dicom_results = {"Bladder": {"d2cc_gy_per_fraction": 80.0}}
        text_results = {"Bladder": {"d2cc_gy_per_fraction": 82.0}}
        
        warnings = validate_tps_import(
            dicom_results, text_results, 
            dicom_patient_id="123", text_metadata={"patient_id": "123"}
        )
        self.assertEqual(len(warnings), 0)

    # --- 3. TEST 3D COORDINATE LOOKUP ---
    def test_voxel_lookup_simple(self):
        """
        Test transforming a point (x,y,z) to a dose value.
        Origin at (0,0,0), Spacing 1mm. Point at (2,2,2).
        """
        # Create a simple 5x5x5 dose grid with value 10.0 everywhere
        dose_grid = np.full((5, 5, 5), 10.0)
        
        # Define Grid Geometry
        origin = (0.0, 0.0, 0.0)
        spacing = (1.0, 1.0) # x, y
        z_offsets = [0.0, 1.0, 2.0, 3.0, 4.0] # z spacing = 1.0
        dose_scaling = 1.0
        
        # Test Point at (2, 2, 2) -> Should hit index [2,2,2]
        dose = get_dose_at_point(
            dose_grid, dose_scaling, origin, spacing, z_offsets, 
            point_coordinates=[2.0, 2.0, 2.0]
        )
        
        self.assertEqual(dose, 10.0)

if __name__ == '__main__':
    print("Running Hybrid Features Validation Suite...")
    unittest.main()