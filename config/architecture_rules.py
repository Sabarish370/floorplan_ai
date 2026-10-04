ADJACENCY_PREFERENCES = {
    "hall": {
        "bedroom": "preferred",
        "kitchen": "preferred",
        "bathroom": "preferred",
        "pooja": "preferred",
        "dining": "preferred",
    },
    "kitchen": {
        "hall": "preferred",
        "dining": "preferred",
    },
    "pooja": {
        "hall": "preferred",
    },
    "bedroom": {
        "bedroom": "neutral",
        "bathroom": "acceptable",
    },
    "bathroom": {
        "hall": "acceptable",
        "bedroom": "preferred",
        "kitchen": "avoid",
    }
}

PASSAGE_POLICY = {
    "hall": {"can_be_passage": True},
    "dining": {"can_be_passage": True},
    "living": {"can_be_passage": True},
    "kitchen": {"can_be_passage": False},
    "bathroom": {"can_be_passage": False},
    "bedroom": {"can_be_passage": False},
    "pooja": {"can_be_passage": True}, # soft penalty only
    "parking": {"can_be_passage": False},
    "circulation": {"can_be_passage": True},
}

CIRCULATION_CONSTRAINTS = {
    "require_direct_hall_access_for_bedrooms": True,
    "require_direct_hall_access_for_kitchen": True,
    "require_direct_hall_access_for_pooja": False,

    "allow_bathroom_as_passage": False,
    "allow_kitchen_as_passage": False,
    "allow_bedroom_as_passage": False,

    "forbid_mandatory_passage_dependencies": True,
}


PASSAGE_ROOM_PENALTIES = {
    "bedroom": 20,
    "bathroom": 15,
    "kitchen": 15,
    "pooja": 10,
    "hall": 0,
    "dining": 0,
    "circulation": 0,
}

OPTIMIZATION_WEIGHTS = {
    "architecture": 0.45,
    "vastu": 0.20,
    "space_utilization": 0.25,
    "compactness": 0.10,
}
