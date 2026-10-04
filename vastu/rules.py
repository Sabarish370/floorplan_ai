from typing import List, Dict, Any

VASTU_RULES: List[Dict[str, Any]] = [
    {
        "id": "pooja_zone",
        "room_type": "pooja",
        "preferred_zones": ["NE"],
        "acceptable_zones": ["E", "N"],
        "avoid_zones": ["SW", "S"],
        "severity": "preference",
        "weight": 15
    },
    {
        "id": "kitchen_zone",
        "room_type": "kitchen",
        "preferred_zones": ["SE"],
        "acceptable_zones": ["NW"],
        "avoid_zones": [],
        "severity": "preference",
        "weight": 15
    },
    {
        "id": "master_bedroom_zone",
        "room_type": "master_bedroom",
        "preferred_zones": ["SW"],
        "acceptable_zones": [],
        "avoid_zones": [],
        "severity": "preference",
        "weight": 15
    },
    {
        "id": "bedroom_zone",
        "room_type": "bedroom",
        "preferred_zones": ["SW"],
        "acceptable_zones": ["NW", "W", "S"],
        "avoid_zones": [],
        "severity": "preference",
        "weight": 10
    },
    {
        "id": "bathroom_avoid_zones",
        "room_type": "bathroom",
        "preferred_zones": ["NW", "W", "S"],
        "acceptable_zones": ["SE", "E"],
        "avoid_zones": ["NE", "CENTER"],
        "severity": "preference",
        "weight": 15
    },
    {
        "id": "hall_zone",
        "room_type": "hall",
        "preferred_zones": ["NE", "N", "E", "CENTER"],
        "acceptable_zones": [],
        "avoid_zones": [],
        "severity": "preference",
        "weight": 10
    },
    {
        "id": "parking_zone",
        "room_type": "parking",
        "preferred_zones": ["NW", "SE", "NE"],
        "acceptable_zones": [],
        "avoid_zones": [],
        "severity": "preference",
        "weight": 10
    }
]
