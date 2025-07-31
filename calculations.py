import numpy as np
import pydicom
from skimage import draw

# This file will contain the logic for dose-volume calculations.

def transform_contour_to_dose_grid(contour_data, image_position, pixel_spacing, image_orientation):
    """Transforms contour data from the patient coordinate system to the dose grid's voxel coordinates using a full affine transformation."""
    # Extract the row and column direction vectors from the image orientation
    row_vec = np.array(image_orientation[:3])
    col_vec = np.array(image_orientation[3:])
    # The slice direction vector is the cross product of the row and column vectors
    slice_vec = np.cross(row_vec, col_vec)

    # Create the rotation matrix
    rotation_matrix = np.array([row_vec, col_vec, slice_vec]).T

    # Create the full affine transformation matrix
    affine_matrix = np.eye(4)
    affine_matrix[:3, :3] = rotation_matrix
    affine_matrix[:3, 3] = image_position

    # Invert the matrix to go from patient coordinates to voxel coordinates
    inv_affine_matrix = np.linalg.inv(affine_matrix)

    transformed_contours = []
    for contour in contour_data:
        points = np.array(contour).reshape((-1, 3))
        # Add a fourth dimension (w=1) to the points for the affine transformation
        points_homogeneous = np.hstack([points, np.ones((points.shape[0], 1))])
        # Apply the inverse affine transformation
        transformed_points_homogeneous = np.dot(inv_affine_matrix, points_homogeneous.T).T
        # Scale by pixel spacing
        transformed_points = transformed_points_homogeneous[:, :3]
        transformed_points[:, 0] /= pixel_spacing[0]
        transformed_points[:, 1] /= pixel_spacing[1]
        transformed_contours.append(transformed_points)
    return transformed_contours

def create_mask_from_contours(transformed_contours, dose_grid_shape, grid_frame_offset_vector):
    """Creates a 3D boolean mask from transformed contour data."""
    z_offsets = np.array(grid_frame_offset_vector, dtype=float)
    mask = np.zeros(dose_grid_shape, dtype=bool)
    for contour_points in transformed_contours:
        x_voxels = contour_points[:, 0]
        y_voxels = contour_points[:, 1]
        z_mm = contour_points[0, 2]
        z_slice_index = (np.abs(z_offsets - z_mm)).argmin()
        if z_slice_index >= dose_grid_shape[0]:
            continue
        slice_shape = (dose_grid_shape[1], dose_grid_shape[2])
        y_voxels_clipped = np.clip(y_voxels, 0, slice_shape[0] - 1)
        x_voxels_clipped = np.clip(x_voxels, 0, slice_shape[1] - 1)
        rr, cc = draw.polygon(y_voxels_clipped, x_voxels_clipped, shape=slice_shape)
        mask[z_slice_index, rr, cc] = True
    return mask

def get_dvh(structure_data, dose_grid, dose_scaling, image_position, pixel_spacing, grid_frame_offset_vector, number_of_fractions, image_orientation):
    """Calculates the Dose-Volume Histogram (DVH) for each structure."""
    dvh_results = {}
    dose_grid_shape = dose_grid.shape
    slice_thickness = np.abs(grid_frame_offset_vector[1] - grid_frame_offset_vector[0])
    voxel_volume_cc = (pixel_spacing[0] * pixel_spacing[1] * slice_thickness) / 1000.0

    for name, data in structure_data.items():
        transformed_contours = transform_contour_to_dose_grid(data["ContourData"], image_position, pixel_spacing, image_orientation)
        mask = create_mask_from_contours(transformed_contours, dose_grid_shape, grid_frame_offset_vector)
        
        if not np.any(mask):
            continue

        organ_doses_gy_per_fraction = dose_grid[mask] * dose_scaling
        organ_volume_cc = len(organ_doses_gy_per_fraction) * voxel_volume_cc

        d2cc_gy_per_fraction = 0
        if organ_volume_cc >= 2.0:
            voxels_for_2cc = int(round(2.0 / voxel_volume_cc))
            sorted_doses = np.sort(organ_doses_gy_per_fraction)[::-1]
            d2cc_gy_per_fraction = sorted_doses[voxels_for_2cc - 1]

        total_d2cc_gy = d2cc_gy_per_fraction * number_of_fractions

        dvh_results[name] = {
            "volume_cc": round(organ_volume_cc, 2),
            "d2cc_gy_per_fraction": round(d2cc_gy_per_fraction, 2),
            "total_d2cc_gy": round(total_d2cc_gy, 2)
        }

    return dvh_results