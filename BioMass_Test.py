import numpy as np
import rasterio
import matplotlib.pyplot as plt
from rasterio.plot import reshape_as_image
import argparse
import os
import gdown
from zipfile import ZipFile


def download_images():
    url_image = 'https://drive.google.com/file/d/1ICvruBHE-x2V2qeYRErmZUsyNrGV-ZjF/view?usp=sharing'
    test_images_zip = 'Testimages.zip'
    
    print("Downloading the images...")
    gdown.download(url_image, test_images_zip, quiet=False, fuzzy=True)
    
    print("Extracting the images...")
    with ZipFile(test_images_zip, 'r') as zip_ref:
        zip_ref.extractall('.')

    # Remove after finished extraction    
    os.remove(test_images_zip) 
    print("Images extracted successfully!")


# Load geo-referenced single-band image(Red and NIR band)
def load_Sentinel_2_geo(path):
    with rasterio.open(path) as src:
        raster_data = src.read(1).astype(np.float32)
        profile = src.profile
        transform = src.transform
        gsd_x = abs(transform[0])
        gsd_y = abs(transform[4])
    
    return raster_data, profile, (gsd_x, gsd_y)

# Load TCI (3bands) 
def load_tci_image(path):
    with rasterio.open(path) as src:
        tci_data = src.read()
        profile = src.profile
        transform = src.transform
    return reshape_as_image(tci_data), profile

# Slicing or entire image to estimate Biomass
def crop_quarter(array, quarter):
    h, w = array.shape[:2]
  
    half_h, half_w = h // 2, w // 2

    if quarter == 0:
        return array
    elif quarter == 1:
        return array[:half_h, :half_w]
    elif quarter == 2:
        return array[:half_h, half_w:]
    elif quarter == 3:
        return array[half_h:, :half_w]
    elif quarter == 4:
        return array[half_h:, half_w:]
    else:
        raise ValueError("Quarter must be 0 (entire image), 1, 2, 3, or 4")


# Compute Normalized Difference Vegetation Index (NDVI)
def compute_ndvi(red, infrared):

    ndvi = (infrared - red) / (infrared + red + 1e-6)
    return np.clip(ndvi, -1, 1)


def extract_nvdi_mask(ndvi, threshold):
    
    return (ndvi > threshold).astype(np.uint8)

def estimate_biomass(NDVI, mask, pixel_size_x, pixel_size_y):

    height, width = NDVI.shape

    forest_pixels = np.sum(mask)

    # m²/ pixel
    area_of_one_pixel = (pixel_size_x*pixel_size_y)     

    # Forest area calculation (m² to km2)
    forest_area_km2 = (forest_pixels * area_of_one_pixel)/(1000*1000)  

    # slope* NDVI + intercept
    biomass_density = 2.779 * NDVI - 0.383              
    
    biomass_density = np.clip(biomass_density, 0, None) 

    # tons/pixel = (tons/ha) × (ha/pixel) , 1 hectare (ha) = 10,000 square meters (m²)
    biomass_map = biomass_density * (area_of_one_pixel/10000) * mask  

    # total tons
    total_biomass_tons = np.sum(biomass_map)                          

    return {
        "area_of_one_pixel": int(area_of_one_pixel),
        "area_of_sliced_tile":[width*pixel_size_x, height*pixel_size_y, width*pixel_size_x*height*pixel_size_y],
        "forest_area_km²": forest_area_km2,
        "biomass_tons": total_biomass_tons,
        "biomass_map": biomass_map
    }

def visualize_biomass(tci_image, red, infrared, ndvi, biomass_raster, quarter_no, stats, save_img):


    tile_no = "Full Raster" if quarter_no == 0 else f"Quarter {quarter_no}"

    print ("\n Tested tile >>> ", tile_no)


    fig, axs = plt.subplots(2, 2, figsize=(12, 12))
    fig.subplots_adjust(bottom=0.18)  

    # TCI Image
    im0 = axs[0, 0].imshow(tci_image)
    axs[0, 0].set_title(f"TCI Image - {tile_no}")
    axs[0, 0].axis('off')
    fig.colorbar(im0, ax=axs[0, 0], fraction=0.046, pad=0.04).set_label("RGB", rotation=270, labelpad=10)

    # NIR Band
    im1 = axs[0, 1].imshow(infrared, cmap='RdYlGn')
    axs[0, 1].set_title(f"NIR Band - {tile_no}")
    axs[0, 1].axis('off')
    fig.colorbar(im1, ax=axs[0, 1], fraction=0.046, pad=0.04).set_label("NIR", rotation=270, labelpad=10)

    # NDVI
    im2 = axs[1, 0].imshow(ndvi, cmap='RdYlGn', vmin=-1, vmax=1)
    axs[1, 0].set_title("NDVI")
    axs[1, 0].axis('off')
    fig.colorbar(im2, ax=axs[1, 0], fraction=0.046, pad=0.04).set_label("NDVI", rotation=270, labelpad=10)

    # Biomass
    im3 = axs[1, 1].imshow(biomass_raster, cmap="Greens")
    axs[1, 1].set_title("Estimated Biomass (tons/pixel)")
    axs[1, 1].axis('off')
    fig.colorbar(im3, ax=axs[1, 1], fraction=0.046, pad=0.04).set_label("Tons", rotation=270, labelpad=10)


    satistic_data = [
        ["Area_of_one_pixel", f"{stats['area_of_one_pixel']:,} m²"],
        ["Area_of_sliced_tile", f"{stats['area_of_sliced_tile'][0]/1000} km * {stats['area_of_sliced_tile'][1]/1000} km = {stats['area_of_sliced_tile'][2]/1000} km²"],
        ["Detected Forest Area", f"{stats['forest_area_km²']:.2f} km²"],
        ["Total Biomass", f"{stats['biomass_tons']:.2f} tons"]
    ]

    print(f"\n Biomass Calculation  >>> \n ")
    print(satistic_data)
 
    table_ax = fig.add_axes([0.2, 0.04, 0.65, 0.1])  
    table_ax.axis("off")
    table = table_ax.table(cellText=satistic_data,
                           colLabels=["Statistic", "Values"],
                           cellLoc="left",
                           loc="center")
    table.scale(1, 2)
    table.auto_set_font_size(False)
    table.set_fontsize(12)

    plt.savefig(save_img)
    plt.show()


def run_biomass(tci_path, red_path, nir_path, save_img, threshold, quarter):
    tci_image, _ = load_tci_image(tci_path)
    tci_crop = crop_quarter(tci_image, quarter)

    red, profile, (pixel_size_x, pixel_size_y) = load_Sentinel_2_geo(red_path)
    print(f"\n Pixel Size  >>> X: {pixel_size_x} meter,  Y: {pixel_size_y} meter")

    nir, _, _ = load_Sentinel_2_geo(nir_path)
    red_crop = crop_quarter(red, quarter)
    nir_crop = crop_quarter(nir, quarter)

    ndvi = compute_ndvi(red_crop, nir_crop)
    ndvi_mask = extract_nvdi_mask(ndvi, threshold)
    stats = estimate_biomass(ndvi, ndvi_mask, pixel_size_x, pixel_size_y)

    visualize_biomass(tci_crop, red_crop, nir_crop, ndvi, stats["biomass_map"], quarter,stats, save_img)


if __name__ == "__main__":


    parser = argparse.ArgumentParser(description="Estimate biomass from Sentinel-2 imagery.")
    parser.add_argument("--tci", type=str, required=True, help="Path to TCI (3-band RGB) image")
    parser.add_argument("--red", type=str, required=True, help="Path to Red band (Band 4) image")
    parser.add_argument("--nir", type=str, required=True, help="Path to NIR band (Band 8) image")
    parser.add_argument("--save-img", type=str, default="result.png", help="Path to save result image")
    parser.add_argument("--quarter", type=int, default=0, choices=[0, 1, 2, 3, 4],
                        help="Quarter to slice (0 = entire image, 1~4 for sliced tiles )")
    parser.add_argument("--threshold", type=float, default=0.4,
                        help="NDVI threshold for Forest region masking ")
    

    args = parser.parse_args()

    download_images() 

    run_biomass(args.tci, args.red, args.nir, save_img=args.save_img, quarter=args.quarter, threshold=args.threshold)

