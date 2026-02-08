# Transformer/unit_mapping.py
# Central mapping table for MTP Units → Master Recipe Units with IRDIs

UNIT_MAPPING = {
    # --- Time ---
    1007: {  # Sekunde
        "name": "Sekunde",
        "si_irdi": "https://si-digital-framework.org/SI/units/second",
        "qudt_irdi": "https://qudt.org/vocab/unit/SEC",
    },
    1006: {  # Minute
        "name": "minute",
        "si_irdi": "https://si-digital-framework.org/SI/units/minute",
        "qudt_irdi": "https://qudt.org/vocab/unit/MIN",
    },
    1059: {  # Stunde
        "name": "hour",
        "si_irdi": "https://si-digital-framework.org/SI/units/hour",
        "qudt_irdi": "https://qudt.org/vocab/unit/HR",
    },

    # --- Angle / Rotation ---
    1004: {  # Radiant
        "name": "radian",
        "si_irdi": "https://si-digital-framework.org/SI/units/radian",
        "qudt_irdi": "https://qudt.org/vocab/unit/RAD",
    },
    1009: {  # Umdrehung
        "name": "revolution",
        "si_irdi": "https://si-digital-framework.org/SI/units/revolution",
        "qudt_irdi": "https://qudt.org/vocab/unit/REV",
    },

    # --- Length ---
    1010: {  # Meter
        "name": "meter",
        "si_irdi": "https://si-digital-framework.org/SI/units/meter",
        "qudt_irdi": "https://qudt.org/vocab/unit/M",
    },

    # --- Speed / Frequency ---
    1077: {  # Hertz
        "name": "hertz",
        "si_irdi": "https://si-digital-framework.org/SI/units/hertz",
        "qudt_irdi": "https://qudt.org/vocab/unit/HZ",
    },
    1085: {  # Umdrehungen pro Minute
        "name": "revolution per minute",
        "si_irdi": "https://si-digital-framework.org/SI/units/revolution-per-minute",
        "qudt_irdi": "https://qudt.org/vocab/unit/REV-PER-MIN",
    },

    # --- Temperature ---
    1000: {  # Kelvin
        "name": "kelvin",
        "si_irdi": "https://si-digital-framework.org/SI/units/kelvin",
        "qudt_irdi": "https://qudt.org/vocab/unit/K",
    },
    1001: {  # Grad Celsius
        "name": "degree celsius",
        "si_irdi": "https://si-digital-framework.org/SI/units/degree-celsius",
        "qudt_irdi": "https://qudt.org/vocab/unit/DEG_C",
    },

    # --- Fallback ---
    1998: {  # Maßeinheit nicht bekannt
        "name": "unknown",
        "si_irdi": None,
        "qudt_irdi": None,
    },
}

