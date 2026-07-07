# Crous Watch

Surveille automatiquement le site [trouverunlogement.lescrous.fr](https://trouverunlogement.lescrous.fr)
pour de nouveaux logements dans les villes de ton choix (par défaut : Montpellier,
Nîmes, Perpignan) et t'envoie une notification push gratuite dès qu'un logement
apparaît.

Le script cible par défaut l'outil `45`, qui correspond à l'offre restante pour
l'année universitaire **2026‑2027** (phase complémentaire, ouverte depuis le
7 juillet 2026).

## 1. Créer un "topic" ntfy (2 minutes, gratuit, sans compte)

1. Installe l'app **ntfy** sur ton téléphone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/us/app/ntfy/id1625396347)), ou ouvre https://ntfy.sh dans un navigateur.
2. Choisis un nom de topic **unique et difficile à deviner** (n'importe qui connaissant
   le nom peut lire/envoyer sur ce topic), par exemple : `crous-debya-8f21a`.
3. Abonne-toi à ce topic dans l'app (bouton "Subscribe to topic").

## 2. Créer le dépôt GitHub

1. Crée un nouveau dépôt GitHub (public ou privé — un dépôt public donne des
   minutes Actions illimitées gratuitement).
2. Ajoute-y les fichiers de ce dossier :
   - `crous_watch.py`
   - `.github/workflows/crous-watch.yml`
   - `README.md`
3. Dans **Settings → Secrets and variables → Actions → New repository secret** :
   - Nom : `NTFY_TOPIC`
   - Valeur : le nom de topic choisi à l'étape 1 (ex. `crous-debya-8f21a`)

## 3. Activer et tester

1. Va dans l'onglet **Actions** du dépôt, active les workflows si demandé.
2. Sélectionne **Crous Watch** puis clique sur **Run workflow** pour lancer un
   premier test manuel.
3. Vérifie les logs : tu devrais voir le nombre de pages parcourues et,
   éventuellement, les logements déjà en ligne (le premier passage remplit
   juste `seen.json`, sans notification — c'est normal, tout est "déjà vu").
4. Les passages suivants (automatiques, toutes les 20 min) ne notifieront que
   les **nouveaux** logements.

## 4. Personnaliser

Dans `crous_watch.py` :

```python
TARGET_CITIES = ["Montpellier", "Nimes", "Perpignan"]  # ajoute/retire des villes
TOOL_IDS = [45]  # ajoute 42 pour surveiller aussi l'offre 2025-2026
```

## Tester en local (optionnel)

```bash
pip install requests beautifulsoup4
export NTFY_TOPIC="ton-topic"
python crous_watch.py
```

## Limites à connaître

- Le site limite parfois l'accès ("Vous êtes trop nombreux !") en cas de forte
  affluence : le script réessaie automatiquement avec des pauses.
- La structure HTML du site peut changer sans préavis ; si le script ne trouve
  plus rien, c'est le premier endroit à vérifier.
- Un intervalle de 20 minutes est un bon compromis. Ne descends pas trop bas
  (< 10 min) pour rester respectueux envers le site.
