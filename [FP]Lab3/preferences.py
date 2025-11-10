# -*- coding: utf-8 -*-
from typing import Dict, List, Set

Prefs = Dict[str, Set[str]]

def _lower(s: str) -> str:
    return s.lower()

def _parse_line(line: str) -> List[str]:
    return [t.strip() for t in line.split(",") if t.strip()]

def make_prefs(genres_text: str, authors_text: str, keywords_text: str) -> Prefs:
    return {
        "genres": set(map(_lower, _parse_line(genres_text))),
        "authors": set(_parse_line(authors_text)),
        "keywords": set(map(_lower, _parse_line(keywords_text))),
    }
