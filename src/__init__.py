"""Source de métadonnées Livraddict pour Calibre."""

from __future__ import annotations

import re
import threading
import time
import urllib.parse

from calibre.ebooks.metadata.sources.base import Option, Source

_BASE = "https://www.livraddict.com"
_LOCK = threading.Lock()
_DERNIERE = [0.0]


class Livraddict(Source):
    name = "Livraddict"
    description = "Télécharge métadonnées et couvertures depuis Livraddict (livraddict.com)"
    author = "H4TH0R"
    version = (1, 0, 2)
    minimum_calibre_version = (6, 0, 0)

    capabilities = frozenset({"identify", "cover"})
    touched_fields = frozenset({
        "title", "authors", "identifier:livraddict", "identifier:isbn", "comments", "rating",
        "publisher", "pubdate", "series", "series_index", "tags", "languages",
    })
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    can_get_multiple_covers = False

    options = (
        Option("max_results", "number", 3, "Nombre de fiches à examiner",
               "Combien de résultats de recherche ouvrir (plus = plus lent)."),
        Option("delai", "number", 1.5, "Délai entre requêtes (s)",
               "Pause minimale entre deux pages, pour ne pas surcharger le site."),
        Option("titre_propre", "bool", True, "Nettoyer le titre",
               "« Saga, tome 2 : Titre » devient « Titre » (la série et le numéro vont dans les champs Série)."),
        Option("edition", "choices", "ancienne", "Édition utilisée pour éditeur / date / ISBN",
               "Quelle édition française retenir quand il y en a plusieurs.",
               {"ancienne": "La plus ancienne (1re parution française)",
                "recente": "La plus récente",
                "ebook": "Ebook français si disponible"}),
        Option("hors_serie", "choices", "apres", "Numérotation des hors-séries",
               "Livraddict note « HS 3 » ; Calibre a besoin d'un nombre.",
               {"apres": "Après les tomes (3.1, 3.2…)",
                "zero": "Avant les tomes (0.1, 0.2…)",
                "aucun": "Ne pas remplir la série"}),
        Option("tags_lectorat", "bool", True, "Ajouter le lectorat aux tags", "Ex. « Young Adult », « Adulte »."),
        Option("tags_themes", "bool", True, "Ajouter les thèmes aux tags", "Ex. « Dystopie », « Adapté en film »."),
        Option("titre_vo", "bool", False, "Ajouter le titre original au résumé", ""),
    )

    # ── identifiants ─────────────────────────────────────────────────────────
    def get_book_url(self, identifiers):
        slug = identifiers.get("livraddict")
        if slug:
            return ("livraddict", slug, f"{_BASE}/biblio/livre/{slug}.html")
        return None

    def id_from_url(self, url):
        from calibre_plugins.livraddict.parser import slug_de_url
        slug = slug_de_url(url) if "livraddict.com" in url else None
        return ("livraddict", slug) if slug else None

    def get_cached_cover_url(self, identifiers):
        slug = identifiers.get("livraddict")
        if slug:
            return self.cached_identifier_to_cover_url(slug)
        isbn = identifiers.get("isbn")
        if isbn:
            slug = self.cached_isbn_to_identifier(isbn)
            if slug:
                return self.cached_identifier_to_cover_url(slug)
        return None

    # ── réseau ───────────────────────────────────────────────────────────────
    def _get(self, url, timeout):
        with _LOCK:
            attente = float(self.prefs["delai"]) - (time.monotonic() - _DERNIERE[0])
            if attente > 0:
                time.sleep(attente)
            br = self.browser
            br.addheaders = [h for h in br.addheaders if h[0].lower() != "accept-language"] + \
                [("Accept-Language", "fr-FR,fr;q=0.9")]
            try:
                return br.open_novisit(url, timeout=timeout).read()
            finally:
                _DERNIERE[0] = time.monotonic()

    def _recherche(self, terme, timeout):
        from calibre_plugins.livraddict.parser import parse_recherche
        url = f"{_BASE}/search.php?t=" + urllib.parse.quote(terme)
        return parse_recherche(self._get(url, timeout))

    # ── identify ─────────────────────────────────────────────────────────────
    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        from calibre_plugins.livraddict.parser import numero_tome, parse_page_auteur, score

        slug = identifiers.get("livraddict")
        if not slug and identifiers.get("isbn"):
            slug = self.cached_isbn_to_identifier(identifiers["isbn"])
        if slug:
            slugs = [slug]
        else:
            if not title:
                log.info("Livraddict : pas de titre, recherche impossible (le site ne cherche pas par ISBN)")
                return None
            titre = self._titre_recherche(title)
            tome = numero_tome(title) or self._numero_prefixe(title)
            auteurs = [a for a in (authors or []) if a and a.lower() not in ("unknown", "inconnu(e)")]
            candidats = []
            try:
                livres, pages_auteurs = self._recherche(titre, timeout)
                candidats = livres
                # Plan B : le titre seul ne donne rien d'exploitable → bibliographie de l'auteur
                bons = [c for c in candidats if score(c, titre, auteurs, tome) > 0.3]
                if not bons and auteurs and not abort.is_set():
                    _, pages_auteurs = self._recherche(auteurs[0], timeout)
                    if pages_auteurs:
                        html = self._get(_BASE + pages_auteurs[0], timeout)
                        candidats = parse_page_auteur(html, auteurs[0])
            except Exception:
                log.exception("Livraddict : échec de la recherche")
                return "Livraddict : la recherche a échoué (voir le journal)"
            notes = sorted(((score(c, titre, auteurs, tome), c) for c in candidats), key=lambda x: -x[0])
            slugs = [c.slug for s, c in notes if s > 0.3][: int(self.prefs["max_results"])]
            if not slugs:
                log.info("Livraddict : aucun résultat pertinent pour", titre, auteurs)
                return None

        for rang, sl in enumerate(slugs):
            if abort.is_set():
                return None
            mi = self._fiche(log, sl, identifiers.get("isbn"), timeout)
            if mi is not None:
                mi.source_relevance = rang
                self.clean_downloaded_metadata(mi)
                result_queue.put(mi)
        return None

    @staticmethod
    def _numero_prefixe(title):
        m = re.match(r"^\s*t\s*(\d+)\s*[-–:.]", title, re.I)
        return int(m.group(1)) if m else None

    @staticmethod
    def _titre_recherche(title):
        t = re.sub(r"^\s*(?:t|tome|vol\.?)\s*\d+(?:[.,]\d+)?\s*[-–:.]\s*", "", title, flags=re.I)
        t = re.sub(r"\s*[(\[]\s*(?:t|tome|vol\.?)\s*\d+\s*[)\]]\s*$", "", t, flags=re.I)
        t = re.sub(r",?\s*(?:tome|t\.)\s*\d+\s*$", "", t, flags=re.I)
        return t.strip() or title

    def _fiche(self, log, slug, isbn_voulu, timeout):
        from calibre.ebooks.metadata.book.base import Metadata
        from calibre.utils.date import parse_only_date
        from calibre_plugins.livraddict.parser import nettoyer_titre, parse_livre

        url = f"{_BASE}/biblio/livre/{slug}.html"
        try:
            livre = parse_livre(self._get(url, timeout), slug)
        except Exception:
            log.exception("Livraddict : impossible de lire", url)
            return None
        if livre is None:
            log.info("Livraddict : pas une fiche livre", url)
            return None

        titre = nettoyer_titre(livre.titre_brut, livre.serie) if self.prefs["titre_propre"] else livre.titre_brut
        mi = Metadata(titre, livre.auteurs or None)
        mi.set_identifier("livraddict", slug)
        mi.languages = ["fra"]

        ed = livre.choisir_edition(isbn_voulu, self.prefs["edition"])
        isbn = livre.isbn_pour(ed)
        if isbn:
            mi.isbn = isbn
        for i in livre.tous_isbn():
            self.cache_isbn_to_identifier(i, slug)
        if ed and ed.editeur:
            mi.publisher = ed.editeur
        d = livre.premiere_parution() if self.prefs["edition"] == "ancienne" else None
        if d is None and ed:
            from datetime import date as _date
            d = ed.date or (_date(ed.annee, 1, 1) if ed.annee else None)
        if d:
            mi.pubdate = parse_only_date(d.isoformat(), assume_utc=False, as_utc=False)

        if livre.serie:
            idx = livre.serie_index(self.prefs["hors_serie"])
            if idx is not None:
                mi.series, mi.series_index = livre.serie, idx

        tags = list(livre.genres)
        if self.prefs["tags_lectorat"]:
            tags += livre.lectorat
        if self.prefs["tags_themes"]:
            tags += livre.themes
        if tags:
            mi.tags = tags

        if livre.note is not None:
            mi.rating = round(livre.note / 4, 1)       # /20 → /5

        resume = livre.resume
        if resume and livre.titre_vo and self.prefs["titre_vo"]:
            resume += f"<p><i>Titre original : {livre.titre_vo}</i></p>"
        if resume:
            mi.comments = resume

        if livre.couverture:
            self.cache_identifier_to_cover_url(slug, livre.couverture)
        mi.has_cover = bool(livre.couverture)
        return mi

    # ── couverture ───────────────────────────────────────────────────────────
    def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers={},
                       timeout=30, get_best_cover=False):
        url = self.get_cached_cover_url(identifiers)
        if url is None:
            from queue import Empty, Queue
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors, identifiers=identifiers, timeout=timeout)
            if abort.is_set():
                return
            res = []
            while True:
                try:
                    res.append(rq.get_nowait())
                except Empty:
                    break
            res.sort(key=self.identify_results_keygen(title=title, authors=authors, identifiers=identifiers))
            for mi in res:
                url = self.get_cached_cover_url(mi.identifiers)
                if url:
                    break
        if not url or abort.is_set():
            log.info("Livraddict : pas de couverture")
            return
        try:
            data = self._get(url, timeout)
        except Exception:
            log.exception("Livraddict : échec du téléchargement de la couverture", url)
            return
        if data:
            result_queue.put((self, data))


if __name__ == "__main__":
    # calibre-debug -e __init__.py   (Calibre fermé, depuis le dossier du plugin)
    from calibre.ebooks.metadata.sources.test import (authors_test, series_test, test_identify_plugin,
                                                      title_test)
    test_identify_plugin(Livraddict.name, [
        ({"title": "Marquer les ombres, tome 2", "authors": ["Veronica Roth"]},
         [title_test("Marquer les ombres", exact=False), authors_test(["Veronica Roth"]),
          series_test("Marquer les ombres", 2.0)]),
        ({"title": "L'insurrection", "authors": ["Veronica Roth"]},
         [title_test("insurrection", exact=False), series_test("Divergente / Divergence", 2.0)]),
        ({"title": "Au tréfonds du ciel", "authors": ["Vernor Vinge"]},
         [title_test("Au tréfonds du ciel", exact=True), authors_test(["Vernor Vinge"])]),
    ])
