MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

RESULT_FILTERS = {
    "all": "all", "All results": "all",
    "win": "win", "Wins": "win", "wins": "win",
    "loss": "loss", "Losses": "loss", "losses": "loss",
    "draw": "draw", "Draws": "draw", "draws": "draw",
}
TIME_FILTERS = {
    "all": "all", "All time controls": "all",
    "bullet": "bullet", "Bullet": "bullet",
    "blitz": "blitz", "Blitz": "blitz",
    "rapid": "rapid", "Rapid": "rapid",
    "daily": "daily", "Daily": "daily",
}
COLOR_FILTERS = {
    "all": "all", "Both colors": "all",
    "white": "white", "As White": "white",
    "black": "black", "As Black": "black",
}


def fmt_number(value):
    if value is None or value == "":
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def fmt_date(value):
    parts = str(value or "").strip().replace(".", "-").split("-")
    if len(parts) != 3:
        return "—"
    try:
        month = int(parts[1])
        if not 1 <= month <= 12:
            return "—"
        return f"{MONTHS[month - 1]} {int(parts[2])}, {parts[0]}"
    except (ValueError, IndexError):
        return str(value)


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    minutes = max(0, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}h {minutes % 60}m"


def result_text(result):
    return {"win": "Win", "loss": "Loss", "draw": "Draw"}.get(result, "Unknown")


def result_letter(result):
    return {"win": "W", "loss": "L", "draw": "D"}.get(result, "?")


def csv_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def game_matches_filters(game, filters):
    search = str(filters.get("search") or "").strip().lower()
    if search:
        haystack = " ".join(
            str(game.get(key) or "")
            for key in ("opponent", "opening", "eco", "white", "black", "termination")
        ).lower()
        if search not in haystack:
            return False
    result = RESULT_FILTERS.get(filters.get("result", "all"), "all")
    if result != "all" and game.get("result") != result:
        return False
    time_class = TIME_FILTERS.get(filters.get("timeClass", "all"), "all")
    if time_class != "all" and game.get("timeClass") != time_class:
        return False
    color = COLOR_FILTERS.get(filters.get("color", "all"), "all")
    if color != "all" and game.get("color") != color:
        return False
    date = str(game.get("date") or "")
    if date and filters.get("dateFrom") and date < str(filters["dateFrom"]):
        return False
    if date and filters.get("dateTo") and date > str(filters["dateTo"]):
        return False
    return True


def filter_game_details(details, filters):
    return [game for game in details if game_matches_filters(game, filters)]
