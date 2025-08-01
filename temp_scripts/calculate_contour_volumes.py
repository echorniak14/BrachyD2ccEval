import pydicom
from pathlib import Path
import numpy as np
from skimage.draw import polygon

def get_structure_data(rtstruct_file):
    """Extracts ROI names and contour data from an RTSTRUCT file."""
    if not rtstruct_file:
        return {}
    ds = pydicom.dcmread(rtstruct_file)
    structures = {}
    for roi_contour, structure_set_roi in zip(ds.ROIContourSequence, ds.StructureSetROISequence):
        structures[structure_set_roi.ROIName] = {
            "ROINumber": structure_set_roi.ROINumber,
            "ContourData": [contour.ContourData for contour in roi_contour.ContourSequence]
        }
    return structures

def get_dose_data(rtdose_file):
    """Extracts dose grid, scaling factor, and position data from an RTDOSE file."""
    if not rtdose_file:
        return None, None, None, None, None, None
    ds = pydicom.dcmread(rtdose_file)
    return ds.pixel_array, ds.DoseGridScaling, ds.ImagePositionPatient, ds.PixelSpacing, ds.GridFrameOffsetVector, ds.ImageOrientationPatient

def calculate_contour_volumes(rtstruct_file, rtdose_file):
    """Calculates the volume of each contour in an RTSTRUCT file."""
    structure_data = get_structure_data(rtstruct_file)
    _, _, image_position, pixel_spacing, _, _ = get_dose_data(rtdose_file)

    if not structure_data:
        return {}

    volumes = {}
    for name, data in structure_data.items():
        if name != "Sigmoid":
            continue

        print(f"\n--- Debugging Structure: {name} ---")

        if not data["ContourData"] or not data["ContourData"][0]:
            continue

        # Group contours by their Z coordinate
        slices_by_z = {}
        for contour_slice in data["ContourData"]:
            if contour_slice:
                points = np.array(contour_slice).reshape((-1, 3))
                z = round(np.mean(points[:, 2]), 4) # Round to handle floating point inaccuracies
                if z not in slices_by_z:
                    slices_by_z[z] = []
                slices_by_z[z].append(points)

        sorted_z = sorted(slices_by_z.keys())

        total_volume_cc = 0
        for i in range(len(sorted_z) - 1):
            z1 = sorted_z[i]
            z2 = sorted_z[i+1]

            def get_total_area(z_level_points_list):
                total_area = 0
                for slice_points in z_level_points_list:
                    # Shoelace formula for polygon area
                    x = slice_points[:, 0]
                    y = slice_points[:, 1]
                    area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
                    total_area += area / 100 # convert from mm^2 to cm^2
                return total_area

            area1 = get_total_area(slices_by_z[z1])
            area2 = get_total_area(slices_by_z[z2])
            
            distance_cm = abs(z1 - z2) / 10.0
            slab_volume = (area1 + area2) / 2.0 * distance_cm
            total_volume_cc += slab_volume

        volumes[name] = total_volume_cc

        volumes[name] = total_volume_cc

    return volumes

    return volumes

def main():
    rtstruct_file = r"C:\Users\echorniak\GIT\BrachyD2ccEval\DOE^JANE_ANON93124_RTst_2025-07-11_122839_HDR_30mm.Cyl_n1__00000\2.16.840.1.114362.1.12177026.23360333229.711517051.371.3.dcm"
    rtdose_file = r"C:\Users\echorniak\GIT\BrachyD2ccEval\DOE^JANE_ANON93124_RTDOSE_2025-07-11_122839_HDR_Dose.for.30mm.Cylinder_n1__00000\2.16.840.1.114362.1.12177026.23360333229.711517226.314.193.dcm"

    if not Path(rtstruct_file).is_file() or not Path(rtdose_file).is_file():
        print("Error: One or both DICOM files not found.")
        return

    volumes = calculate_contour_volumes(rtstruct_file, rtdose_file)

    if volumes:
        print("Contour Volumes (cc):")
        for name, volume in volumes.items():
            print(f"  {name}: {volume:.4f}")
    else:
        print("Could not calculate contour volumes.")

if __name__ == "__main__":
    main()
