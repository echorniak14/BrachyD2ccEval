# config.py

templates = {
    "Cervix HDR - EMBRACE II": {
        "plan_type": "Cervix",
        "alpha_beta_ratios": {
            "Bladder": 3,
            "Rectum": 3,
            "Sigmoid": 3,
            "Bowel": 3,
            "Vagina": 3,
            "Uterus": 3,
            "Cervix": 10,
            "Hrctv": 10,
            "Gtv": 10,
            "Default": 3
        },
        "constraints": {
            "target_constraints": {
                "Hrctv D90": {"min": 85.0, "max": 90.0, "unit": "Gy"},
                "Hrctv D98": {"min": 75.0, "unit": "Gy"},
                "Gtv D98": {"min": 95.0, "unit": "Gy"}
            },
            "oar_constraints": {
                "Bladder": {"D2cc": {"max": 80.0, "unit": "Gy"}},
                "Rectum": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
                "Sigmoid": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
                "Bowel": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}}
            }
        },
        "point_dose_constraints": {
            "Point A": {"alpha_beta": 10, "report_only": True},
            "Bladder Point": {"alpha_beta": 3, "report_only": True},
            "RV Point": {"alpha_beta": 3, "max_eqd2": 65.0, "unit": "Gy"},
        }
    },
    "Cervix HDR - ABS/GEC-Estro": {
        "plan_type": "Cervix",
        "alpha_beta_ratios": { # Assuming same as EMBRACE II
            "Bladder": 3,
            "Rectum": 3,
            "Sigmoid": 3,
            "Bowel": 3,
            "Vagina": 3,
            "Uterus": 3,
            "Cervix": 10,
            "Hrctv": 10,
            "Gtv": 10,
            "Default": 3
        },
        "constraints": {
            "target_constraints": {
                "Hrctv D90": {"min": 85.0, "max": 90.0, "unit": "Gy"}, # Same as EMBRACE II
                "Hrctv D98": {"min": 75.0, "unit": "Gy"}, # Same as EMBRACE II
                "Gtv D98": {"min": 95.0, "unit": "Gy"} # Same as EMBRACE II
            },
            "oar_constraints": {
                "Bladder": {"D2cc": {"warning": 80.0, "max": 90.0, "unit": "Gy"}},
                "Rectum": {"D2cc": {"warning": 70.0, "max": 75.0, "unit": "Gy"}},
                "Sigmoid": {"D2cc": {"warning": 70.0, "max": 75.0, "unit": "Gy"}},
                "Bowel": {"D2cc": {"warning": 70.0, "max": 75.0, "unit": "Gy"}}
            }
        },
        "point_dose_constraints": {
            "Point A": {"alpha_beta": 10, "report_only": True},
            "Bladder Point": {"alpha_beta": 3, "report_only": True},
            "RV Point": {"alpha_beta": 3, "max_eqd2": 65.0, "unit": "Gy"},
        }
    },
    "Cylinder HDR": {
        "plan_type": "Cylinder",
        "alpha_beta_ratios": {
            "Bladder": 3,
            "Rectum": 3,
            "Sigmoid": 3,
            "Bowel": 3,
            "Vagina": 3,
            "Uterus": 3,
            "Cervix": 3,
            "HRCTV": 3,
            "GTV": 3,
            "Default": 3
        },
        "constraints": {
            "target_constraints": {},
            "oar_constraints": {
                "Bladder": {"D2cc": {"max": 80.0, "unit": "Gy"}},
                "Rectum": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
                "Sigmoid": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}},
                "Bowel": {"D2cc": {"warning": 65.0, "max": 70.0, "unit": "Gy"}}
            }
        },
        "point_dose_constraints": {
            "Prescription Point": {
                "check_type": "prescription_tolerance",
                "tolerance": 0.10  # This sets the 10% tolerance
            }
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
            "Hrctv": 10,
            "Gtv": 10,
            "Default": 3
        },
        "constraints": {
            "target_constraints": {
                "Gtv D90": {"min": 95.0, "unit": "Gy"},
                "Gtv D98": {"min": 98.0, "unit": "Gy"},
                "Hrctv D90": {"min": 90.0, "unit": "Gy"},
                "Hrctv D98": {"min": 95.0, "unit": "Gy"}
            },
            "oar_constraints": {
                "Bladder": {"D2cc": {"max": 80.0, "unit": "Gy"}},
                "Rectum": {"D2cc": {"max": 70.0, "unit": "Gy"}},
                "Sigmoid": {"D2cc": {"max": 70.0, "unit": "Gy"}},
                "Bowel": {"D2cc": {"max": 65.0, "unit": "Gy"}}
            }
        },
        "point_dose_constraints": {
            "Prescription Point": {
                "check_type": "prescription_tolerance",
                "tolerance": 0.05  # This means +/- 5% of the prescribed dose
            }
        }
    }
}

# Default to EMBRACE II template
alpha_beta_ratios = templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]
constraints = templates["Cervix HDR - EMBRACE II"]["constraints"]