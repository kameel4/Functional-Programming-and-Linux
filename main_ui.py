# astro_classifier_ui_threads.py
import sys, os, threading
import numpy as np
import tifffile
from PIL import Image
import cv2
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem
from PyQt5.QtGui import QPixmap, QImage, QPainter

CLASS_DEFS = [
    ("Очень тусклые", 0.00, 0.10, (255, 200, 150)),
    ("Тусклые",       0.10, 0.25, (100, 200, 0)),
    ("Средние",       0.25, 0.40, (0, 255, 255)),
    ("Яркие",         0.40, 0.60, (0, 165, 255)),
    ("Очень яркие",   0.60, 0.80, (0, 0, 255)),
    ("Сверхъяркие",   0.80, 1.00, (200, 0, 200)),
]

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


def tiff_to_jpeg(input_path, output_path):
    img = tifffile.imread(input_path)
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

def process_block(gray_block, x_off, y_off, results, lock):
    local_contours = []
    for name, lo, hi, color in CLASS_DEFS:
        mask = np.logical_and(gray_block >= lo, gray_block < hi).astype(np.uint8) * 255
        if name in ("Очень яркие", "Сверхъяркие"):
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            for i in range(1, num_labels):
                if stats[i, cv2.CC_STAT_AREA] < 1: continue
                x, y, w_box, h_box, _ = stats[i]
                component_mask = (labels[y:y+h_box, x:x+w_box] == i).astype(np.uint8) * 255
                contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    cnt = cnt + [x_off + x, y_off + y]
                    local_contours.append((cnt, color))
        else:
            kernel = np.ones((3,3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                if cv2.contourArea(cnt) < 1: continue
                cnt = cnt + [x_off, y_off]
                local_contours.append((cnt, color))
    with lock:
        results.extend(local_contours)

def find_and_draw_contours_multithread(gray_float01, base_color_image):
    h, w = gray_float01.shape
    block_height = h // 2
    block_width = w // 4
    results = []
    lock = threading.Lock()
    threads = []
    for i in range(2):
        for j in range(4):
            y0, y1 = i * block_height, (i+1) * block_height if i < 1 else h
            x0, x1 = j * block_width, (j+1) * block_width if j < 3 else w
            gray_block = gray_float01[y0:y1, x0:x1]
            t = threading.Thread(target=process_block, args=(gray_block, x0, y0, results, lock))
            threads.append(t)
            t.start()
    for t in threads: t.join()
    out = base_color_image.copy()
    for cnt, color in results:
        cv2.drawContours(out, [cnt], -1, color, thickness=2, lineType=cv2.LINE_AA)
    return out

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
        self.setWindowTitle("Классификатор объектов по яркости (TIFF) — threads")
        self.resize(1200, 700)
        self.tiff_image = None
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QHBoxLayout(); central.setLayout(main_layout)
        left_widget = QVBoxLayout()
        btn_open = QPushButton("Открыть TIFF"); btn_open.clicked.connect(self.open_tiff); left_widget.addWidget(btn_open)
        self.preview_scene = QGraphicsScene()
        self.preview_view = ZoomableGraphicsView(self.preview_scene)
        left_widget.addWidget(QLabel("Превью (JPEG)"))
        left_widget.addWidget(self.preview_view, stretch=1)
        right_widget = QVBoxLayout()
        btn_run = QPushButton("Классифицировать (threads)"); btn_run.clicked.connect(self.run_classification); right_widget.addWidget(btn_run)
        right_widget.addWidget(QLabel("Результат"))
        self.result_scene = QGraphicsScene()
        self.result_view = ZoomableGraphicsView(self.result_scene)
        right_widget.addWidget(self.result_view, stretch=1)
        main_layout.addLayout(left_widget, stretch=1)
        main_layout.addLayout(right_widget, stretch=1)

    def open_tiff(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите TIFF файл", ".", "TIFF files (*.tif *.tiff);;All files (*)")
        if not path: return
        tmp_jpg = os.path.splitext(path)[0] + "_preview.jpg"
        try: tiff_to_jpeg(path, tmp_jpg)
        except: return
        pix = QPixmap(tmp_jpg)
        self.preview_scene.clear()
        self.preview_scene.addItem(QGraphicsPixmapItem(pix))
        self.preview_view.fitInView(self.preview_scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        try: self.tiff_image = tifffile.imread(path)
        except: self.tiff_image = None

    def run_classification(self):
        if self.tiff_image is None: return
        img = self.tiff_image
        if img.ndim == 2: gray = img
        elif img.ndim == 3:
            if img.shape[0] in (1,2,3,4) and img.shape[0] != img.shape[1]:
                img2 = np.transpose(img, (1,2,0))
            else: img2 = img
            gray = img2[...,0]
        else: return
        gray_norm = normalize_float01(gray)
        if img.ndim == 2:
            base_rgb = (np.stack([gray_norm]*3, axis=-1) * 255).astype(np.uint8)
            base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
        else:
            if img.ndim == 3:
                if img.shape[0] in (3,4): img2 = np.transpose(img, (1,2,0))
                else: img2 = img
                chans = []
                for i in range(min(3, img2.shape[2])):
                    chans.append((normalize_float01(img2[..., i])*255).astype(np.uint8))
                if len(chans)<3: chans = chans+[chans[0]]*(3-len(chans))
                base_rgb = np.stack(chans[:3], axis=-1)
                base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
            else:
                base_bgr = (np.stack([gray_norm]*3, axis=-1) * 255).astype(np.uint8)
                base_bgr = cv2.cvtColor(base_bgr, cv2.COLOR_RGB2BGR)
        result_bgr = find_and_draw_contours_multithread(gray_norm, base_bgr)
        qimg = cv2_to_qimage(result_bgr)
        pix = QPixmap.fromImage(qimg)
        self.result_scene.clear()
        self.result_scene.addItem(QGraphicsPixmapItem(pix))
        self.result_view.fitInView(self.result_scene.itemsBoundingRect(), Qt.KeepAspectRatio)

if __name__ == "__main__":
    app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec_())
