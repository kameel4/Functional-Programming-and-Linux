from astropy.io import fits
import numpy as np
import tifffile
import sys

def fits_to_tiff(src, dst):
    data = fits.getdata(src)
    data = np.nan_to_num(data)

    # растяжка по перцентилям
    vmin, vmax = np.percentile(data, (1, 99))  
    data = np.clip(data, vmin, vmax)

    data = (data - vmin) / (vmax - vmin)  # нормализация 0..1
    data = (data * 65535).astype(np.uint16)
    tifffile.imwrite(dst, data)

if __name__ == "__main__":
    for i in range(1, 10):
        src = f'hubble{i}.fits'
        dst = f'hubble{i}.tiff'
        fits_to_tiff(src, dst)
