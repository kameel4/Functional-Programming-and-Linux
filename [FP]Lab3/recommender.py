from functools import reduce
from typing import Callable, Dict, Iterable, List

Book = Dict[str, object]
Prefs = Dict[str, set]

def stream(iterable):
    for x in iterable:
        yield x

def normalize_book(book: Book) -> Book:
    return {
        "title": book.get("title", ""),
        "author": book.get("author", ""),           # вместо «режиссера»
        "genre": (book.get("genre", "") or "").lower(),
        "description": book.get("description", ""),
        "year": int(book.get("year", 0)),
        "cover": book.get("cover", ""),             # <— добавлено
    }

def score_book(prefs: Prefs, book: Book) -> int:
    score = 0
    if book["genre"] in prefs["genres"] and prefs["genres"]:
        score += 3
    if book["author"] in prefs["authors"] and prefs["authors"]:
        score += 3
    if prefs["keywords"]:
        hay = f'{str(book["title"]).lower()} {str(book["description"]).lower()}'
        score += sum(1 for kw in prefs["keywords"] if kw in hay)
    return score

def annotate_scores(prefs: Prefs) -> Callable[[Iterable[Book]], Iterable[Book]]:
    def _inner(books: Iterable[Book]) -> Iterable[Book]:
        for b in books:
            bb = dict(b)
            bb["score"] = score_book(prefs, b)
            yield bb
    return _inner

def filter_only_genres(prefs: Prefs, enabled: bool) -> Callable[[Iterable[Book]], Iterable[Book]]:
    def _inner(books: Iterable[Book]) -> Iterable[Book]:
        for b in books:
            if not enabled or not prefs["genres"] or b["genre"] in prefs["genres"]:
                yield b
    return _inner

def filter_after_year(year_threshold: int) -> Callable[[Iterable[Book]], Iterable[Book]]:
    def _inner(books: Iterable[Book]) -> Iterable[Book]:
        if year_threshold <= 0:
            yield from books
        else:
            for b in books:
                if int(b["year"]) > year_threshold:
                    yield b
    return _inner

def _sorter(mode: str):
    if mode == "alpha":
        return lambda items: sorted(items, key=lambda b: str(b["title"]))
    if mode == "year":
        return lambda items: sorted(items, key=lambda b: int(b["year"]), reverse=True)
    return lambda items: sorted(items, key=lambda b: (int(b.get("score", 0)), int(b["year"])), reverse=True)

def _compose(*funcs: Callable):
    def _composed(x):
        return reduce(lambda acc, f: f(acc), funcs, x)
    return _composed

def recommend(books: List[Book], prefs: Prefs, only_genres: bool, year_after: int, sort_mode: str) -> List[Book]:
    pipeline = _compose(
        stream,
        lambda it: (normalize_book(b) for b in it),
        filter_only_genres(prefs, only_genres),
        filter_after_year(year_after),
        annotate_scores(prefs),
        list,
        _sorter(sort_mode),
    )
    return pipeline(books)
