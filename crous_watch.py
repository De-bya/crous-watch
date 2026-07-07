#!/usr/bin/env python3
"""
Surveillance des logements CROUS pour des villes cibles.

Compare les logements actuellement en ligne sur trouverunlogement.lescrous.fr
avec ceux déjà vus lors du dernier passage (fichier seen.json), et envoie une
notification (ntfy.sh) pour chaque nouveau logement détecté.
"""

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration — à adapter à tes besoins
# ---------------------------------------------------------------------------

# Villes à surveiller (insensible aux accents/majuscules)
# TARGET_CITIES = ["Montpellier", "Nimes", "Perpignan"]

# ID(s) d'outil du site CROUS à surveiller.
# 45 = offre restante 2026-2027 (phase complémentaire, ouverte depuis le 7 juillet 2026)
# 42 = offre 2025-2026 (fin de l'année en cours)
TOOL_IDS = [45]

BASE_URL = "https://trouverunlogement.lescrous.fr"
STATE_FILE = Path(__file__).parent / "seen.json"
MAX_PAGES = 30          # garde-fou pour ne pas boucler indéfiniment
REQUEST_DELAY = 2.0     # secondes entre deux requêtes (politesse envers le site)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CrousWatch/1.0; +https://github.com/)"
}

ACCOMMODATION_RE = re.compile(r"/tools/(\d+)/accommodations/(\d+)")

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalized(text: str) -> str:
    return strip_accents(text).lower()

def extract_city(text: str) -> str:
    """
    Extrait la ville à partir du texte d'un logement.

    Cherche un code postal français suivi du nom de la ville,
    par exemple :
        34000 Montpellier
        30000 Nîmes
        66100 Perpignan
    """
    text = re.sub(r"\s+", " ", text)

    m = re.search(r"\b\d{5}\s+([A-Za-zÀ-ÿ' -]+)", text)
    if m:
        city = m.group(1).strip()

        # Nettoyage : on s'arrête avant certains mots fréquents
        city = re.split(
            r"\b(Résidence|Residence|Loyer|Studio|T1|T2|Appartement|Chambre)\b",
            city,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" ,-")

        return city

    return "Ville inconnue"

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Récupération et parsing des pages
# ---------------------------------------------------------------------------


def fetch_page(tool_id: int, page: int):
    url = f"{BASE_URL}/tools/{tool_id}/search"
    params = {"page": page} if page > 1 else {}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"  ... erreur réseau ({e}), nouvelle tentative", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
            continue
        if resp.status_code == 200 and "trop nombreux" not in resp.text.lower():
            return resp.text
        wait = 15 * (attempt + 1)
        print(
            f"  ... réponse inattendue (status={resp.status_code}), pause {wait}s",
            file=sys.stderr,
        )
        time.sleep(wait)
    return None


def parse_listings(html: str, tool_id: int):
    """Extrait les logements présents sur une page de résultats correspondant
    aux villes cibles.

    Retourne une liste de dicts: {id, url, city, text}
    """
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    seen_ids_on_page = set()

    for link in soup.find_all("a", href=True):
        m = ACCOMMODATION_RE.search(link["href"])
        if not m or int(m.group(1)) != tool_id:
            continue
        acc_id = m.group(2)
        if acc_id in seen_ids_on_page:
            continue
        seen_ids_on_page.add(acc_id)

        # Remonte dans l'arbre HTML pour capturer le bloc contenant l'adresse
        # et le prix affichés autour du lien.
        container = link
        text = ""
        for _ in range(4):
            if container.parent is None:
                break
            container = container.parent
            text = container.get_text(" ", strip=True)
            if len(text) > 40:
                break

        city = extract_city(text)

        listings.append(
            {
                "id": acc_id,
                "url": f"{BASE_URL}/tools/{tool_id}/accommodations/{acc_id}",
                "city": city,
                "text": text[:300],
            }
        )


    return listings


def has_next_page(html: str) -> bool:
    norm = normalized(html)
    m = re.search(r"page (\d+) sur (\d+)", norm)
    if m:
        current, total = int(m.group(1)), int(m.group(2))
        return current < total
    return False


def scan_tool(tool_id: int):
    results = {}
    for page in range(1, MAX_PAGES + 1):
        print(f"[tool {tool_id}] page {page}...")
        html = fetch_page(tool_id, page)
        if html is None:
            print(
                f"[tool {tool_id}] page {page} inaccessible, arrêt de ce tool.",
                file=sys.stderr,
            )
            break

        for item in parse_listings(html, tool_id):
            results[item["id"]] = item

        if not has_next_page(html):
            break
        time.sleep(REQUEST_DELAY)

    return results


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


def notify(new_listings):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC non configuré — pas de notification envoyée (voir README).")
        return
    for item in new_listings:
        title = f"Nouveau logement CROUS - {item['city']}"
        body = f"{item['text']}\n{item['url']}"
        try:
            requests.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=body.encode("utf-8"),
                headers={
                    "Title": title.encode("utf-8"),
                    "Click": item["url"],
                    "Tags": "house",
                },
                timeout=10,
            )
        except requests.RequestException as e:
            print(f"Échec d'envoi de la notification: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    state = load_state()
    all_current = {}

    for tool_id in TOOL_IDS:
        all_current.update(scan_tool(tool_id))

    previous_ids = set(state.keys())
    current_ids = set(all_current.keys())
    new_ids = current_ids - previous_ids

    new_listings = [all_current[i] for i in new_ids]

    if new_listings:
        print(f"{len(new_listings)} nouveau(x) logement(s) trouvé(s) !")
        for item in new_listings:
            print(f"  - [{item['city']}] {item['url']}")
        notify(new_listings)
    else:
        print("Aucun nouveau logement pour l'instant.")

    save_state(all_current)


if __name__ == "__main__":
    main()
