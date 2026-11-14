# Livraddict — source de métadonnées pour Calibre

Plugin [Calibre](https://calibre-ebook.com) qui télécharge les métadonnées et les couvertures depuis
[Livraddict](https://www.livraddict.com), le réseau social de lecteurs francophones.

## Ce que le plugin récupère

| Champ Calibre | Source sur Livraddict |
|---|---|
| Titre | Titre de la fiche, nettoyé (« Saga, tome 2 : Titre » → « Titre ») |
| Auteurs | Auteurs de la fiche |
| Série / numéro | Bloc « Saga » ; les hors-séries « HS n » sont numérotés 3.1, 3.2… (réglable) |
| Résumé | Synopsis, en paragraphes, sans les notes du site |
| Éditeur / ISBN | Toujours issus de la **même édition** française (par défaut la plus ancienne ayant un ISBN) |
| Date de publication | 1re parution française |
| Tags | Genres, lectorat (Young Adult, Adulte…) et thèmes (Dystopie…) |
| Note | Moyenne sur 20 convertie sur 5 |
| Couverture | Image en grand format |
| Identifiants | `livraddict:<slug>`, `isbn:` |

## Installation

1. Télécharger `livraddict-x.y.z.zip` dans les [Releases](../../releases).
2. Calibre → **Préférences → Extensions → Charger une extension à partir d'un fichier** → choisir le zip.
3. Redémarrer Calibre.
4. **Préférences → Téléchargement des métadonnées** → cocher **Livraddict**.

Aucune clé ni cookie n'est nécessaire.

## Options (bouton « Configurer »)

- Nombre de fiches examinées (3 par défaut) et délai entre requêtes (1,5 s)
- Nettoyage du titre
- Édition retenue : la plus ancienne, la plus récente ou l'ebook français
- Numérotation des hors-séries : après les tomes, avant (0.x) ou sans série
- Ajout du lectorat, des thèmes et du titre original

## Limites connues

- La recherche de Livraddict ne fonctionne qu'avec le **titre** (ni ISBN, ni « titre + auteur »).
  Le plugin cherche donc par titre, garde les résultats du bon auteur, et consulte la bibliographie
  de l'auteur en dernier recours. Les ISBN rencontrés sont mémorisés pour les recherches suivantes.
- Deux tomes au titre identique (« Marquer les ombres » T1 et T2) ne sont distingués que si le
  numéro figure dans le titre recherché (« Marquer les ombres, tome 2 » ou « T2 - … »).
- Le plugin lit les pages publiques du site : une refonte de Livraddict peut le casser.

## Développement

```bash
pip install pytest beautifulsoup4
pytest                 # tests avec un faux Calibre et des pages enregistrées (résumés anonymisés)
python build.py        # → dist/livraddict-<version>.zip
```

Test contre le vrai site, dans Calibre (Calibre fermé) :

```bash
cd src
calibre-debug -e __init__.py
```

Installation rapide pendant le développement :

```bash
calibre-customize -b src
```

## Usage responsable

Le plugin fait peu de requêtes, espacées d'au moins 1,5 s, uniquement quand vous lancez une
recherche dans Calibre. Merci de ne pas réduire ce délai, pour respecter le site et sa communauté.
Ce projet n'est pas affilié à Livraddict.

## Licence

GPL v3, comme Calibre (voir [LICENSE](LICENSE)).
