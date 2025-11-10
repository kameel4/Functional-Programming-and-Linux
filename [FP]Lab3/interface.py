# -*- coding: utf-8 -*-
import sys, os, json, csv
from pathlib import Path
from typing import Dict, List

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QCheckBox, QSpinBox, QComboBox, QToolButton, QScrollArea
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QImageReader

from data_loader import read_books, Book
from preferences import make_prefs
from recommender import recommend

# === путь к данным (JSON с полем cover) ===
DATA_PATH = "books.json"
DATA_DIR = Path(DATA_PATH).resolve().parent

def _abs_cover_path(p: str) -> str:
    pth = Path(p)
    return str(pth if pth.is_absolute() else (DATA_DIR / pth).resolve())

# ------------------ Виджет карточки книги ------------------
class BookCard(QWidget):
    def __init__(self, book: Dict[str, object], index: int):
        super().__init__()
        self.book = book

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10); row.setSpacing(12)

        # Обложка
        cover = QLabel()
        cover.setFixedSize(QSize(80, 120))
        path = str(book.get("cover", ""))
        reader = QImageReader(path); reader.setAutoTransform(True); reader.setDecideFormatFromContent(True)
        img = reader.read(); pix = QPixmap.fromImage(img)
        if not pix.isNull():
            cover.setPixmap(pix.scaled(80, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        row.addWidget(cover)

        # Тексты
        col = QVBoxLayout()
        title = QLabel(f"{index}. {book.get('title','')}"); title.setStyleSheet("font-weight:600;")
        author_year = QLabel(f"{book.get('author','')} • {book.get('year','')}"); author_year.setStyleSheet("color:#555;")
        genre = QLabel(str(book.get("genre",""))); genre.setStyleSheet("color:#777;")
        desc = QLabel(str(book.get("description",""))); desc.setWordWrap(True); desc.setStyleSheet("color:#444;")
        col.addWidget(title); col.addWidget(author_year); col.addWidget(genre); col.addWidget(desc); col.addStretch(1)
        row.addLayout(col, stretch=1)

        # Рейтинг
        score_box = QVBoxLayout()
        score_lbl = QLabel(str(book.get("score", 0))); score_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
        score_lbl.setStyleSheet("font-size:18px; font-weight:600;")
        score_box.addWidget(score_lbl); score_box.addStretch(1)
        row.addLayout(score_box)

# ------------------ Главное окно ------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Рекомендательная система книг (PyQt)")
        self.resize(960, 700)

        # Данные
        self.books_db: List[Book] = read_books(DATA_PATH)
        self.recommendations: List[Book] = []
        self.to_read: List[Book] = []

        # === ЖАНРЫ как чекбоксы ===
        self.genre_cbs: List[QCheckBox] = []
        genre_row_widget = QWidget()
        genre_row_layout = QHBoxLayout(genre_row_widget)
        genre_row_layout.setContentsMargins(0, 0, 0, 0); genre_row_layout.setSpacing(8)
        for g in self._collect_genres(self.books_db):
            cb = QCheckBox(g)
            self.genre_cbs.append(cb)
            genre_row_layout.addWidget(cb)
        genre_row_layout.addStretch(1)

        # === АВТОРЫ: выпадающий список + «чипы» выбранных авторов ===
        self.author_combo = QComboBox()
        self.author_combo.addItem("— выбрать автора —")
        for a in self._collect_authors(self.books_db):
            self.author_combo.addItem(a)
        self.author_combo.activated[str].connect(self.on_author_selected)

        self.selected_authors: List[str] = []
        self.author_tag_widgets: Dict[str, QWidget] = {}

        # контейнер для чипов (горизонтальный скролл)
        self.author_tags_container = QWidget()
        self.author_tags_layout = QHBoxLayout(self.author_tags_container)
        self.author_tags_layout.setContentsMargins(0, 0, 0, 0)
        self.author_tags_layout.setSpacing(6)
        self.author_tags_layout.addStretch(1)

        self.author_tags_scroll = QScrollArea()
        self.author_tags_scroll.setWidget(self.author_tags_container)
        self.author_tags_scroll.setWidgetResizable(True)
        self.author_tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.author_tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.author_tags_scroll.setFixedHeight(36)
        self.author_tags_scroll.setStyleSheet("QScrollArea { border: none; }")

        # Ключевые слова
        self.keywords_edit = QLineEdit()

        self.only_genres_cb = QCheckBox("Только указанные жанры")
        self.year_spin = QSpinBox(); self.year_spin.setRange(0, 2100); self.year_spin.setValue(0)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("По рейтингу", userData="score")
        self.sort_combo.addItem("По алфавиту", userData="alpha")
        self.sort_combo.addItem("По году публикации (новые сверху)", userData="year")

        self.recommend_btn = QPushButton("Показать рекомендации")
        self.add_to_read_btn = QPushButton("Добавить в «прочитать»")
        self.save_btn = QPushButton("Сохранить рекомендации...")

        # Список карточек
        self.cards = QListWidget(); self.cards.setSelectionMode(QListWidget.ExtendedSelection)
        self.cards.setSpacing(8); self.cards.setStyleSheet("QListWidget { background:#f5f5f5; border:none; }")

        # Список «прочитать»
        self.to_read_list = QListWidget()

        # Компоновка
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        row_genres = QHBoxLayout(); row_genres.addWidget(QLabel("Жанры:")); row_genres.addWidget(genre_row_widget, stretch=1)

        row_author = QHBoxLayout()
        row_author.addWidget(QLabel("Авторы:"))
        row_author.addWidget(self.author_combo)
        row_author.addWidget(self.author_tags_scroll, stretch=1)

        row_kw = QHBoxLayout(); row_kw.addWidget(QLabel("Ключевые слова:")); row_kw.addWidget(self.keywords_edit)

        filters = QHBoxLayout()
        filters.addWidget(self.only_genres_cb)
        filters.addWidget(QLabel("Год после:")); filters.addWidget(self.year_spin)
        filters.addStretch(1)
        filters.addWidget(QLabel("Сортировка:")); filters.addWidget(self.sort_combo)

        btns = QHBoxLayout(); btns.addWidget(self.recommend_btn); btns.addWidget(self.add_to_read_btn); btns.addStretch(1); btns.addWidget(self.save_btn)

        lists = QHBoxLayout()
        lists.addWidget(self.cards, stretch=3)
        side = QVBoxLayout(); side.addWidget(QLabel("Список «прочитать»:")); side.addWidget(self.to_read_list); lists.addLayout(side, stretch=1)

        layout.addLayout(row_genres)
        layout.addLayout(row_author)
        layout.addLayout(row_kw)
        layout.addLayout(filters)
        layout.addLayout(btns)
        layout.addLayout(lists)

        # Сигналы
        self.recommend_btn.clicked.connect(self.on_recommend)
        self.add_to_read_btn.clicked.connect(self.on_add_to_read)
        self.save_btn.clicked.connect(self.on_save)

        self.on_recommend()

    # ---- helpers ----
    @staticmethod
    def _collect_genres(books: List[Book]) -> List[str]:
        s = {str(b.get("genre","")).strip().lower() for b in books if b.get("genre")}
        return sorted(s)

    @staticmethod
    def _collect_authors(books: List[Book]) -> List[str]:
        s = {str(b.get("author","")).strip() for b in books if b.get("author")}
        return sorted(s, key=lambda x: x.casefold())

    def fill_cards(self, items: List[Book]):
        self.cards.clear()
        for i, book in enumerate(items, 1):
            w = BookCard(book, i)
            it = QListWidgetItem(self.cards); it.setSizeHint(w.sizeHint()); it.setData(Qt.UserRole, book)
            self.cards.addItem(it); self.cards.setItemWidget(it, w)

    def selected_books_from_cards(self) -> List[Book]:
        return [dict(it.data(Qt.UserRole)) for it in self.cards.selectedItems()]

    # ---- авторы: добавление/удаление чипов ----
    def on_author_selected(self, name: str):
        if name == "— выбрать автора —":
            return
        if name in self.selected_authors:
            # уже выбран — ничего не делаем
            self.author_combo.setCurrentIndex(0)
            return
        self.selected_authors.append(name)
        self._add_author_tag(name)
        self.author_combo.setCurrentIndex(0)
        # по желанию сразу обновлять выдачу:
        # self.on_recommend()

    def _add_author_tag(self, name: str):
        w = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(8, 2, 4, 2); lay.setSpacing(6)
        lbl = QLabel(name)
        btn = QToolButton(); btn.setText("×"); btn.setCursor(Qt.PointingHandCursor); btn.setAutoRaise(True)
        btn.setFixedSize(18, 18)
        btn.clicked.connect(lambda: self._remove_author_tag(name))
        lay.addWidget(lbl); lay.addWidget(btn)

        w.setStyleSheet("QWidget { background:#e9eef7; border:1px solid #c6d2ee; border-radius:10px; }")
        # вставляем перед растягивающим спейсером
        idx = self.author_tags_layout.count() - 1
        self.author_tags_layout.insertWidget(idx, w)
        self.author_tag_widgets[name] = w

    def _remove_author_tag(self, name: str):
        if name in self.selected_authors:
            self.selected_authors.remove(name)
        w = self.author_tag_widgets.pop(name, None)
        if w:
            w.setParent(None)
            w.deleteLater()
        # self.on_recommend()  # если хочется автообновление — раскомментируйте

    # ---- handlers ----
    def on_recommend(self):
        # жанры из чекбоксов
        genres_text = ", ".join(cb.text() for cb in self.genre_cbs if cb.isChecked())
        # авторы из выбранных «чипов»
        authors_text = ", ".join(self.selected_authors)
        prefs = make_prefs(genres_text, authors_text, self.keywords_edit.text())

        only_genres = self.only_genres_cb.isChecked()
        year_after = int(self.year_spin.value())
        sort_mode = self.sort_combo.currentData()
        self.recommendations = recommend(self.books_db, prefs, only_genres, year_after, sort_mode)
        self.fill_cards(self.recommendations)

    def on_add_to_read(self):
        for b in self.selected_books_from_cards():
            self.to_read.append(b)
            self.to_read_list.addItem(f'{b.get("title","")} — {b.get("author","")} ({b.get("year","")})')

    def on_save(self):
        if not self.recommendations:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить рекомендации", "recommendations.json",
                                              "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        if path.lower().endswith(".json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.recommendations, f, ensure_ascii=False, indent=2)
        else:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["title","author","genre","year","description","score","cover"])
                for b in self.recommendations:
                    w.writerow([b.get("title",""), b.get("author",""), b.get("genre",""),
                                b.get("year",""), b.get("description",""), b.get("score",0),
                                b.get("cover","")])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
