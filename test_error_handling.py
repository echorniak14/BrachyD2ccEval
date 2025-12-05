import unittest
import sys
import os
from unittest.mock import MagicMock

# Path fix to find your src folder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from validators import (
    validate_patient_ids, 
    validate_file_completeness, 
    check_plan_time, 
    validate_channel_mapping,
    check_dwell_times,
    check_fraction_count
)

class TestEchoSafetyChecks(unittest.TestCase):

    def create_mock_dicom(self, patient_id="12345"):
        """Helper to create a fake DICOM object"""
        ds = MagicMock()
        ds.PatientID = patient_id
        return ds

    # --- 1. PATIENT ID CHECKS ---
    def test_mrn_mismatch(self):
        """Test Case: Plan and Dose have different MRNs."""
        ds_plan = self.create_mock_dicom("JOHN_DOE")
        ds_dose = self.create_mock_dicom("JANE_DOE")
        
        errors = validate_patient_ids([ds_plan, ds_dose])
        self.assertTrue(len(errors) > 0)
        self.assertIn("Mismatch", errors[0])

    def test_json_history_mismatch(self):
        """Test Case: DICOM matches, but Historical JSON is different."""
        ds_plan = self.create_mock_dicom("JOHN_DOE")
        history = {"patient_mrn": "WRONG_PATIENT"}
        
        errors = validate_patient_ids([ds_plan], history)
        self.assertTrue(len(errors) > 0)
        self.assertIn("History Mismatch", errors[0])

    # --- 2. FILE COMPLETENESS ---
    def test_missing_files(self):
        """Test Case: User forgot RT DOSE."""
        uploaded_types = ['RTPLAN', 'RTSTRUCT'] # Missing RTDOSE
        errors = validate_file_completeness(uploaded_types)
        self.assertTrue(len(errors) > 0)
        self.assertIn("RTDOSE", errors[0])

    def test_duplicate_files(self):
        """Test Case: User uploaded two RT Plans."""
        uploaded_types = ['RTPLAN', 'RTPLAN', 'RTSTRUCT', 'RTDOSE']
        errors = validate_file_completeness(uploaded_types)
        self.assertTrue(len(errors) > 0)
        self.assertIn("Multiple files", errors[0])

    # --- 3. PLAN CHECKS ---
    def test_plan_time_warning(self):
        """Test Case: Plan exported at 8PM (20:00)."""
        warnings = check_plan_time("200000.000")
        self.assertTrue(len(warnings) > 0)
        self.assertIn("outside standard hours", warnings[0])

    def test_plan_time_ok(self):
        """Test Case: Plan exported at 10AM."""
        warnings = check_plan_time("100000.000")
        self.assertEqual(len(warnings), 0)

    # --- 4. CATHETER MAPPING ---
    def test_cylinder_mapping_fail(self):
        """Test Case: Cylinder map Cath 1 -> Channel 1 (Should be 5)."""
        mapping = [{'channel_number': 1, 'transfer_tube_number': 1}]
        warnings = validate_channel_mapping(mapping, "Cylinder")
        self.assertTrue(len(warnings) > 0)
        self.assertIn("Channel 5", warnings[0])

    def test_tandem_ovoid_pass(self):
        """Test Case: T&O Correct Mapping (1->1, 2->3, 3->5)."""
        mapping = [
            {'channel_number': 1, 'transfer_tube_number': 1},
            {'channel_number': 2, 'transfer_tube_number': 3},
            {'channel_number': 3, 'transfer_tube_number': 5}
        ]
        warnings = validate_channel_mapping(mapping, "Tandem and Ovoid")
        self.assertEqual(len(warnings), 0)

    # --- 5. DWELL TIMES ---
    def test_short_dwell_time(self):
        """Test Case: Dwell time is 0.5 seconds (Dangerous)."""
        dwells = [10.0, 5.0, 0.5, 10.0]
        warnings = check_dwell_times(dwells)
        self.assertTrue(len(warnings) > 0)
        self.assertIn("small dwell time", warnings[0])

    def test_zero_dwell_time(self):
        """Test Case: Dwell time is 0.0 seconds (Allowed)."""
        dwells = [10.0, 0.0, 10.0]
        warnings = check_dwell_times(dwells)
        self.assertEqual(len(warnings), 0)

    # --- 6. FRACTION COUNT ---
    def test_fraction_mismatch(self):
        """Test Case: Plan says 5 fractions, User calculates for 3."""
        warnings = check_fraction_count(planned=5, calculated=3)
        self.assertTrue(len(warnings) > 0)
        self.assertIn("calculation uses", warnings[0])

if __name__ == '__main__':
    print("Running Safety Validation Suite for ECHO...")
    unittest.main()