def normalize_room_name(name: str) -> str:
    name = name.lower().strip()
    synonyms = {
        "prayer room": "pooja",
        "pooja room": "pooja",
        "puja": "pooja",
        "living room": "hall",
        "living area": "hall",
        "lounge": "hall",
        "car parking": "parking",
        "garage": "parking",
        "washroom": "bathroom",
        "toilet": "bathroom",
        "bath": "bathroom",
        "bed room": "bedroom",
        "master bedroom": "bedroom",
    }
    return synonyms.get(name, name)
