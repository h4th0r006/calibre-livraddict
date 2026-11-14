"""Analyse des pages Livraddict (fonctions pures, testables hors de Calibre)."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

BASE_URL = "https://www.livraddict.com"
_BOOK_PATH_RE = re.compile(r"/biblio/livre/([^/?#]+?)\.html")
_MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
         "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
         "décembre": 12, "decembre": 12}
_DATE_RE = re.compile(r"^(?:(\d{1,2})(?:er)?\s+)?([a-zéèûô]+)\s+(\d{4})$", re.I)
_TOME_TITRE_RE = re.compile(r"^(?P<serie>.+?),\s*(?:tome|volume|livre)\s*[\d.,]+\s*(?::\s*(?P<titre>.+))?$", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# Outils
# ─────────────────────────────────────────────────────────────────────────────

def cle(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


_VIDES = {"les", "des", "une", "aux", "par", "pour", "sur", "dans", "avec", "the", "and", "tome", "livre",
          "volume", "book", "qui", "que", "est", "son", "ses", "leur", "leurs", "ces", "cette", "edition"}


def mots(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) >= 3 and w not in _VIDES}


_NUM_TOME_RE = re.compile(r"(?:\btome|\bt\.?|\bvol(?:ume)?\.?|\blivre|\bbook)\s*(\d+)\b", re.I)


def numero_tome(titre: str) -> int | None:
    m = _NUM_TOME_RE.search(titre or "")
    return int(m.group(1)) if m else None


def slug_de_url(url: str) -> str | None:
    m = _BOOK_PATH_RE.search(url or "")
    return m.group(1) if m else None


def isbn_valide(isbn: str) -> str | None:
    s = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(s) == 13 and s.isdigit():
        tot = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s[:12]))
        return s if str((10 - tot % 10) % 10) == s[12] else None
    if len(s) == 10:
        try:
            tot = sum((10 if c == "X" else int(c)) * (10 - i) for i, c in enumerate(s))
        except ValueError:
            return None
        if "X" in s[:9] or tot % 11:
            return None
        core = "978" + s[:9]
        tot = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
        return core + str((10 - tot % 10) % 10)
    return None


def nettoyer_titre(titre: str, serie: str | None) -> str:
    """« Divergent / Divergente / Divergence, tome 2 : Insurgés / L'insurrection » → « Insurgés / L'insurrection ».
    « Marquer les ombres, tome 2 » → « Marquer les ombres » (pas de sous-titre : on garde le nom)."""
    m = _TOME_TITRE_RE.match(titre or "")
    if not m:
        return titre
    if m.group("titre"):
        return m.group("titre").strip()
    return (serie or m.group("serie")).strip()


def _texte(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _soup(html: bytes | str) -> BeautifulSoup:
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    return BeautifulSoup(html, "html.parser")


# ─────────────────────────────────────────────────────────────────────────────
# Résultats de recherche / page auteur
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Resultat:
    slug: str
    titre: str
    auteurs: list[str]
    annee: str = ""


def parse_recherche(html) -> tuple[list[Resultat], list[str]]:
    """Renvoie (livres, chemins des pages auteurs trouvées)."""
    soup = _soup(html)
    livres = []
    for li in soup.select("#tab_livres .listing_recherche > li"):
        a = li.select_one("h3 a")
        if not a:
            continue
        slug = slug_de_url(a.get("href", ""))
        if not slug:
            continue
        vo = a.select_one(".titre_vo")
        if vo:
            vo.extract()
        titre = re.sub(r"\s*\(\s*\)\s*$", "", _texte(a)).strip()
        ident = li.select_one(".identite")
        auteurs = [_texte(x) for x in ident.select("a")] if ident else []
        m = re.search(r"\((\d{4})\)", _texte(ident))
        livres.append(Resultat(slug, titre, auteurs, m.group(1) if m else ""))
    auteurs = []
    for a in soup.select("#tab_auteurs a[href*='/biblio/auteur/']"):
        href = a.get("href", "")
        if href not in auteurs:
            auteurs.append(href)
    return livres, auteurs


def parse_page_auteur(html, nom_auteur: str = "") -> list[Resultat]:
    soup = _soup(html)
    out, vus = [], set()
    for a in soup.select("a[href*='/biblio/livre/']"):
        slug = slug_de_url(a.get("href", ""))
        if not slug or slug in vus or not _texte(a):
            continue
        vus.add(slug)
        vo = a.select_one(".titre_vo")
        if vo:
            vo.extract()
        out.append(Resultat(slug, re.sub(r"\s*\(\s*\)\s*$", "", _texte(a)).strip(),
                            [nom_auteur] if nom_auteur else []))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fiche livre
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Edition:
    type: str          # L (papier), E (ebook), A (audio)
    langue: str        # fr, gb...
    annee: int | None
    editeur: str
    date: date | None
    isbn: str | None   # ISBN-13 valide seulement
    pages: int | None


@dataclass
class Livre:
    slug: str
    titre_brut: str
    auteurs: list[str]
    annee: int | None = None
    resume: str = ""
    couverture: str = ""
    note: float | None = None          # sur 20
    serie: str = ""
    tome_label: str = ""               # « 2 », « HS 3 »
    tomes_principaux: list[float] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    lectorat: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    editions: list[Edition] = field(default_factory=list)
    isbn_page: str | None = None
    titre_vo: str = ""

    # -- Numéro de tome pour Calibre --------------------------------------
    def serie_index(self, mode_hs: str = "apres") -> float | None:
        lab = self.tome_label.strip()
        if not lab:
            return None
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)", lab)
        if m:
            return float(m.group(1).replace(",", "."))
        m = re.fullmatch(r"HS\s*(\d+)", lab, re.I)
        if m:
            n = int(m.group(1))
            if mode_hs == "zero":
                return round(n / 10, 2) if n < 10 else round(n / 100, 3)
            if mode_hs == "aucun":
                return None
            base = max(self.tomes_principaux) if self.tomes_principaux else 0
            return base + (round(n / 10, 2) if n < 10 else round(n / 100, 3))
        return None

    def est_hors_serie(self) -> bool:
        return self.tome_label.upper().startswith("HS")

    # -- Choix de l'édition ------------------------------------------------
    def choisir_edition(self, isbn_voulu: str | None = None, preference: str = "ancienne") -> Edition | None:
        if not self.editions:
            return None
        if isbn_voulu:
            v = isbn_valide(isbn_voulu)
            for e in self.editions:
                if v and e.isbn == v:
                    return e
        fr = self._editions_fr()
        if preference == "ebook":
            eb = [e for e in self.editions if e.type == "E" and e.langue == "fr"]
            fr = eb or fr
        fr = [e for e in fr if e.isbn] or fr          # éditeur et ISBN viennent de la même édition
        if preference == "recente":
            return max(fr, key=lambda e: (e.annee or 0, e.date or date(1, 1, 1)))
        return min(fr, key=lambda e: (e.annee or 9999, e.date or date(9999, 12, 31)))

    def premiere_parution(self) -> date | None:
        """Date de la 1re édition française (même sans ISBN)."""
        fr = [e for e in self._editions_fr() if e.annee or e.date]
        if not fr:
            return date(self.annee, 1, 1) if self.annee else None
        e = min(fr, key=lambda e: (e.annee or 9999, e.date or date(9999, 12, 31)))
        return e.date or date(e.annee, 1, 1)

    def _editions_fr(self) -> list[Edition]:
        fr_papier = [e for e in self.editions if e.type == "L" and e.langue == "fr"]
        return fr_papier or [e for e in self.editions if e.langue == "fr" and e.type != "A"] or self.editions

    def isbn_pour(self, ed: Edition | None) -> str | None:
        """ISBN de l'édition choisie ; sinon une autre édition FR du même éditeur ; sinon n'importe laquelle."""
        if ed and ed.isbn:
            return ed.isbn
        fr = self._editions_fr()
        if ed:
            meme = [e for e in fr if e.isbn and e.editeur.split(" (")[0] == ed.editeur.split(" (")[0]]
            if meme:
                return min(meme, key=lambda e: e.annee or 9999).isbn
        return next((e.isbn for e in sorted(fr, key=lambda e: e.annee or 9999) if e.isbn), None) or self.isbn_page

    def tous_isbn(self) -> list[str]:
        out = [e.isbn for e in self.editions if e.isbn]
        if self.isbn_page:
            out.append(self.isbn_page)
        return list(dict.fromkeys(out))


def nom_editeur(brut: str) -> str:
    """« Editions du Masque » → « Le Masque », « Editions de l'Olivier » → « L'Olivier », « Editions J'ai Lu » → « J'ai Lu »."""
    s = re.sub(r"^[ÉE]ditions\s+", "", (brut or "").strip())
    for art, rempl in (("du ", "Le "), ("de la ", "La "), ("des ", "Les "), ("de l'", "L'"), ("de l’", "L'"), ("de ", "")):
        if s.lower().startswith(art):
            reste = s[len(art):]
            return rempl + reste if rempl else reste
    return s


def _parse_date(txt: str) -> date | None:
    m = _DATE_RE.match(txt.strip())
    if not m:
        return None
    mois = _MOIS.get(m.group(2).lower())
    if not mois:
        return None
    return date(int(m.group(3)), mois, int(m.group(1) or 1))


def _parse_edition(bloc) -> Edition:
    classes = bloc.get("class", [])
    typ = next((c[6:] for c in classes if c.startswith("etype_")), "")
    langue = next((c[6:] for c in classes if c.startswith("elang_")), "")
    an = bloc.select_one(".year")
    ed = bloc.select_one("a.editeur")
    editeur = nom_editeur(_texte(ed))
    dt, isbn, pages = None, None, None
    for p in bloc.select(".edi_infos_general p"):
        t = _texte(p)
        if t.upper().startswith("ISBN"):
            isbn = isbn_valide(t.split(":", 1)[-1])
        elif re.fullmatch(r"\d+\s+pages?", t):
            pages = int(t.split()[0])
        elif dt is None:
            dt = _parse_date(t)
    annee = int(_texte(an)) if an and _texte(an).isdigit() else None
    return Edition(typ, langue, annee, editeur, dt, isbn, pages)


def parse_livre(html, slug: str = "") -> Livre | None:
    soup = _soup(html)
    titre_el = soup.select_one(".header_book_title")
    if not titre_el:
        return None
    if not slug:
        can = soup.select_one("link[rel=canonical]")
        slug = slug_de_url(can.get("href", "")) if can else ""
    auteurs = [_texte(a) for a in soup.select(".header_book_authors a")] or \
              [_texte(soup.select_one(".header_book_authors"))]
    an = _texte(soup.select_one(".header_book_year"))
    livre = Livre(slug=slug or "", titre_brut=_texte(titre_el), auteurs=[a for a in auteurs if a],
                  annee=int(an) if an.isdigit() else None)

    # JSON-LD (résumé propre, ISBN, image)
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.string or "")
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Book":
            livre.isbn_page = isbn_valide(str(data.get("isbn", "")))
            livre.couverture = data.get("image") or ""

    syn = soup.select_one(".synopsis_content")
    if syn:
        for p in syn.select(".book_original_title"):
            livre.titre_vo = re.sub(r"^\s*Titre original\s*:\s*", "", _texte(p))
            p.extract()
        for sp in syn.find_all("span", recursive=False):      # notes du site (« réédité … ici »)
            if re.search(r"r[ée]?[ée]dit|version augment|voir ici", _texte(sp), re.I):
                sp.extract()
        for a in syn.select("a"):
            a.unwrap()
        html_syn = syn.decode_contents().strip()
        html_syn = re.sub(r"(<br\s*/?>\s*)+$", "", html_syn)
        if html_syn:
            paras = [x.strip() for x in re.split(r"<br\s*/?>", html_syn) if x.strip()]
            livre.resume = "".join(f"<p>{x}</p>" for x in paras)

    cov = soup.select_one(".book_cover a[href]")
    if cov:
        livre.couverture = cov["href"]
    if not livre.couverture:
        og = soup.select_one('meta[property="og:image"]')
        livre.couverture = og.get("content", "") if og else ""

    note = soup.select_one(".displayMoyenne .displayNoteNote") or soup.select_one(".displayNoteNote")
    try:
        livre.note = float(_texte(note).replace(",", ".")) if note else None
    except ValueError:
        livre.note = None

    saga = soup.select_one(".portlet-saga")
    if saga:
        a = saga.select_one("a[href*='saga-']")
        livre.serie = _texte(a)
        cur = saga.select_one(".tome_current")
        livre.tome_label = _texte(cur)
        for t in saga.select(".pagination-saga a"):
            lab = _texte(t)
            if re.fullmatch(r"\d+(?:[.,]\d+)?", lab):
                livre.tomes_principaux.append(float(lab.replace(",", ".")))

    for a in soup.select("a[href*='toplivres.php']"):
        href, t = a.get("href", ""), _texte(a)
        if not t:
            continue
        if "g=" in href and t not in livre.genres:
            livre.genres.append(t)
        elif "lectorat=" in href and t not in livre.lectorat:
            livre.lectorat.append(t)
        elif "tag=" in href and t not in livre.themes:
            livre.themes.append(t)

    livre.editions = [_parse_edition(b) for b in soup.select("#editions .editionBlock")]
    return livre


# ─────────────────────────────────────────────────────────────────────────────
# Classement des résultats
# ─────────────────────────────────────────────────────────────────────────────

def score(res: Resultat, titre: str, auteurs: list[str], tome: int | None = None) -> float:
    """Plus haut = meilleur. -1 si l'auteur ne correspond pas."""
    if auteurs:
        voulu = set().union(*(mots(a) for a in auteurs))
        trouve = set().union(*(mots(a) for a in res.auteurs)) if res.auteurs else set()
        if trouve and voulu and not voulu & trouve:
            return -1.0
    t_voulu, t_res = mots(titre), mots(res.titre)
    if not t_voulu:
        return 0.5
    commun = len(t_voulu & t_res) / len(t_voulu)
    bonus = 0.5 if cle(titre) and cle(titre) in cle(res.titre) else 0.0
    malus = 0.02 * max(0, len(t_res) - len(t_voulu))   # préfère les titres courts
    if tome is not None:
        n = numero_tome(res.titre)
        if n == tome:
            bonus += 0.3
        elif n is not None:
            malus += 0.4
    return commun + bonus - malus
