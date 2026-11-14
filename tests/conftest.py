"""Faux Calibre minimal pour tester le plugin sans installer Calibre."""
import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
FIX = Path(__file__).resolve().parent / "fixtures"

# URL (fin de chemin, insensible à la casse) → fixture
ROUTES = {
    "search.php?t=l'insurrection": "s_insur.html",
    "search.php?t=veronica roth": "s_roth.html",
    "/biblio/auteur/veronica-roth.html": "a_roth.html",
    "/biblio/livre/marquer-les-ombres-tome-2.html": "b_t2.html",
    "/biblio/livre/divergente-raconte-par-quatre.html": "b_hs3.html",
    "/biblio/livre/divergent-divergente-divergence-tome-2-insurges-l-insurrection.html": "b_hs3.html",
    "/biblio/livre/noirs-tatouages.html": "b_noirs.html",
}


class FakeBrowser:
    def __init__(self):
        self.addheaders = []
        self.visited = []

    def open_novisit(self, url, timeout=30):
        u = unquote(url)
        self.visited.append(u.replace("https://www.livraddict.com", ""))
        for k, f in ROUTES.items():
            if u.lower().endswith(k):
                data = (FIX / f).read_bytes()
                return types.SimpleNamespace(read=lambda d=data: d)
        return types.SimpleNamespace(read=lambda: b"<html><div id='tab_livres'></div></html>")


class Option:
    def __init__(self, name, type_, default, label, desc, choices=None):
        self.name, self.default = name, default


class Source:
    def __init__(self):
        self.prefs = {o.name: o.default for o in self.options}
        self._cov, self._isbn = {}, {}
        self.browser = FakeBrowser()

    def cache_identifier_to_cover_url(self, i, u):
        self._cov[i] = u

    def cached_identifier_to_cover_url(self, i):
        return self._cov.get(i)

    def cache_isbn_to_identifier(self, isbn, i):
        self._isbn[isbn] = i

    def cached_isbn_to_identifier(self, isbn):
        return self._isbn.get(isbn)

    def clean_downloaded_metadata(self, mi):
        pass

    def identify_results_keygen(self, **kw):
        return lambda mi: mi.source_relevance


class Metadata:
    def __init__(self, title, authors):
        self.title, self.authors = title, authors
        self.identifiers, self.isbn = {}, None
        self.series = self.series_index = self.publisher = self.pubdate = None
        self.rating = self.comments = None
        self.tags, self.languages, self.source_relevance = [], [], 0
        self.has_cover = False

    def set_identifier(self, k, v):
        self.identifiers[k] = v


class Log:
    def info(self, *a):
        pass

    error = exception = info


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def _install_fake_calibre():
    for n in ("calibre", "calibre.ebooks", "calibre.ebooks.metadata", "calibre.ebooks.metadata.sources",
              "calibre.ebooks.metadata.book", "calibre.utils"):
        _module(n)
    _module("calibre.ebooks.metadata.sources.base", Source=Source, Option=Option)
    _module("calibre.ebooks.metadata.book.base", Metadata=Metadata)
    _module("calibre.utils.date", parse_only_date=lambda s, **k: datetime.fromisoformat(s))
    pkg = _module("calibre_plugins")
    pkg.__path__ = []
    spec = importlib.util.spec_from_file_location("calibre_plugins.livraddict", SRC / "__init__.py",
                                                  submodule_search_locations=[str(SRC)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibre_plugins.livraddict"] = mod
    spec.loader.exec_module(mod)
    return mod


LA = _install_fake_calibre()


@pytest.fixture
def plugin():
    p = LA.Livraddict()
    p.prefs["delai"] = 0
    return p


@pytest.fixture
def log():
    return Log()
