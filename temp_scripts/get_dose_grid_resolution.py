import sys
sys.path.append('C:/Users/echorniak/GIT/BrachyD2ccEval')
from src.dicom_parser import get_dose_data, find_dicom_file

dose_dir = 'C:/Users/echorniak/GIT/BrachyD2ccEval/sample_data/Jane Doe/DOE^JANE_ANON93124_RTDOSE_2025-07-11_122839_HDR_Dose.for.30mm.Cylinder_n1__00000'
dose_file = find_dicom_file(dose_dir)

_, _, _, pixel_spacing, grid_frame_offset_vector, _ = get_dose_data(dose_file)

print(f'Pixel Spacing: {pixel_spacing}')
print(f'Grid Frame Offset Vector: {grid_frame_offset_vector}')