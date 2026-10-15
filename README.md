# Planificateur de championnat

Génère le calendrier des championnats de l'AVLI par optimisation sous contraintes.

À partir de la liste des équipes, des dates disponibles et des indisponibilités de chacune, l'outil propose un calendrier qui indique pour chaque date :

- les deux équipes qui s'affrontent,
- l'équipe qui organise la soirée.

> 🚧 Projet en cours de démarrage. Le solveur n'est pas encore choisi : [Google OR-Tools](https://developers.google.com/optimization) (CP-SAT) ou [Timefold](https://timefold.ai/).

## Le problème

Une saison typique, c'est :

- **11 équipes**, chacune joue **4 matchs** ;
- **22 dates**, avec **un match par date** ;
- chaque équipe **organise 2 soirées** dans la saison.

### Contraintes obligatoires

Un calendrier qui ne respecte pas ces règles est refusé.

| Contrainte                | Description                                                                       |
| ------------------------- | --------------------------------------------------------------------------------- |
| Nombre de matchs          | Chaque équipe joue exactement le nombre de matchs prévu.                          |
| Pas de match à double     | Deux équipes ne se rencontrent qu'une seule fois.                                 |
| Indisponibilités          | Une équipe indisponible à une date ne peut ni jouer ni organiser ce jour-là.      |
| Présences imposées        | Une équipe peut être obligée de jouer à une date (p. ex. un lieu précis).         |
| Rencontres interdites     | Certaines paires d'équipes ne doivent pas s'affronter.                            |
| Matchs déjà fixés         | Des matchs décidés à l'avance sont repris tels quels.                             |
| Organisation              | L'équipe qui organise ne joue pas ce soir-là, et chaque équipe organise autant.   |
| Repos minimum             | Au moins 7 jours entre deux engagements (jouer ou organiser) d'une même équipe.   |
| Charge sur 31 jours       | Pas plus de 2 matchs pour une équipe sur une période de 31 jours.                 |

### Objectifs à optimiser

Parmi les calendriers valides, on cherche le meilleur :

- **Répartition régulière** : les matchs d'une équipe sont étalés sur la saison, sans tout jouer en novembre puis attendre jusqu'en avril.
- **Écart maximal** : l'écart le plus court entre deux engagements d'une même équipe est le plus grand possible.

## Utilisation

_À venir._

L'idée :

1. décrire la saison dans un fichier de configuration (équipes, dates, contraintes) ;
2. lancer le solveur ;
3. récupérer le calendrier dans un tableau (Markdown / CSV) prêt à être envoyé aux équipes.

## Feuille de route

- [ ] Choisir le solveur (OR-Tools ou Timefold)
- [ ] Définir le format du fichier de configuration
- [ ] Modéliser les contraintes obligatoires
- [ ] Ajouter les objectifs d'optimisation
- [ ] Exporter le calendrier (Markdown, CSV)
- [ ] Reprendre la saison 2025-2026 comme cas de test

## Historique

Ce projet remplace [championnat-avli](https://github.com/benoituffer/championnat-avli), une première version en PHP qui générait des milliers de calendriers aléatoires et gardait le meilleur. Le passage à un solveur de contraintes doit permettre de trouver directement un calendrier optimal et d'ajouter facilement de nouvelles règles.
