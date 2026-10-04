ARCHITECTURAL_CONFIG = {
    "room_realism": {
        "bedroom": {
            "min_width": 10, "max_width": 20,
            "min_depth": 10, "max_depth": 20,
            "min_area": 120, "max_area": 300,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.0
        },
        "hall": {
            "min_width": 10, "max_width": 25,
            "min_depth": 10, "max_depth": 25,
            "min_area": 150, "max_area": 400,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.5
        },
        "kitchen": {
            "min_width": 7, "max_width": 18,
            "min_depth": 7, "max_depth": 18,
            "min_area": 60, "max_area": 220,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.0
        },
        "bathroom": {
            "min_width": 5, "max_width": 15,
            "min_depth": 5, "max_depth": 15,
            "min_area": 35, "max_area": 120,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.5
        },
        "pooja": {
            "min_width": 4, "max_width": 12,
            "min_depth": 4, "max_depth": 12,
            "min_area": 20, "max_area": 100,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.0
        },
        "parking": {
            "min_width": 9, "max_width": 20,
            "min_depth": 16, "max_depth": 25,
            "min_area": 140, "max_area": 500,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 3.0
        },
        "dining": {
            "min_width": 8, "max_width": 18,
            "min_depth": 8, "max_depth": 18,
            "min_area": 80, "max_area": 200,
            "min_aspect_ratio": 1.0, "max_aspect_ratio": 2.0
        }
    },
    "weights": {
        "vastu": 0.20,
        "architecture": 0.45,
        "space": 0.25,
        "compactness": 0.10
    }
}
