
# config.py

# Alpha/Beta Ratios for different organs
# Based on EMBRACE II protocols
alpha_beta_ratios = {
    "Bladder": 3,
    "Rectum": 3,
    "Sigmoid": 3,
    "Bowel": 3,
    "Vagina": 3,
    "Uterus": 3,
    "Cervix": 8,
    "CTV-HR": 8,
    "CTV-IR": 8,
    "Default": 3  # Default value for any other structures
}

# EMBRACE II Constraints
# TODO: Add constraints for different organs
constraints = {
    "Bladder": {
        "BED": {"max": 133.33, "unit": "Gy"},
        "EQD2": {"max": 80.0, "unit": "Gy"}
    },
    "Rectum": {
        "BED": {"max": 116.67, "unit": "Gy"},
        "EQD2": {"max": 70.0, "unit": "Gy"}
    },
    "Sigmoid": {
        "BED": {"max": 116.67, "unit": "Gy"},
        "EQD2": {"max": 70.0, "unit": "Gy"}
    },
    "Bowel": {
        "BED": {"max": 108.33, "unit": "Gy"},
        "EQD2": {"max": 65.0, "unit": "Gy"}
    }
}
