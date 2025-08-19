# config.py

templates = {
    "Cervix HDR - EMBRACE II": {
        "alpha_beta_ratios": {
            "Bladder": 3,
            "Rectum": 3,
            "Sigmoid": 3,
            "Bowel": 3,
            "Vagina": 3,
            "Uterus": 3,
            "Cervix": 10,
            "HRCTV": 10,
            "GTV": 10,
            "Default": 3
        },
        "constraints": {
            "HRCTV D90": {"min": 85.0, "max": 90.0, "unit": "Gy"},
            "HRCTV D98": {"min": 75.0, "unit": "Gy"},
            "GTV D98": {"min": 95.0, "unit": "Gy"},
            "Bladder": {"D2cc": {"max": 80.0, "unit": "Gy"}},
            "Rectum": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
            "Sigmoid": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
            "Bowel": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}}
        }
    },
    "Custom": {
        "alpha_beta_ratios": {
            "Bladder": 3,
            "Rectum": 3,
            "Sigmoid": 3,
            "Bowel": 3,
            "Vagina": 3,
            "Uterus": 3,
            "Cervix": 10,
            "HRCTV": 10,
            "GTV": 10,
            "Default": 3
        },
        "constraints": {
            "Bladder": {"D2cc": {"max": 80.0, "unit": "Gy"}},
            "Rectum": {"D2cc": {"max": 70.0, "unit": "Gy"}},
            "Sigmoid": {"D2cc": {"max": 70.0, "unit": "Gy"}},
            "Bowel": {"D2cc": {"max": 65.0, "unit": "Gy"}}
        }
    }
}

# Default to EMBRACE II template
alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]
constraints = templates["Cervix HDR - EMBRACE II"]["constraints"]