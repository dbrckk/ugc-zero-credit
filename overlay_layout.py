"""Fixed safe-zone geometry for product cards (no face recognition claim)."""
LAYOUTS = frozenset({"full", "pip_left", "pip_right"})

def card_geometry(layout: str, width: int, height: int) -> dict:
    if layout not in LAYOUTS:
        raise ValueError(f"Mode d'insert inconnu: {layout}")
    if not (isinstance(width, int) and isinstance(height, int) and width >= 100 and height >= 180):
        raise ValueError("Dimensions vidéo invalides")
    if layout == "full":
        return {"layout": layout, "inner_width": width, "inner_height": height,
                "x": 0, "y": 0, "border": 0, "shadow": 0,
                "total_width": width, "total_height": height}
    inner_w = max(2, 2 * round(width * .37 / 2))
    inner_h = max(2, 2 * round(height * .25 / 2))
    border = max(2, round(width * .005))
    shadow = max(2, round(width * .006))
    card_w = inner_w + 2 * (border + shadow)
    card_h = inner_h + 2 * (border + shadow)
    margin = round(width * .045)
    x = margin if layout == "pip_left" else width - margin - card_w
    y = round(height * .35)
    if x < 0 or y < 0 or x + card_w > width or y + card_h > height * .68:
        raise ValueError("La carte produit entre en conflit avec les zones sûres")
    return {"layout": layout, "inner_width": inner_w, "inner_height": inner_h,
            "x": x, "y": y, "border": border, "shadow": shadow,
            "total_width": card_w, "total_height": card_h}

def framed_card_filters(border: int, shadow: int) -> str:
    """White inset border and dark outer framing using local FFmpeg filters."""
    if border <= 0 or shadow <= 0:
        raise ValueError("Bordure et ombre attendues pour le mode carte")
    return (f"pad=iw+{2*border}:ih+{2*border}:x={border}:y={border}:color=0xFCFCFF,"
            f"pad=iw+{2*shadow}:ih+{2*shadow}:x={shadow}:y={shadow}:color=0x171A28")
