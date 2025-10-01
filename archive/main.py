import OpenEXR, Imath
import numpy as np
import cv2
import os

# --- Классы яркости ---
classes = [
    (0.00, 0.10, (255, 200, 150)),  # Очень тусклые
    (0.10, 0.25, (0, 255, 0)),      # Тусклые
    (0.25, 0.40, (0, 255, 255)),    # Средние
    (0.40, 0.60, (0, 165, 255)),    # Яркие
    (0.60, 0.80, (0, 0, 255)),      # Очень яркие
    (0.80, 1.00, (200, 0, 200)),    # Сверхяркие
]

def list_files(path="."):
    print(f"Содержимое директории: {os.path.abspath(path)}\n")
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        if os.path.isfile(full_path):
            print(f"[FILE] {name}")
        elif os.path.isdir(full_path):
            print(f"[DIR ] {name}")
        else:
            print(f"[????] {name}")

def read_exr_gray(path):
    """Читает EXR как grayscale (берем канал R)"""
    exr_file = OpenEXR.InputFile(path)
    dw = exr_file.header()['dataWindow']
    size = (dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1)

    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    # читаем только канал R (если у тебя RGB, то этого достаточно)
    raw = exr_file.channel('R', pt)

    data = np.frombuffer(raw, dtype=np.float32)
    img = np.reshape(data, (size[1], size[0]))
    return img


def classify_and_draw(exr_path, out_path="classified.png"):
    # 1. Загружаем EXR
    img = read_exr_gray(exr_path)

    # 2. Нормализуем в диапазон [0,1]
    norm = cv2.normalize(img, None, 0, 1, cv2.NORM_MINMAX)

    # 3. В 8-бит для отображения
    norm_8u = (norm * 255).astype(np.uint8)
    canvas = cv2.cvtColor(norm_8u, cv2.COLOR_GRAY2BGR)

    # 4. Обрабатываем классы
    for idx, (low, high, color) in enumerate(classes, start=1):
        # Маска по диапазону
        mask = cv2.inRange(norm, low, high)

        # Контуры объектов
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Рисуем контуры
        cv2.drawContours(canvas, contours, -1, color, 1)

        # Подписываем номер класса в центре каждого объекта
        for cnt in contours:
            M = cv2.moments(cnt)
            if M["m00"] > 0:  # чтобы не делить на ноль
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                cv2.putText(canvas, str(idx), (cx, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

    # 5. Сохраняем результат
    cv2.imwrite(out_path, canvas)
    print(f" Результат сохранён в {out_path}")


if __name__ == "__main__":
    list_files()
    # classify_and_draw("stars.exr", "classified.png")
