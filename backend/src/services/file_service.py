import os
from pathlib import Path
from datetime import datetime
import shutil

class FileService:
    def __init__(self, base_dir_name="Patient Data"):
        # Base directory relative to the project root (assuming backend/src/services/file_service.py)
        # parents[0]=services, parents[1]=src, parents[2]=backend, parents[3]=ROOT
        self.project_root = Path(__file__).resolve().parents[3]
        self.base_dir = self.project_root / base_dir_name
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, patient_id, plan_name, timestamp=None):
        """
        Constructs the directory path: Patient Data / Patient_ID / Plan_Name / Timestamp
        """
        # Sanitize inputs
        p_id = "".join([c for c in str(patient_id) if c.isalnum() or c in (' ', '-', '_')]).strip()
        p_name = "".join([c for c in str(plan_name) if c.isalnum() or c in (' ', '-', '_')]).strip()
        
        if not p_id: p_id = "Unknown_Patient"
        if not p_name: p_name = "Unknown_Plan"
        
        if timestamp is None:
            timestamp = datetime.now()
        
        ts_str = timestamp.strftime('%Y-%m-%d_%H-%M-%S')
        
        session_dir = self.base_dir / p_id / p_name / ts_str
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def save_file(self, file_content, filename, patient_id, plan_name, subfolder=None, timestamp=None):
        """
        Saves a file content (bytes) to the structured directory.
        Optional 'subfolder' to group files (e.g. 'DICOM', 'Reports', 'Excels').
        """
        session_dir = self._get_session_dir(patient_id, plan_name, timestamp)
        
        if subfolder:
            target_dir = session_dir / subfolder
            target_dir.mkdir(exist_ok=True)
        else:
            target_dir = session_dir
            
        file_path = target_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(file_content)
            
        return str(file_path)

    def save_derived_file(self, file_content, filename, patient_id, plan_name, timestamp=None):
        """Helper for artifacts (Reports, Sheets)"""
        return self.save_file(file_content, filename, patient_id, plan_name, subfolder="Generated", timestamp=timestamp)

    def save_input_file(self, file_content, filename, patient_id, plan_name, timestamp=None):
        """Helper for inputs (DICOMs, Schedules)"""
        return self.save_file(file_content, filename, patient_id, plan_name, subfolder="Input", timestamp=timestamp)
