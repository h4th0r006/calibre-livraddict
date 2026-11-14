from queue import Queue
from threading import Event

from calibre_plugins.livraddict.parser import isbn_valide, nettoyer_titre, nom_editeur


def identify(plugin, log, title, authors, identifiers=None):
    q = Queue()
    plugin.identify(log, q, Event(), title=title, authors=authors, identifiers=identifiers or {})
    out = []
    while not q.empty():
        out.append(q.get())
    return out


# ── recherche ───────────────────────────────────────────────────────────────

def test_titre_avec_prefixe_tome_et_filtre_auteur(plugin, log):
    res = identify(plugin, log, "T2 - L'insurrection", ["Veronica Roth"])
    assert len(res) == 1
    assert res[0].identifiers["livraddict"].startswith("divergent-divergente-divergence-tome-2")


def test_plan_b_bibliographie_auteur(plugin, log):
    res = identify(plugin, log, "Marquer les ombres, tome 2", ["Veronica Roth"])
    assert res and res[0].identifiers["livraddict"] == "marquer-les-ombres-tome-2"


def test_cache_isbn_evite_la_recherche(plugin, log):
    plugin._fiche(log, "divergente-raconte-par-quatre", None, 30)
    plugin.browser.visited.clear()
    identify(plugin, log, "x", [], {"isbn": "9782266316866"})
    assert plugin.browser.visited == ["/biblio/livre/divergente-raconte-par-quatre.html"]


# ── fiche livre ─────────────────────────────────────────────────────────────

def test_fiche_tome(plugin, log):
    mi = plugin._fiche(log, "marquer-les-ombres-tome-2", None, 30)
    assert (mi.title, mi.series, mi.series_index) == ("Marquer les ombres", "Marquer les ombres", 2.0)
    # éditeur et ISBN de la même édition, date = 1re parution française
    assert (mi.publisher, mi.isbn) == ("Pocket (Jeunesse)", "9782266304955")
    assert str(mi.pubdate.date()) == "2018-10-11"
    assert mi.rating == 4.0
    assert mi.comments.startswith("<p>") and "Titre original" not in mi.comments
    assert plugin.get_cached_cover_url({"livraddict": "marquer-les-ombres-tome-2"}).endswith("couv26434318.jpg")


def test_hors_serie(plugin, log):
    mi = plugin._fiche(log, "divergente-raconte-par-quatre", None, 30)
    assert mi.series == "Divergente / Divergence" and mi.series_index == 3.3
    assert "réédité" not in mi.comments and "<a" not in mi.comments
    assert {"Science-Fiction", "Young Adult", "Dystopie"} <= set(mi.tags)


def test_options_hors_serie_et_edition(plugin, log):
    plugin.prefs["hors_serie"] = "zero"
    assert plugin._fiche(log, "divergente-raconte-par-quatre", None, 30).series_index == 0.3
    plugin.prefs["hors_serie"] = "aucun"
    assert plugin._fiche(log, "divergente-raconte-par-quatre", None, 30).series is None
    plugin.prefs.update(hors_serie="apres", edition="recente")
    mi = plugin._fiche(log, "divergente-raconte-par-quatre", None, 30)
    assert (mi.publisher, mi.isbn) == ("Pocket (Jeunesse - Best seller)", "9782266316866")


def test_premiere_edition_sans_isbn(plugin, log):
    mi = plugin._fiche(log, "noirs-tatouages", None, 30)
    assert (mi.publisher, mi.isbn, mi.pubdate.year) == ("J'ai Lu", "9782290014509", 2008)


# ── fonctions utilitaires ───────────────────────────────────────────────────

def test_utilitaires():
    assert isbn_valide("972092580202") is None
    assert isbn_valide("2-266-30495-X") == "9782266304955"
    assert nettoyer_titre("Divergent / Divergente / Divergence, tome 2 : Insurgés / L'insurrection",
                          "Divergente") == "Insurgés / L'insurrection"
    assert [nom_editeur(x) for x in ("Editions du Masque", "Editions de l'Olivier", "Editions de Minuit")] \
        == ["Le Masque", "L'Olivier", "Minuit"]
