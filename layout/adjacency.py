def get_room_adjacency_preferences(room_type):
    """
    Returns the preferred adjacency for a given room type.
    """
    prefs = {
        "hall": ["entrance", "bedroom", "kitchen", "bathroom", "pooja", "dining", "parking"],
        "kitchen": ["hall", "dining"],
        "bedroom": ["hall"],
        "bathroom": ["hall", "bedroom"],
        "pooja": ["hall"],
        "parking": ["entrance"],
        "dining": ["kitchen", "hall"],
        "utility": ["kitchen", "bathroom"]
    }
    return prefs.get(room_type, ["hall"])
