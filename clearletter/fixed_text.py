"""Texts that Claude is never allowed to write.

Why: the emergency numbers, the disclaimer and the fallback message are the
parts where a mistake would be most dangerous (a wrong phone number, invented
urgency, a missing warning). So they are written once, by a person, here, and
the program adds them to every output. The model only writes sections 1 to 5a.
"""

LANGUAGES = ("en", "fr", "es")
COUNTRIES = ("uk", "fr")

# The five section headings, in order (see SPEC.md section 6).
HEADINGS = {
    "en": [
        "What this letter says",
        "What you need to do",
        "Dates and medicines",
        "Questions to ask your doctor",
        "When to get urgent help",
    ],
    "fr": [
        "Ce que dit cette lettre",
        "Ce que vous devez faire",
        "Dates et médicaments",
        "Questions à poser à votre médecin",
        "Quand obtenir de l'aide en urgence",
    ],
    "es": [
        "Qué dice esta carta",
        "Qué tiene que hacer",
        "Fechas y medicamentos",
        "Preguntas para su médico",
        "Cuándo pedir ayuda urgente",
    ],
}

# Used in section 5 when the letter itself lists no warning signs.
NO_WARNING_SIGNS = {
    "en": "The letter does not list specific warning signs.",
    "fr": "La lettre ne donne pas de signes d'alerte particuliers.",
    "es": "La carta no menciona señales de alarma concretas.",
}

# Emergency numbers depend on the COUNTRY the patient lives in, and the text
# on the LANGUAGE they read. A Spanish speaker in London gets Spanish + 111/999.
EMERGENCY = {
    ("uk", "en"): "If you are worried and it is not an emergency, call NHS 111. In an emergency, call 999.",
    ("uk", "fr"): "Si vous êtes inquiet et que ce n'est pas une urgence, appelez le NHS 111. En cas d'urgence, appelez le 999.",
    ("uk", "es"): "Si le preocupa algo y no es una emergencia, llame al NHS 111. En caso de emergencia, llame al 999.",
    ("fr", "en"): "In a medical emergency in France, call 15 (SAMU) or 112.",
    ("fr", "fr"): "En cas d'urgence médicale, appelez le 15 (SAMU) ou le 112.",
    ("fr", "es"): "En caso de urgencia médica en Francia, llame al 15 (SAMU) o al 112.",
}

DISCLAIMER = {
    "en": (
        "This explanation was made by a computer program to help you read your letter. "
        "It may contain mistakes. It does not replace your doctor, nurse or pharmacist. "
        "Always follow the letter and ask them if anything is unclear."
    ),
    "fr": (
        "Cette explication a été faite par un programme informatique pour vous aider à lire votre lettre. "
        "Elle peut contenir des erreurs. Elle ne remplace pas votre médecin, votre infirmier ou votre pharmacien. "
        "Suivez toujours la lettre et posez-leur vos questions si quelque chose n'est pas clair."
    ),
    "es": (
        "Esta explicación la ha hecho un programa informático para ayudarle a leer su carta. "
        "Puede contener errores. No sustituye a su médico, enfermero o farmacéutico. "
        "Siga siempre lo que dice la carta y pregúnteles si algo no está claro."
    ),
}

FALLBACK = {
    "en": "We could not explain this letter safely. Please ask your doctor, nurse or pharmacist to explain it to you.",
    "fr": "Nous n'avons pas pu expliquer cette lettre de façon sûre. Demandez à votre médecin, votre infirmier ou votre pharmacien de vous l'expliquer.",
    "es": "No hemos podido explicar esta carta de forma segura. Pida a su médico, enfermero o farmacéutico que se la explique.",
}


def finish(model_text, language, country):
    """Add the fixed emergency text and the disclaimer after the model's text."""
    return (
        f"{model_text.rstrip()}\n\n"
        f"{EMERGENCY[(country, language)]}\n\n"
        f"---\n*{DISCLAIMER[language]}*\n"
    )


def fallback(language, country):
    """What the patient sees when the pipeline could not produce a safe explanation."""
    return (
        f"**{FALLBACK[language]}**\n\n"
        f"{EMERGENCY[(country, language)]}\n\n"
        f"---\n*{DISCLAIMER[language]}*\n"
    )
