"""The Aerolith material palette (Bryce material dicts, see harness brc_material / sheet.Ctx.mat).

Solid gloss: high specularity + reflection of the Aero sky; colour lives in diffuse + ambient.
Glass: low diffusion (Bryce shading is additive), high transparency; the `transparent` colour
filters what shows through. Every glass material is matted twice (light / dark page)."""


def gloss(diffuse, ambient, ambience=0.35, reflection=0.35, specularity=1.0, diffusion=0.75):
    return dict(diffuse=diffuse, diffusion=diffusion, ambient=ambient, ambience=ambience,
                specularity=specularity, reflection=reflection)


def glass(diffuse, ambient, transparent, transparency=0.85, diffusion=0.12, ambience=0.08,
          reflection=0.25, refraction=1.25, specularity=1.0):
    return dict(diffuse=diffuse, diffusion=diffusion, ambient=ambient, ambience=ambience,
                specularity=specularity, transparency=transparency, transparent=transparent,
                reflection=reflection, refraction=refraction)


# --- solid gloss: (normal, hover, active) per colour; white label text sits on these
AQUA = gloss("#1466c8", "#0a3a80")
AQUA_HOVER = gloss("#2584ea", "#0a3a80", ambience=0.5)
AQUA_ACTIVE = gloss("#1466c8", "#1f6fd8", ambience=0.45)        # pressed = dished face (catalog), lit from within

# green leans yellow: its face mirrors blue sky, which would otherwise pull it toward teal
GREEN = gloss("#2a9418", "#0f4f08", reflection=0.25)
GREEN_HOVER = gloss("#36ad22", "#0f4f08", ambience=0.5, reflection=0.25)
GREEN_ACTIVE = gloss("#2a9418", "#1f8a12", ambience=0.45, reflection=0.25)

RED = gloss("#c8283a", "#6a0d18")
AMBER = gloss("#e09a12", "#7a4a00")
DISABLED = gloss("#9fb2c4", "#5d7184", specularity=0.4, reflection=0.12, diffusion=0.7)

PEARL = gloss("#f4f8fb", "#c8d6e4", ambience=0.3, reflection=0.3, diffusion=0.8)
LIQUID = gloss("#43c92b", "#1d8a12", ambience=0.45, reflection=0.3, diffusion=0.7)
LIQUID_AQUA = gloss("#2a9cf0", "#0a5ab0", ambience=0.5, reflection=0.3, diffusion=0.7)

# --- glass
CLEAR = glass("#d8f0ff", "#9fd8ff", "#e8f8ff")                       # quiet button, big glass
TINT = glass("#bfe6ff", "#7cc4f0", "#cdeeff", transparency=0.7, diffusion=0.18, ambience=0.15)
TINT_GREEN = glass("#c4f2c0", "#6fd06a", "#d4f8d0", transparency=0.7, diffusion=0.18, ambience=0.15)
FROST = glass("#f2f9ff", "#d8ecff", "#f4fbff", transparency=0.62, diffusion=0.35, ambience=0.2,
              reflection=0.15, refraction=1.05, specularity=0.8)
SMOKE = glass("#1c2a3a", "#0e1a28", "#5a7a9a", transparency=0.55, diffusion=0.3, ambience=0.25,
              reflection=0.2, refraction=1.05, specularity=0.8)                # dark-theme panels

GLASS_KEYS = ("transparency",)


def is_glass(m):
    return bool(m and m.get("transparency", 0) > 0)

# --- fields (recessed wells): near-white floor for dark ink / slate floor for light ink
FIELD = gloss("#ffffff", "#f2f8fd", ambience=0.62, reflection=0.07, specularity=0.6, diffusion=0.6)
FIELD_DARK = gloss("#1b2938", "#0e1824", ambience=0.35, reflection=0.15, specularity=0.6, diffusion=0.8)
FIELD_FOCUS = gloss("#ffffff", "#d4ecff", ambience=0.66, reflection=0.07, specularity=0.7, diffusion=0.6)
FIELD_DARK_FOCUS = gloss("#1f3348", "#123a5e", ambience=0.5, reflection=0.15, specularity=0.7, diffusion=0.8)

# --- gems (badges, status orbs)
GEM = {
    "ok": gloss("#2a9418", "#0f4f08", reflection=0.3),
    "info": gloss("#1466c8", "#0a3a80", reflection=0.3),
    "warn": gloss("#e8a516", "#7a4a00", reflection=0.3),
    "error": gloss("#cc2a3c", "#6a0d18", reflection=0.3),
}

# --- icons: standalone (aqua, a touch lighter than the button so thin strokes stay blue) and
# pearl (white, for glyphs on coloured buttons)
ICON = {"aqua": gloss("#1c78dc", "#0a4796", reflection=0.3), "pearl": PEARL}

# --- small solid accents
SUN = gloss("#f6b81c", "#a05a00", ambience=0.45, reflection=0.3)          # theme switch: light
MOON = gloss("#7d93c8", "#26355e", ambience=0.35, reflection=0.35)        # theme switch: dark
DIM = gloss("#c6d4e2", "#7d90a4", ambience=0.4, reflection=0.25, specularity=0.7)   # spinner: unlit orb
AQUA_MID = gloss("#4f9fe6", "#1a5aa8", ambience=0.45, reflection=0.3)       # spinner: trail
CHOICE = glass("#a8dcff", "#4fa8ec", "#c4e8ff", transparency=0.6, diffusion=0.22, ambience=0.24,
               reflection=0.22, refraction=1.05, specularity=0.9)            # selected choice card
CHOICE_DARK = glass("#1a4a7a", "#0f3a6a", "#4a8ac8", transparency=0.5, diffusion=0.3, ambience=0.32,
                    reflection=0.22, refraction=1.05, specularity=0.85)
DROP_DARK = glass("#2f7a46", "#1c5a30", "#5aa86a", transparency=0.55, diffusion=0.28, ambience=0.26,
                  reflection=0.22, refraction=1.05, specularity=0.85)          # drop zone, drag-over, dark page
