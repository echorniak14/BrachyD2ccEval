import pydicom
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from skimage import measure
import os

# Function to find DICOM files in a directory
def find_dicom_files(directory):
    dicom_files = {"RTDOSE": None, "RTSTRUCT": None}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.dcm'):
                file_path = os.path.join(root, file)
                try:
                    ds = pydicom.dcmread(file_path, force=True)
                    modality = ds.Modality
                    if modality == "RTDOSE":
                        dicom_files["RTDOSE"] = file_path
                    elif modality == "RTSTRUCT":
                        dicom_files["RTSTRUCT"] = file_path
                except Exception as e:
                    print(f"Skipping file {file_path}: {e}")
    return dicom_files

# Load DICOM files
dicom_dir = "C:\\Users\\echorniak\\GIT\\BrachyD2ccEval"
dicom_files = find_dicom_files(dicom_dir)

if not dicom_files["RTDOSE"] or not dicom_files["RTSTRUCT"]:
    print("Error: RTDOSE or RTSTRUCT file not found.")
    exit()

rtdose = pydicom.dcmread(dicom_files["RTDOSE"])
rtstruct = pydicom.dcmread(dicom_files["RTSTRUCT"])

# Get dose data
dose_grid = rtdose.pixel_array * rtdose.DoseGridScaling
image_pos_patient = rtdose.ImagePositionPatient
pixel_spacing = rtdose.PixelSpacing # This is (row_spacing, col_spacing) -> (y, x)
grid_frame_offset = rtdose.GridFrameOffsetVector

# Create a 3D plot
fig = plt.figure(figsize=(12, 12))
ax = fig.add_subplot(111, projection='3d')

# Define colors for structures
structure_colors = {
    "Bladder": "yellow",
    "Rectum": "brown",
    "Sigmoid": "purple",
    "Bowel": "orange"
}

# Plot structures
for roi_contour, roi_info in zip(rtstruct.ROIContourSequence, rtstruct.StructureSetROISequence):
    roi_name = roi_info.ROIName
    color = structure_colors.get(roi_name, "gray") # Default to gray if not specified
    if hasattr(roi_contour, 'ContourSequence'):
        for contour in roi_contour.ContourSequence:
            contour_data = np.array(contour.ContourData).reshape(-1, 3)
            # Check if contour is closed
            if np.all(contour_data[0] == contour_data[-1]):
                x, y, z = contour_data.T
                verts = [list(zip(x, y, z))]
                ax.add_collection3d(Poly3DCollection(verts, facecolors=color, linewidths=1, alpha=0.3))
            else: # If not closed, just plot the line
                ax.plot(contour_data[:,0], contour_data[:,1], contour_data[:,2], color=color, alpha=0.5)

# Plot 500 cGy (5 Gy) isodose surface
iso_dose_level = 5.0

# The dose grid from pydicom is indexed (z, y, x).
# We need to calculate the spacing in each of these dimensions.
try:
    z_spacing = np.abs(grid_frame_offset[1] - grid_frame_offset[0])
    y_spacing = pixel_spacing[0]
    x_spacing = pixel_spacing[1]
    dose_spacing = (z_spacing, y_spacing, x_spacing)

    # Generate the isosurface. The output verts are scaled by the spacing.
    # The coordinate order of verts will be (z, y, x) corresponding to the dose_grid indexing.
    verts, faces, _, _ = measure.marching_cubes(dose_grid, level=iso_dose_level, spacing=dose_spacing)

    # The returned vertices are in a (z, y, x) coordinate system.
    # We need to swap them to (x, y, z) for plotting and then add the grid origin.
    verts_patient_coord = verts[:, [2, 1, 0]] + image_pos_patient

    # Create the mesh
    mesh = Poly3DCollection(verts_patient_coord[faces], alpha=0.2, facecolor='black', edgecolor='none')
    ax.add_collection3d(mesh)

except Exception as e:
    print(f"Could not generate isodose surface: {e}")
    print(f"This may be because the isodose level ({iso_dose_level} Gy) is not found within the dose grid, or the grid spacing is non-uniform.")

# Set labels and title
ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.set_zlabel('Z (mm)')
ax.set_title('3D Visualization of Structures and 5 Gy Isodose Surface')

# Set aspect ratio to be equal to avoid distortion
ax.set_box_aspect([1,1,1]) # For modern matplotlib
try:
    ax.set_aspect('equal')
except NotImplementedError:
    pass # Older matplotlib might not support this for 3d

# Set view
ax.view_init(elev=30, azim=-135)

plt.show()