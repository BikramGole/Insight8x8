"""Rating-aware chess intelligence layered on top of Stockfish evaluations."""

import sys
from pathlib import Path

BOARD_DIR = Path(__file__).resolve().parent / "vendor"
if str(BOARD_DIR) not in sys.path:
    sys.path.insert(0, str(BOARD_DIR))

import chess

PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
CENTRE = {chess.D4, chess.E4, chess.D5, chess.E5}

PHASE_LABELS = ("opening", "middlegame", "endgame")


def phase_for_ply(ply, board=None):
    if ply <= 20:
        return "opening"
    if ply >= 70 or (board is not None and _minor_and_heavy_material(board) <= 12):
        return "endgame"
    return "middlegame"


def _minor_and_heavy_material(board):
    total = 0
    for piece in board.piece_map().values():
        if piece.piece_type not in (chess.PAWN, chess.KING):
            total += PIECE_VALUE[piece.piece_type]
    return total


def thresholds_for_rating(rating):
    value = int(rating or 1500)
    if value < 1000:
        return 40, 85, 160
    if value < 1400:
        return 30, 65, 125
    if value < 1800:
        return 25, 50, 100
    if value < 2200:
        return 20, 42, 85
    return 15, 35, 70


def classify_loss_for_rating(loss, rating=None, phase=None):
    if loss is None:
        return None
    good, inaccuracy, mistake = thresholds_for_rating(rating)
    if rating is not None and phase in PHASE_LABELS:
        if phase == "opening":
            factor = 1.1
        elif phase == "endgame":
            factor = 0.9
        else:
            factor = 1.0
        good, inaccuracy, mistake = (int(good * factor), int(inaccuracy * factor), int(mistake * factor))
    if loss <= good:
        return "best or good"
    if loss <= inaccuracy:
        return "inaccuracy"
    if loss <= mistake:
        return "mistake"
    return "blunder"


def _piece_at(board, square):
    piece = board.piece_at(square)
    return piece.piece_type if piece else None


def _pawn_is_passed(board, square, color):
    file_index = chess.square_file(square)
    rank = chess.square_rank(square)
    step = 1 if color == chess.WHITE else -1
    for enemy in board.pieces(chess.PAWN, not color):
        if abs(chess.square_file(enemy) - file_index) <= 1:
            enemy_rank = chess.square_rank(enemy)
            if (enemy_rank - rank) * step > 0:
                return False
    return True


def _has_skewer(board, mover_color, from_square, to_square):
    moved = _piece_at(board, to_square)
    if moved in (None, chess.PAWN, chess.KING):
        return False
    for target in board.attacks(to_square):
        target_piece = board.piece_at(target)
        if not target_piece or target_piece.color == mover_color:
            continue
        if PIECE_VALUE[target_piece.piece_type] < 3:
            continue
        file_delta = chess.square_file(to_square) - chess.square_file(target)
        rank_delta = chess.square_rank(to_square) - chess.square_rank(target)
        divisor = 0
        if file_delta == 0 and rank_delta:
            divisor = abs(rank_delta)
        elif rank_delta == 0 and file_delta:
            divisor = abs(file_delta)
        elif abs(file_delta) == abs(rank_delta):
            divisor = abs(file_delta)
        if not divisor:
            continue
        step_file = file_delta // divisor
        step_rank = rank_delta // divisor
        behind_file = chess.square_file(target) - step_file
        behind_rank = chess.square_rank(target) - step_rank
        if not (0 <= behind_file < 8 and 0 <= behind_rank < 8):
            continue
        behind = chess.square(behind_file, behind_rank)
        behind_piece = board.piece_at(behind)
        if behind_piece and behind_piece.color == mover_color and PIECE_VALUE[behind_piece.piece_type] >= 3:
            return True
    return False


def tactical_motifs(fen, uci):
    """Return human-readable tactical themes for a UCI move from ``fen``."""
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return []
    except (ValueError, TypeError, AssertionError):
        return []
    mover = board.turn
    moved_type = _piece_at(board, move.from_square)
    captured_type = None
    if board.is_en_passant(move):
        captured_type = chess.PAWN
    else:
        captured_type = _piece_at(board, move.to_square)
    gives_check = board.gives_check(move)
    is_capture = captured_type is not None
    board.push(move)
    motifs = []
    if gives_check:
        motifs.append("check")
    if is_capture:
        motifs.append("capture")
    if moved_type == chess.PAWN and chess.square_rank(move.to_square) in (0, 7):
        motifs.append("promotion")
    if moved_type == chess.PAWN and _pawn_is_passed(board, move.to_square, mover):
        motifs.append("passed pawn")
    if captured_type and PIECE_VALUE[moved_type] >= 3 and PIECE_VALUE[captured_type] <= 1:
        motifs.append("sacrifice")
    attacked = []
    for square in board.attacks(move.to_square):
        piece = board.piece_at(square)
        if piece and piece.color != mover and PIECE_VALUE[piece.piece_type] >= 3:
            attacked.append(square)
    if len(attacked) >= 2:
        motifs.append("fork")
    if board.is_check() and not gives_check:
        motifs.append("discovered check")
    if any(board.is_pinned(not mover, square) for square in board.pieces(chess.KNIGHT, not mover)):
        motifs.append("pin")
    if _has_skewer(board, mover, move.from_square, move.to_square):
        motifs.append("skewer")
    known = []
    for motif in motifs:
        if motif not in known:
            known.append(motif)
    return known


def explain_positional_mistake(fen_before, fen_after, uci, entry=None):
    """Explain the positional cost of a move in plain language."""
    try:
        before = chess.Board(fen_before)
        after = chess.Board(fen_after)
        move = chess.Move.from_uci(uci)
    except (ValueError, TypeError, AssertionError):
        return _fallback_explanation(entry)
    if move not in before.legal_moves:
        return _fallback_explanation(entry)
    mover = before.turn
    before_centre = _centre_control(before, mover)
    after_centre = _centre_control(after, mover)
    if after_centre < before_centre:
        return (
            f"You gave up control of the centre ({before_centre} to {after_centre} central squares); "
            "the opponent can now dictate the pace."
        )
    before_shield = _king_safety(before, mover)
    after_shield = _king_safety(after, mover)
    if after_shield < before_shield:
        return "Your king lost pawn cover, so future tactics against it become much more dangerous."
    before_developed = _developed_minors(before, mover)
    after_developed = _developed_minors(after, mover)
    moved_type = before.piece_type_at(move.from_square)
    if moved_type in (chess.KNIGHT, chess.BISHOP) and after_developed <= before_developed:
        return "The piece moved without improving development; bringing minors out earlier would coordinate your position."
    before_pawns = _pawn_weaknesses(before, mover)
    after_pawns = _pawn_weaknesses(after, mover)
    if after_pawns > before_pawns:
        return "The pawn structure weakened, creating long-term targets for the opponent."
    before_space = _space_score(before, mover)
    after_space = _space_score(after, mover)
    if after_space < before_space - 2:
        return "The move gave ground instead of gaining space, leaving your pieces passive."
    return _fallback_explanation(entry)


def why_is_better(entry=None):
    """Explain why the engine's preferred move is stronger than the played move."""
    entry = entry or {}
    best = entry.get("bestMoveSan") or "The engine move"
    played = entry.get("move")
    loss = entry.get("centipawnLoss")
    motifs = [item for item in (entry.get("bestMotifs") or []) if item not in ("capture",)]
    parts = [f"{best} is stronger"]
    if motifs:
        parts.append("it creates " + ", ".join(motifs[:2]))
    elif entry.get("replySan"):
        parts.append(f"it avoids {entry['replySan']}")
    else:
        parts.append("it keeps the evaluation from slipping")
    if loss is not None and loss > 0 and played:
        parts.append(f"while {played} cost {int(loss)} centipawns")
    if entry.get("phase"):
        parts.append(f"in the {entry['phase']}")
    return "; ".join(parts) + "."


def _fallback_explanation(entry=None):
    entry = entry or {}
    loss = entry.get("centipawnLoss")
    best = entry.get("bestMoveSan")
    if loss is not None:
        text = f"Stockfish measures a {int(loss)} centipawn loss here."
    else:
        text = "Stockfish prefers a different continuation here."
    if best:
        text += f" {best} keeps the evaluation from getting worse."
    return text


def _centre_control(board, color):
    count = 0
    for square in CENTRE:
        if board.attackers(color, square):
            count += 1
    return count


def _king_safety(board, color):
    king_square = board.king(color)
    if king_square is None:
        return 2
    king_file = chess.square_file(king_square)
    rank_step = 1 if color == chess.WHITE else -1
    king_rank = chess.square_rank(king_square)
    shield = 0
    for offset in (-1, 0, 1):
        file_index = king_file + offset
        if not 0 <= file_index < 8:
            continue
        for distance in range(1, 3):
            rank = king_rank + rank_step * distance
            if 0 <= rank < 8 and _piece_at(board, chess.square(file_index, rank)) == chess.PAWN:
                shield += 1
                break
    if board.has_castling_rights(color):
        shield += 1
    return shield


def _developed_minors(board, color):
    back_rank = 0 if color == chess.WHITE else 7
    count = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP):
        for square in board.pieces(piece_type, color):
            if chess.square_rank(square) != back_rank:
                count += 1
    return count


def _pawn_weaknesses(board, color):
    pawns = list(board.pieces(chess.PAWN, color))
    files = [chess.square_file(square) for square in pawns]
    doubled = len(files) - len(set(files))
    isolated = 0
    for file_index in set(files):
        neighbours = (file_index - 1, file_index + 1)
        if not any(other in files for other in neighbours if 0 <= other < 8):
            isolated += 1
    return doubled + isolated


def _space_score(board, color):
    score = 0
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        rank = chess.square_rank(square)
        advance = rank if color == chess.WHITE else 7 - rank
        score += max(0, advance - 1)
    return score


def recurring_weaknesses(analyses):
    """Aggregate repeated mistakes across analysed games into coaching themes."""
    if not analyses:
        return []
    counters = {}
    games = 0
    for item in analyses:
        if not isinstance(item, dict):
            continue
        analysis = item.get("analysis") or {}
        moves = analysis.get("moves") or []
        if not moves:
            continue
        games += 1
        metadata = {
            key: item.get(key)
            for key in ("game_id", "date", "color", "timeClass", "playerRating")
        }
        move_entries = moves.values() if isinstance(moves, dict) else moves
        for index, entry in enumerate(move_entries, start=1):
            if not isinstance(entry, dict):
                continue
            classification = entry.get("classification")
            if classification in ("blunder", "mistake"):
                key = "decision_quality"
                title = "Decision quality under pressure"
                detail = "Repeated blunders and mistakes; slow down on critical moves."
                weight = 2 if classification == "blunder" else 1
                _bump(counters, key, title, detail, weight, metadata, entry)
            phase = entry.get("phase") or phase_for_ply(index)
            if phase == "opening" and classification in ("inaccuracy", "mistake", "blunder"):
                _bump(
                    counters,
                    "opening",
                    "Opening accuracy",
                    "Early inaccuracies repeat; revise your first moves.",
                    1,
                    metadata,
                    entry,
                )
            for motif in entry.get("motifs") or []:
                if motif in ("check", "capture", "best or good"):
                    continue
                key = f"motif:{motif}"
                _bump(
                    counters,
                    key,
                    f"Missed {motif}",
                    f"Review positions involving {motif} before committing to a move.",
                    1,
                    metadata,
                    entry,
                )
            explanation = entry.get("explanation") or ""
            if "centre" in explanation:
                _bump(
                    counters,
                    "centre",
                    "Central control",
                    "Moves often surrender the centre; fight for d4/e4/d5/e5 early.",
                    1,
                    metadata,
                    entry,
                )
            elif "king" in explanation:
                _bump(
                    counters,
                    "king_safety",
                    "King safety",
                    "Pawn cover around the king is frequently neglected.",
                    1,
                    metadata,
                    entry,
                )
            elif "development" in explanation:
                _bump(
                    counters,
                    "development",
                    "Development",
                    "Minors often stay passive; prioritise development and castling.",
                    1,
                    metadata,
                    entry,
                )
    weaknesses = []
    for key, data in counters.items():
        count = data["count"]
        severity = "high" if count >= 6 else "medium" if count >= 3 else "low"
        weaknesses.append(
            {
                "key": key,
                "title": data["title"],
                "detail": data["detail"],
                "count": count,
                "games": len({sample.get("game_id") for sample in data["samples"] if sample.get("game_id")}),
                "severity": severity,
                "samples": data["samples"][:3],
            }
        )
    weaknesses.sort(key=lambda item: (item["count"], item["games"]), reverse=True)
    for item in weaknesses:
        item["games"] = item["games"] or games
    return weaknesses[:10]


def _bump(counters, key, title, detail, weight, metadata, entry):
    data = counters.setdefault(key, {"title": title, "detail": detail, "count": 0, "samples": []})
    data["count"] += weight
    sample = dict(metadata)
    sample.update(
        {
            "ply": entry.get("ply"),
            "san": entry.get("san"),
            "classification": entry.get("classification"),
            "centipawnLoss": entry.get("centipawnLoss"),
            "bestMoveSan": entry.get("bestMoveSan"),
            "explanation": entry.get("explanation"),
            "motifs": entry.get("motifs") or [],
        }
    )
    data["samples"].append(sample)
