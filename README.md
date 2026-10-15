# Planificateur de championnat

Génère le calendrier des championnats de l'AVLI par optimisation sous contraintes, avec le solveur [Google OR-Tools](https://developers.google.com/optimization) (CP-SAT).

À partir de la liste des équipes, des dates disponibles et des indisponibilités de chacune, l'outil propose un calendrier qui indique pour chaque date :

- les deux équipes qui s'affrontent,
- l'équipe qui organise la soirée.

## Le problème

Une saison typique, c'est :

- **11 équipes**, chacune joue **4 matchs** ;
- **22 dates**, avec **un match par date** ;
- chaque équipe **organise 2 soirées** dans la saison.

Tous ces nombres viennent du fichier de configuration de la saison.

Dans toute la suite, un **engagement** désigne une soirée où une équipe est mobilisée : elle **joue** ou elle **organise**.

### Contraintes obligatoires

Un calendrier qui ne respecte pas ces règles est refusé.

| Contrainte            | Description                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------- |
| Nombre de matchs      | Chaque équipe joue exactement le nombre de matchs prévu.                                          |
| Pas de match à double | Deux équipes se rencontrent au plus une fois.                                                     |
| Indisponibilités      | Une équipe indisponible à une date n'a aucun engagement ce jour-là.                               |
| Présences imposées    | Une équipe peut être obligée de jouer à une date (p. ex. un lieu précis).                         |
| Rencontres interdites | Certaines paires d'équipes ne doivent pas s'affronter.                                            |
| Rencontres imposées   | Certaines paires d'équipes doivent s'affronter une fois ; le solveur choisit la date.             |
| Matchs déjà fixés     | Des matchs décidés à l'avance (paire + date, organisatrice facultative) sont repris tels quels.   |
| Organisation          | L'équipe qui organise ne joue pas ce soir-là, et chaque équipe organise autant de fois.           |
| Charge d'engagements  | Au plus 3 engagements par équipe sur toute période de 7 jours (configurable).                     |
| Charge de matchs      | Au plus 2 matchs par équipe sur toute période de 31 jours (configurable).                         |

Si tous les matchs sont fixés, le solveur n'attribue que les organisatrices. Les événements hors championnat (Case XP, galas…) ne sont pas pris en compte.

### Objectifs à optimiser

Parmi les calendriers valides, on cherche le meilleur. Les objectifs sont traités **dans l'ordre** : chacun est optimisé, puis figé, avant de passer au suivant.

1. **Écart entre engagements** : le plus petit écart (en jours) entre deux engagements d'une même équipe est le plus grand possible.
2. **Écart entre matchs** : même chose pour les seuls matchs.
3. **Départage par équipe** : la somme, sur toutes les équipes, de leur plus petit écart entre engagements, puis entre matchs, est la plus grande possible. Sans ce critère, une seule équipe coincée par ses indisponibilités fixe l'écart minimal, et le solveur ne fait plus d'effort pour les autres.
4. **Répartition régulière** : les matchs de chaque équipe sont étalés sur la saison. Le k-ième match d'une équipe devrait idéalement tomber à k × durée / (N + 1) jours du début ; on minimise l'écart total à ces positions idéales.

### Quand aucun calendrier n'existe

L'outil ne se contente pas de répondre « impossible » :

1. il signale les contradictions évidentes : une date où trop peu d'équipes sont disponibles, une présence imposée sur une indisponibilité, des dates trop rapprochées pour le nombre d'équipes… ;
2. il cherche le **plus petit nombre de contraintes à ignorer** (indisponibilités, présences imposées, rencontres interdites ou imposées, matchs fixés) pour qu'un calendrier existe, et propose jusqu'à trois possibilités. Exemple : « Il suffit d'ignorer 1 contrainte : 1. Équipe A indisponible le 04/12/2025 ; 2. Équipe E indisponible le 04/12/2025… » ;
3. il écrit un **calendrier provisoire** avec la première possibilité, clairement marqué comme tel ;
4. si même en ignorant toutes ces contraintes rien n'est possible, ce sont les dates ou les paramètres qui posent problème : il indique quel plafond de charge assouplir.

## Utilisation

### Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) et Python 3.12 (uv le télécharge si besoin). Dans le devcontainer, tout est installé automatiquement ; sinon :

```bash
uv sync
```

### Décrire la saison

Une saison se décrit dans un fichier YAML. Voir l'exemple complet et commenté : [`exemples/saison-exemple.yaml`](exemples/saison-exemple.yaml).

```yaml
saison: Ligue A — exemple

equipes:
  - Équipe A
  - Équipe B
  # …

parametres:
  matchs_par_equipe: 4
  matchs_par_date: 1               # facultatif, 1 par défaut
  organisations_par_equipe: 2      # facultatif, déduit du nombre de dates
  charge_matchs:                   # au plus 2 matchs sur toute période de 31 jours
    maximum: 2
    jours: 31
  charge_engagements:              # au plus 3 engagements sur toute période de 7 jours
    maximum: 3
    jours: 7

dates:                             # format JJ/MM/AAAA
  - 27/11/2025
  - 04/12/2025

indisponibilites:                  # date → équipes (ni jouer ni organiser)
  27/11/2025: [Équipe A, Équipe B]

presences_imposees:                # date → équipes qui doivent jouer
  04/12/2025: [Équipe C]

rencontres_interdites:
  - [Équipe A, Équipe D]

rencontres_imposees:               # se rencontrent une fois, date libre
  - [Équipe B, Équipe E]

matchs_fixes:
  - date: 04/12/2025
    equipes: [Équipe C, Équipe E]
    organisatrice: Équipe F        # facultatif
```

Les noms d'équipes doivent être écrits **exactement** comme dans `equipes`. En cas de faute de frappe (majuscule, accent, apostrophe…), l'outil s'arrête et propose le nom le plus proche :

```
Configuration invalide (saisons/ma-saison.yaml) :
  - Équipe inconnue « équipe a » dans « indisponibilites › 27/11/2025 ». Vouliez-vous dire « Équipe A » ?
```

> 🔒 **Données réelles** : le dépôt est public. Les fichiers des vraies saisons vont dans `saisons/`, qui est ignoré par git.

### Générer le calendrier

```bash
uv run planificateur saisons/2026-2027.yaml
```

Le calendrier s'affiche et est écrit à côté du fichier YAML :

- `2026-2027-calendrier.md` : tableau Date | Équipe 1 | Équipe 2 | Équipe organisatrice, suivi d'un résumé par équipe (dates, écarts minimaux) ;
- `2026-2027-calendrier.csv` : le même tableau, séparé par des `;` pour Excel ou LibreOffice.

L'outil ne remplace jamais un fichier qu'il n'a pas lui-même généré. Avant d'être écrit, chaque calendrier est revérifié par un validateur indépendant du solveur.

Options :

| Option             | Effet                                                                   |
| ------------------ | ----------------------------------------------------------------------- |
| `--sortie DOSSIER` | écrit les fichiers dans ce dossier                                      |
| `--temps-max S`    | temps de calcul maximal par objectif, en secondes (30 par défaut)       |
| `--graine N`       | graine aléatoire du solveur                                             |

Pour 22 dates et 11 équipes, comptez quelques minutes. L'outil indique pour chaque objectif si la valeur est prouvée optimale ou si c'est la meilleure trouvée dans le temps imparti ; augmenter `--temps-max` peut alors l'améliorer.

## Développement

```bash
uv run pytest          # tests
uv run ruff check      # analyse statique
uv run ruff format     # mise en forme
```

Organisation du code (`src/planificateur/`) :

| Module          | Rôle                                                                     |
| --------------- | ------------------------------------------------------------------------ |
| `config.py`     | lecture et validation du YAML, messages d'erreur                         |
| `noms.py`       | suggestion du nom d'équipe le plus proche                                |
| `modele.py`     | modèle CP-SAT : variables, contraintes, termes des objectifs             |
| `resolution.py` | résolution objectif par objectif                                         |
| `diagnostic.py` | explication des cas impossibles                                          |
| `validateur.py` | vérification indépendante d'un calendrier (sans OR-Tools)                |
| `export.py`     | export Markdown et CSV                                                   |
| `cli.py`        | commande `planificateur`                                                 |

Les tests couvrent chaque contrainte (un cas qui réussit, un cas qui échoue), le validateur sur des calendriers volontairement faux, et comparent les objectifs du solveur à une recherche exhaustive sur un mini-championnat.

## Feuille de route

- [x] Choisir le solveur : OR-Tools (CP-SAT)
- [x] Définir le format du fichier de configuration
- [x] Modéliser les contraintes obligatoires
- [x] Ajouter les objectifs d'optimisation
- [x] Exporter le calendrier (Markdown, CSV)
- [x] Expliquer les cas impossibles
- [x] Reprendre la saison 2025-2026 comme cas de test (exemple anonymisé)
- [x] Générer le calendrier 2026-2027
- [ ] Vérifier un calendrier retouché à la main (`planificateur verifier saison.yaml calendrier.csv`)
- [ ] Accélérer la preuve d'optimalité des objectifs de départage

## Historique

Ce projet remplace [championnat-avli](https://github.com/benoituffer/championnat-avli), une première version en PHP qui générait des milliers de calendriers aléatoires et gardait le meilleur. Le passage à un solveur de contraintes permet de trouver directement un calendrier optimal, d'expliquer pourquoi une saison est impossible et d'ajouter facilement de nouvelles règles.
