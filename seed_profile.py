"""Preload a user's known favourites into the taste profile:  python seed_profile.py --user pranav"""
import argparse

from carnatic.profile import ProfileStore

FAVOURITES = {
    "pranav": [
        "Raghuvamsa Sudha", "Swaminatha Paripalaya", "Vallinayakane", "Endaro Mahanubhavulu", "Odi Baarayya",
        "Nagumomu", "Paramapurusha", "Pibare Rama Rasam", "Vatapi Ganapatim", "Mahaganapatim",
        "Manavyalakinchara", "Bantureeti Kolu",
    ],
}

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--user", default="pranav"); a = p.parse_args()
    store = ProfileStore()
    for title in FAVOURITES.get(a.user, []):
        store.record_feedback(a.user, "krithi", title, 1, "listed as a favourite")
    store.set_preference(a.user, "interests", ["devotional krithis"])
    print(store.get(a.user))
