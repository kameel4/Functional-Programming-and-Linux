import numpy as np
import tifffile
from PIL import Image

def normalize_to_uint8(array):
    """Нормализация данных в диапазон 0..255"""
    array = array.astype(np.float32)
    # Обрезаем крайние значения (как авто-контраст)
    low, high = np.percentile(array, (0.5, 99.5))
    array = np.clip((array - low) / (high - low), 0, 1)
    return (array * 255).astype(np.uint8)

def tiff_to_jpeg(input_path, output_path):
    img = tifffile.imread(input_path)

    if img.ndim == 2:
        # Ч/б TIFF → Ч/б JPEG
        norm = normalize_to_uint8(img)
        Image.fromarray(norm, mode="L").save(output_path, quality=95)
    elif img.ndim == 3:
        if img.shape[0] in [3, 4]:  
            # Формат (каналы, высота, ширина) → транспонируем
            img = np.transpose(img, (1, 2, 0))
        # Нормализуем каждый канал
        norm = np.stack([normalize_to_uint8(img[..., i]) for i in range(img.shape[2])], axis=-1)
        Image.fromarray(norm).save(output_path, quality=95)
    else:
        raise ValueError(f"Неожиданная форма массива {img.shape}")

# пример использования
tiff_to_jpeg("hubble4.tiff", "hubble4.jpg")
