import sys, os, threading
import numpy as np
import tifffile
from PIL import Image
import cv2
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLabel, 
                             QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
                             QSpinBox, QGroupBox, QFormLayout)
from PyQt5.QtGui import QPixmap, QImage, QPainter

# Классификация астрономических объектов
# Правила классификации: (яркость_мин, яркость_макс, площадь_мин, площадь_макс, название, цвет)
ASTRO_CLASSES = [
    # Звезды - яркие, компактные объекты
    (0.60, 1.00, 100, 500, "Star", (255, 255, 0)),           # Яркая звезда
    (0.40, 0.60, 100, 300, "Dim Star", (200, 200, 100)),    # Тусклая звезда
    
    # Ядра галактик - очень яркие, средние по размеру
    (0.70, 1.00, 500, 3000, "Galaxy Core", (255, 0, 255)),  # Ядро галактики
    
    # Галактики - средняя яркость, крупные объекты
    (0.25, 0.60, 3000, 500000, "Galaxy", (0, 255, 255)),     # Галактика
    (0.15, 0.40, 5000, 3000000, "Faint Galaxy", (0, 200, 200)), # Тусклая галактика
    
    # Туманности - тусклые, большие, рассеянные объекты
    (0.10, 0.40, 5000, float(), "Nebula", (255, 100, 255)),   # Туманность
    (0.05, 0.20, 10000, float('inf'), "Large Nebula", (200, 50, 200)), # Большая туманность
    
    # Шаровые скопления - яркие, средне-крупные
    (0.40, 0.70, 2000, 8000, "Globular Cluster", (0, 255, 0)), # Шаровое скопление
    
    # Рассеянные скопления - средняя яркость, средний размер
    (0.30, 0.60, 1500, 6000, "Open Cluster", (100, 255, 100)), # Рассеянное скопление
    
    # Квазары/активные ядра - очень яркие точечные источники
    (0.80, 1.00, 100, 400, "Quasar/AGN", (255, 0, 0)),      # Квазар
    
    # Астероиды/кометы - тусклые, маленькие
    (0.10, 0.35, 100, 1000, "Asteroid/Comet", (150, 150, 150)), # Астероид/комета
    
    # Неопознанные слабые объекты
    (0.00, 0.15, 100, 5000, "Faint Object", (100, 100, 100)),  # Слабый объект
]

MIN_CONTOUR_AREA = 100  # Минимальная площадь контура

def normalize_float01(arr):
    a = arr.astype(np.float32)
    bg = np.median(a)
    a = a - bg
    a[a < 0] = 0
    high = np.percentile(a, 99.5)
    if high < 1e-6:
        high = a.max() if a.max() > 0 else 1.0
    a = np.clip(a / high, 0.0, 1.0)
    return a

def classify_astronomical_object(brightness, area):
    """
    Классифицирует астрономический объект по яркости и площади
    
    Args:
        brightness: средняя яркость объекта (0.0-1.0)
        area: площадь контура в пикселях
    
    Returns:
        tuple: (название_класса, цвет_BGR)
    """
    # Проходим по всем правилам классификации
    if area > 30000:
        return "Large Nebula", (200, 50, 200)
    
    for bright_min, bright_max, area_min, area_max, name, color in ASTRO_CLASSES:
        if bright_min <= brightness < bright_max and area_min <= area < area_max:
            return name, color
    
    # Если не подошло ни одно правило - неизвестный объект
    return "Unknown Object", (128, 128, 128)

def get_contour_brightness(gray_norm, contour):
    """
    Вычисляет среднюю яркость внутри контура
    
    Args:
        gray_norm: нормализованное изображение в градациях серого
        contour: контур объекта
    
    Returns:
        float: средняя яркость (0.0-1.0)
    """
    mask = np.zeros(gray_norm.shape, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    mean_val = cv2.mean(gray_norm, mask=mask)[0]
    return mean_val

def tiff_to_jpeg(input_path, output_path):
    img = cv2.imread(input_path)
    def _normalize_to_uint8(array):
        arr = array.astype(np.float32)
        low, high = np.percentile(arr, (0.5, 99.5))
        if high - low <= 1e-6: high = low + 1.0
        arr = np.clip((arr - low) / (high - low), 0, 1)
        return (arr * 255).astype(np.uint8)
    if img.ndim == 2:
        norm = _normalize_to_uint8(img)
        Image.fromarray(norm, mode="L").save(output_path, quality=95)
    elif img.ndim == 3:
        if img.shape[0] in [3,4]: img2 = np.transpose(img, (1,2,0))
        else: img2 = img
        channels = []
        for i in range(img2.shape[2]):
            channels.append(_normalize_to_uint8(img2[..., i]))
        img_out = np.stack(channels, axis=-1)
        Image.fromarray(img_out).save(output_path, quality=95)

from openpyxl import Workbook
# --- замените эти две функции в main_ui.py ---


def process_block(gray_block, x_off, y_off, results, lock, block_id, output_dir, row_idx, col_idx, stats_rows):
    """Обработка блока изображения с выделением комет и звезд внутри больших туманностей"""
    local_contours = []
    h, w = gray_block.shape

    block_bgr = (np.stack([gray_block]*3, axis=-1) * 255).astype(np.uint8)
    block_bgr = cv2.cvtColor(block_bgr, cv2.COLOR_RGB2BGR)

    threshold = 0.05
    mask = (gray_block >= threshold).astype(np.uint8) * 255
    kernel = np.ones((3,3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        cnt_area = cv2.contourArea(cnt)
        if cnt_area < MIN_CONTOUR_AREA:
            continue

        brightness = get_contour_brightness(gray_block, cnt)

        # Определяем вытянутость
        elongation = 1.0
        if len(cnt) >= 5:
            try:
                (cx_e, cy_e), (axes1, axes2), _ = cv2.fitEllipse(cnt)
                major_axis, minor_axis = max(axes1, axes2), min(axes1, axes2)
                if minor_axis > 0:
                    elongation = major_axis / minor_axis
            except Exception:
                pass

        # Выделяем класс кометы
        if elongation >= 5 and brightness > 0.4:
            obj_class = "Flying Comet"
            color = (255, 128, 0)
        else:
            obj_class, color = classify_astronomical_object(brightness, cnt_area)

        # Центр контура
        M = cv2.moments(cnt)
        if M.get("m00", 0) != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            x_r, y_r, w_r, h_r = cv2.boundingRect(cnt)
            cx = int(x_r + w_r / 2)
            cy = int(y_r + h_r / 2)

        mask_local = np.zeros_like(gray_block, dtype=np.uint8)
        cv2.drawContours(mask_local, [cnt], -1, 255, -1)
        max_brightness = float(np.max(gray_block[mask_local > 0])) if np.any(mask_local) else brightness

        cnt_global = cnt + [x_off, y_off]
        local_contours.append((cnt_global, color, obj_class, cnt_area, brightness))

        cv2.drawContours(block_bgr, [cnt], -1, color, 2, cv2.LINE_AA)
        cv2.putText(block_bgr, obj_class, (cx + 5, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

        # === Новый шаг: повторный анализ для больших контуров ===
        if cnt_area > 10000:
            gray_inside = gray_block.copy()
            gray_inside[mask_local == 0] = 0  # анализируем только внутри большой туманности

            local_values = gray_inside[mask_local > 0]
            if len(local_values) > 0:
                local_bg = np.median(local_values)
                local_norm = gray_inside - local_bg
                local_norm[local_norm < 0] = 0
                high = np.percentile(local_norm[local_norm > 0], 99.5) if np.any(local_norm > 0) else 1.0
                local_norm = np.clip(local_norm / high, 0, 1)

                # Находим "звезды внутри"
                submask = (local_norm > 0.6).astype(np.uint8) * 255
                submask = cv2.morphologyEx(submask, cv2.MORPH_OPEN, kernel, iterations=1)
                subcontours, _ = cv2.findContours(submask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for scnt in subcontours:
                    s_area = cv2.contourArea(scnt)
                    if s_area < 30:
                        continue
                    s_brightness = get_contour_brightness(local_norm, scnt)
                    s_color = (255, 255, 100)
                    s_class = "Embedded Star"

                    M2 = cv2.moments(scnt)
                    if M2.get("m00", 0) != 0:
                        sx = int(M2["m10"] / M2["m00"])
                        sy = int(M2["m01"] / M2["m00"])
                    else:
                        sx, sy = 0, 0

                    gx, gy = x_off + sx, y_off + sy

                    cv2.drawContours(block_bgr, [scnt], -1, s_color, 1, cv2.LINE_AA)
                    cv2.putText(block_bgr, "★", (sx + 2, sy - 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, s_color, 1, cv2.LINE_AA)

                    with lock:
                        stats_rows.append([
                            row_idx, col_idx, s_area, round(s_brightness, 5),
                            1.0, gx, gy, s_class
                        ])
                        results.append((scnt + [x_off, y_off], s_color, s_class, s_area, s_brightness))

        # Добавляем основную запись
        with lock:
            stats_rows.append([
                row_idx, col_idx, cnt_area, round(brightness, 5),
                round(max_brightness, 5), x_off + cx, y_off + cy, obj_class
            ])

    # сохраняем блок
    if output_dir:
        try:
            cv2.imwrite(os.path.join(output_dir, f"block_{block_id}.jpg"), block_bgr)
        except Exception:
            pass

    with lock:
        results.extend(local_contours)


def find_and_draw_contours_multithread(gray_float01, base_color_image, num_rows, num_cols, output_dir=None):
    """Многопоточная обработка и сбор статистики в XLSX"""
    h, w = gray_float01.shape
    block_height = h // num_rows
    block_width = w // num_cols

    results = []
    stats_rows = []
    lock = threading.Lock()
    threads = []
    block_id = 0

    for i in range(num_rows):
        for j in range(num_cols):
            y0 = i * block_height
            y1 = (i+1) * block_height if i < num_rows - 1 else h
            x0 = j * block_width
            x1 = (j+1) * block_width if j < num_cols - 1 else w

            gray_block = gray_float01[y0:y1, x0:x1]
            t = threading.Thread(
                target=process_block,
                args=(gray_block, x0, y0, results, lock, block_id, output_dir, i, j, stats_rows)
            )
            threads.append(t)
            t.start()
            block_id += 1

    # дождаться всех потоков
    for t in threads:
        t.join()

    # сохраняем xlsx (если указан output_dir)
    if output_dir:
        try:
            xlsx_path = os.path.join(output_dir, "object_stats.xlsx")
            wb = Workbook()
            ws = wb.active
            ws.title = "Objects"
            headers = ["row", "col", "area", "mean_brightness", "max_brightness", "center_x", "center_y", "class"]
            ws.append(headers)
            for r in stats_rows:
                ws.append(r)
            wb.save(xlsx_path)
        except Exception:
            pass

    # финальная визуализация на общем изображении
    out = base_color_image.copy()
    class_counts = {}

    for cnt, color, obj_class, area, brightness in results:
        # гарантируем целые координаты
        try:
            cnt_int = cnt.astype(np.int32)
        except Exception:
            cnt_int = np.array(cnt, dtype=np.int32)
        cv2.drawContours(out, [cnt_int], -1, color, 2, cv2.LINE_AA)

        M = cv2.moments(cnt_int)
        if M.get("m00", 0) != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            cv2.putText(out, obj_class, (cx + 5, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

        class_counts[obj_class] = class_counts.get(obj_class, 0) + 1

    return out, class_counts


def cv2_to_qimage(cv_img_bgr):
    h, w = cv_img_bgr.shape[:2]
    if cv_img_bgr.ndim == 2:
        img = QImage(cv_img_bgr.data, w, h, w, QImage.Format_Grayscale8)
    else:
        rgb = cv2.cvtColor(cv_img_bgr, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return img.copy()

class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Astronomical Object Classifier")
        self.resize(1400, 800)
        self.tiff_image = None
        self.tiff_path = None
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)
        
        # Левая панель
        left_widget = QVBoxLayout()
        
        btn_open = QPushButton("Open TIFF")
        btn_open.clicked.connect(self.open_tiff)
        left_widget.addWidget(btn_open)
        
        # Настройки разбиения
        settings_group = QGroupBox("Processing Settings")
        settings_layout = QFormLayout()
        
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(2)
        settings_layout.addRow("Rows:", self.spin_rows)
        
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 10)
        self.spin_cols.setValue(4)
        settings_layout.addRow("Columns:", self.spin_cols)
        
        settings_group.setLayout(settings_layout)
        left_widget.addWidget(settings_group)
        
        # Легенда классов объектов
        legend_group = QGroupBox("Object Classes Legend")
        legend_layout = QVBoxLayout()
        legend_text = QLabel(
            "<small>"
            "<b>Stars:</b> Bright, compact<br>"
            "<b>Galaxy Core:</b> Very bright, medium size<br>"
            "<b>Galaxy:</b> Medium brightness, large<br>"
            "<b>Nebula:</b> Dim, very large<br>"
            "<b>Clusters:</b> Medium-bright, medium size<br>"
            "<b>Quasar/AGN:</b> Extremely bright, point source<br>"
            "<b>Asteroid/Comet:</b> Dim, small"
            "</small>"
        )
        legend_text.setWordWrap(True)
        legend_layout.addWidget(legend_text)
        legend_group.setLayout(legend_layout)
        left_widget.addWidget(legend_group)
        
        self.preview_scene = QGraphicsScene()
        self.preview_view = ZoomableGraphicsView(self.preview_scene)
        left_widget.addWidget(QLabel("Preview (JPEG)"))
        left_widget.addWidget(self.preview_view, stretch=1)
        
        # Правая панель
        right_widget = QVBoxLayout()
        
        btn_run = QPushButton("Classify Objects")
        btn_run.clicked.connect(self.run_classification)
        right_widget.addWidget(btn_run)
        
        self.label_info = QLabel("Info: Ready")
        self.label_info.setWordWrap(True)
        right_widget.addWidget(self.label_info)
        
        # Статистика
        self.label_stats = QLabel("Statistics: -")
        self.label_stats.setWordWrap(True)
        right_widget.addWidget(self.label_stats)
        
        right_widget.addWidget(QLabel("Result"))
        self.result_scene = QGraphicsScene()
        self.result_view = ZoomableGraphicsView(self.result_scene)
        right_widget.addWidget(self.result_view, stretch=1)
        
        main_layout.addLayout(left_widget, stretch=1)
        main_layout.addLayout(right_widget, stretch=1)

    def open_tiff(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select TIFF file", ".", 
                                             "TIFF files (*.tif *.tiff);;All files (*)")
        if not path: 
            return
        
        self.tiff_path = path
        tmp_jpg = os.path.splitext(path)[0] + "_preview.jpg"
        
        try: 
            tiff_to_jpeg(path, tmp_jpg)
        except Exception as e:
            self.label_info.setText(f"Error creating preview: {e}")
            return
        
        pix = QPixmap(tmp_jpg)
        self.preview_scene.clear()
        self.preview_scene.addItem(QGraphicsPixmapItem(pix))
        self.preview_view.fitInView(self.preview_scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        
        try: 
            self.tiff_image = cv2.imread(path)
            self.label_info.setText(f"Loaded: {os.path.basename(path)}")
            self.label_stats.setText("Statistics: -")
        except Exception as e:
            self.tiff_image = None
            self.label_info.setText(f"Error loading TIFF: {e}")

    def run_classification(self):
        if self.tiff_image is None: 
            self.label_info.setText("No image loaded!")
            return
        
        num_rows = self.spin_rows.value()
        num_cols = self.spin_cols.value()
        
        self.label_info.setText(f"Processing with {num_rows}x{num_cols} blocks...")
        
        img = self.tiff_image
        
        # Определяем grayscale канал
        if img.ndim == 2: 
            gray = img
        elif img.ndim == 3:
            if img.shape[0] in (1,2,3,4) and img.shape[0] != img.shape[1]:
                img2 = np.transpose(img, (1,2,0))
            else: 
                img2 = img
            gray = img2[...,0]
        else: 
            return
        
        gray_norm = normalize_float01(gray)
        
        # Создаем базовое цветное изображение
        if img.ndim == 2:
            base_rgb = (np.stack([gray_norm]*3, axis=-1) * 255).astype(np.uint8)
            base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
        else:
            if img.ndim == 3:
                if img.shape[0] in (3,4): 
                    img2 = np.transpose(img, (1,2,0))
                else: 
                    img2 = img
                chans = []
                for i in range(min(3, img2.shape[2])):
                    chans.append((normalize_float01(img2[..., i])*255).astype(np.uint8))
                if len(chans)<3: 
                    chans = chans+[chans[0]]*(3-len(chans))
                base_rgb = np.stack(chans[:3], axis=-1)
                base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
            else:
                base_bgr = (np.stack([gray_norm]*3, axis=-1) * 255).astype(np.uint8)
                base_bgr = cv2.cvtColor(base_bgr, cv2.COLOR_RGB2BGR)
        
        # Создаем папку для сохранения блоков
        output_dir = os.path.join(os.path.dirname(self.tiff_path), "blocks")
        os.makedirs(output_dir, exist_ok=True)
        
        # Обработка
        result_bgr, class_counts = find_and_draw_contours_multithread(
            gray_norm, base_bgr, num_rows, num_cols, output_dir
        )
        
        # Сохраняем полный результат
        result_path = os.path.join(os.path.dirname(self.tiff_path), "classified_result.jpg")
        cv2.imwrite(result_path, result_bgr)
        
        # Отображаем результат
        qimg = cv2_to_qimage(result_bgr)
        pix = QPixmap.fromImage(qimg)
        self.result_scene.clear()
        self.result_scene.addItem(QGraphicsPixmapItem(pix))
        self.result_view.fitInView(self.result_scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        
        # Формируем статистику
        total_objects = sum(class_counts.values())
        stats_text = f"<b>Total objects: {total_objects}</b><br>"
        for obj_class, count in sorted(class_counts.items(), key=lambda x: x[1], reverse=True):
            stats_text += f"{obj_class}: {count}<br>"
        
        self.label_stats.setText(stats_text)
        self.label_info.setText(f"Done! Blocks saved to: {output_dir}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())