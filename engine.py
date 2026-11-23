import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import chess

from chesscom import ChessComError

MATE_SCORE = 10000

try:
    import select
except ImportError:
    select = None


def classify_loss(loss):
    if loss is None:
        return None
    if loss <= 25:
        return "best or good"
    if loss <= 50:
        return "inaccuracy"
    if loss <= 100:
        return "mistake"
    return "blunder"


def score_value(score):
    if not score:
        return None
    mate = score.get("mate")
    if mate is not None:
        mate = int(mate)
        return (MATE_SCORE - abs(mate) * 10) * (1 if mate > 0 else -1)
    cp = score.get("cp")
    return int(cp) if cp is not None else None


def format_score(score):
    if not score:
        return "—"
    mate = score.get("mate")
    if mate is not None:
        mate = int(mate)
        return f"M{abs(mate)}" if mate > 0 else f"-M{abs(mate)}"
    cp = score.get("cp")
    return f"{int(cp) / 100:+.2f}" if cp is not None else "—"


def _score_for_player(score, side_to_move, player):
    if not score:
        return {"cp": None, "mate": None}
    cp = score.get("cp")
    mate = score.get("mate")
    if side_to_move != player:
        cp = -cp if cp is not None else None
        mate = -mate if mate is not None else None
    return {"cp": cp, "mate": mate}


def _fen_side(fen):
    parts = str(fen or "").split()
    return parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else "w"


def _san_sequence(fen, ucis):
    try:
        board = chess.Board(fen)
    except Exception:
        return []
    result = []
    for uci in ucis or []:
        try:
            move = board.parse_uci(str(uci))
        except (ValueError, TypeError, AssertionError):
            break
        result.append(board.san(move))
        board.push(move)
    return result


def _first_san(fen, uci):
    sans = _san_sequence(fen, [uci]) if uci else []
    return sans[0] if sans else (str(uci) if uci else "—")


def _move_flags(fen, uci):
    try:
        board = chess.Board(fen)
        move = board.parse_uci(str(uci))
        return {"capture": board.is_capture(move), "check": board.gives_check(move)}
    except Exception:
        return {"capture": False, "check": False}


def _parse_info(line):
    if not line.startswith("info ") or " score " not in line or " string " in line:
        return None
    cp_match = re.search(r"score cp (-?\d+)", line)
    mate_match = re.search(r"score mate (-?\d+)", line)
    if not cp_match and not mate_match:
        return None
    depth_match = re.search(r"\bdepth (\d+)", line)
    index_match = re.search(r"\bmultipv (\d+)", line)
    pv_match = re.search(r"\bpv\b(.*)$", line)
    return {
        "index": int(index_match.group(1)) if index_match else 1,
        "depth": int(depth_match.group(1)) if depth_match else 0,
        "score": {
            "cp": int(cp_match.group(1)) if cp_match else None,
            "mate": int(mate_match.group(1)) if mate_match else None,
        },
        "pv": pv_match.group(1).split() if pv_match else None,
    }


def _find_opportunities(before, after, best_san, best_candidate, reply_score, reply_san):
    items = []
    best_value = score_value(before)
    played_value = score_value(after)
    mate = before.get("mate") if before else None
    if mate is not None and mate > 0 and not (after.get("mate") or 0) > 0:
        items.append(f"Missed a forced mate in {abs(mate)} ({best_san})")
    elif best_value is not None and played_value is not None and best_value >= 300 and played_value < 100:
        items.append(f"Missed a winning advantage ({best_san}, {format_score(before)})")
    if best_candidate.get("capture") or best_candidate.get("check"):
        if best_value is None or played_value is None or best_value - played_value >= 150:
            tactic = "check" if best_candidate.get("check") else "capturing move"
            items.append(f"Tactical shot available: {best_san} ({tactic})")
    reply_value = score_value(reply_score)
    if reply_value is not None and reply_value >= 300 and played_value is not None and played_value < 0:
        items.append(f"Allowed a strong reply: {reply_san}")
    return items


def build_game_analysis(fens, moves, positions, multipv=3):
    entries = {}
    opportunities = []
    summary = {
        "moves": len(moves),
        "classified": 0,
        "bestOrGood": 0,
        "inaccuracies": 0,
        "mistakes": 0,
        "blunders": 0,
        "byColor": {
            "w": {"bestOrGood": 0, "inaccuracies": 0, "mistakes": 0, "blunders": 0},
            "b": {"bestOrGood": 0, "inaccuracies": 0, "mistakes": 0, "blunders": 0},
        },
    }
    for ply, move in enumerate(moves, start=1):
        before_fen = fens[ply - 1]
        after_fen = fens[ply]
        mover = move.get("color") or ("w" if ply % 2 == 1 else "b")
        before_position = positions[ply - 1]
        after_position = positions[ply]
        raw_candidates = before_position.get("candidates") or []
        best_raw = raw_candidates[0] if raw_candidates else {}
        best_uci = best_raw.get("move") or before_position.get("bestMove")
        best_san = _first_san(before_fen, best_uci)
        eval_before = _score_for_player(best_raw.get("score"), _fen_side(before_fen), mover)
        reply_raw = (after_position.get("candidates") or [{}])[0]
        eval_after = _score_for_player(reply_raw.get("score"), _fen_side(after_fen), mover)
        best_value = score_value(eval_before)
        played_value = score_value(eval_after)
        loss = max(0, best_value - played_value) if best_value is not None and played_value is not None else None
        classification = classify_loss(loss)
        candidates = []
        for index, candidate in enumerate(raw_candidates[:multipv], start=1):
            uci = candidate.get("move")
            pv_san = _san_sequence(before_fen, candidate.get("pv") or ([uci] if uci else []))
            flags = _move_flags(before_fen, uci) if uci else {"capture": False, "check": False}
            score = _score_for_player(candidate.get("score"), _fen_side(before_fen), mover)
            candidates.append(
                {
                    "rank": index,
                    "move": uci,
                    "san": pv_san[0] if pv_san else (uci or "—"),
                    "score": score,
                    "centipawns": score_value(score),
                    "pv": pv_san,
                    "capture": flags["capture"],
                    "check": flags["check"],
                }
            )
        reply_uci = reply_raw.get("move") or after_position.get("bestMove")
        reply_san = _first_san(after_fen, reply_uci)
        move_opportunities = _find_opportunities(
            eval_before,
            eval_after,
            best_san,
            candidates[0] if candidates else {},
            reply_raw.get("score"),
            reply_san,
        )
        entries[ply] = {
            "ply": ply,
            "move": move.get("san"),
            "color": mover,
            "bestMove": best_uci,
            "bestMoveSan": best_san,
            "playedMove": move.get("uci"),
            "evalBefore": eval_before,
            "evalAfter": eval_after,
            "centipawnLoss": loss,
            "classification": classification,
            "candidates": candidates,
            "replySan": reply_san,
            "tacticalOpportunities": move_opportunities,
        }
        for text in move_opportunities:
            opportunities.append({"ply": ply, "move": move.get("san"), "color": mover, "text": text})
        if classification:
            key = {
                "best or good": "bestOrGood",
                "inaccuracy": "inaccuracies",
                "mistake": "mistakes",
                "blunder": "blunders",
            }[classification]
            summary["classified"] += 1
            summary[key] += 1
            summary["byColor"][mover][key] += 1
    return {
        "engine": "Stockfish",
        "moves": entries,
        "summary": summary,
        "opportunities": opportunities,
    }


class StockfishAnalyzer:
    def __init__(self, path=None):
        self.set_path(path if path is not None else os.environ.get("STOCKFISH_PATH"))

    def set_path(self, path):
        configured = str(path or "").strip()
        self.path = configured if configured and Path(configured).exists() else shutil.which("stockfish")
        self.available = bool(self.path)

    def _start_process(self):
        return subprocess.Popen(
            [self.path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    @staticmethod
    def _send(process, command):
        process.stdin.write(command + "\n")
        process.stdin.flush()

    def _analyze_position(self, process, fen, depth, movetime, multipv):
        self._send(process, "position fen " + fen)
        self._send(
            process,
            "go depth {depth} movetime {movetime}".format(
                depth=depth, movetime=movetime
            ),
        )
        candidates = {}
        best_move = None
        reached_depth = 0
        buffer = ""
        deadline = time.time() + (movetime / 1000) + 10
        stopping = False
        while time.time() < deadline:
            if select is not None:
                ready, _, _ = select.select(
                    [process.stdout.fileno()], [], [], max(0.01, deadline - time.time())
                )
                if not ready:
                    if stopping:
                        break
                    try:
                        self._send(process, "stop")
                    except (BrokenPipeError, OSError):
                        break
                    stopping = True
                    deadline = time.time() + 2
                    continue
            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", "replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line.startswith("bestmove"):
                    parts = line.split()
                    best_move = parts[1] if len(parts) > 1 and parts[1] != "(none)" else None
                    break
                info = _parse_info(line)
                if not info:
                    continue
                previous = candidates.get(info["index"], {"move": None, "score": {}, "pv": [], "depth": 0})
                if info["depth"] and info["depth"] < previous["depth"]:
                    continue
                reached_depth = max(reached_depth, info["depth"])
                pv = info["pv"] or previous["pv"]
                score = info["score"] if (info["score"].get("cp") is not None or info["score"].get("mate") is not None) else previous["score"]
                candidates[info["index"]] = {
                    "move": pv[0] if pv else previous["move"],
                    "score": score,
                    "pv": pv,
                    "depth": info["depth"] or previous["depth"],
                }
            if best_move:
                break
        ordered = [candidates[key] for key in sorted(candidates)][:multipv]
        if not ordered and best_move:
            ordered = [{"move": best_move, "score": {}, "pv": [best_move], "depth": reached_depth}]
        elif ordered and not ordered[0].get("move") and best_move:
            ordered[0]["move"] = best_move
            if not ordered[0]["pv"]:
                ordered[0]["pv"] = [best_move]
        return {"fen": fen, "depth": reached_depth, "bestMove": best_move, "candidates": ordered}

    @staticmethod
    def _configure_engine(process, multipv):
        StockfishAnalyzer._send(process, "uci")
        StockfishAnalyzer._send(process, "isready")
        StockfishAnalyzer._send(process, "setoption name MultiPV value {multipv}".format(multipv=multipv))

    @staticmethod
    def _stop_process(process):
        try:
            if process.stdin and not process.stdin.closed:
                StockfishAnalyzer._send(process, "quit")
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired, BrokenPipeError, OSError, ValueError):
            process.kill()
            process.wait(timeout=2)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for stream in (process.stdin, process.stdout):
            if stream and not stream.closed:
                stream.close()

    def analyze_positions(self, fens, depth=12, movetime=150, multipv=3, progress=None):
        if not self.available:
            raise ChessComError("Stockfish is not configured on this device.")
        fens = [str(item or "").strip() for item in fens]
        if not fens or any(not fen or len(fen) > 200 for fen in fens):
            raise ChessComError("Invalid FEN supplied for analysis.")
        depth = max(4, min(20, int(depth)))
        movetime = max(50, min(3000, int(movetime)))
        multipv = max(1, min(5, int(multipv)))
        process = self._start_process()
        positions = []
        try:
            self._configure_engine(process, multipv)
            for index, fen in enumerate(fens, start=1):
                result = self._analyze_position(process, fen, depth, movetime, multipv)
                positions.append(result)
                if not result.get("bestMove"):
                    self._stop_process(process)
                    process = self._start_process()
                    self._configure_engine(process, multipv)
                if progress:
                    progress(index, len(fens))
        finally:
            self._stop_process(process)
        return positions

    def analyze_game(self, fens, moves, depth=12, movetime=150, multipv=3, progress=None):
        if len(fens) != len(moves) + 1:
            raise ChessComError("Analysis needs one position per move plus the starting position.")
        positions = self.analyze_positions(
            fens, depth=depth, movetime=movetime, multipv=multipv, progress=progress
        )
        return build_game_analysis(fens, moves, positions, multipv=multipv)

    def analyze(self, fen, depth=12, movetime=400):
        position = self.analyze_positions([fen], depth=depth, movetime=movetime, multipv=3)[0]
        best = position["candidates"][0] if position["candidates"] else {}
        score = best.get("score") or {}
        return {
            "engine": "Stockfish",
            "depth": position["depth"],
            "bestMove": best.get("move") or position["bestMove"],
            "score": score.get("cp"),
            "mate": score.get("mate"),
            "fen": fen,
            "centipawns": score_value(score),
            "candidates": position["candidates"],
        }

    def analyze_move(self, before_fen, after_fen, depth=12, movetime=400):
        before = self.analyze(before_fen, depth=depth, movetime=movetime)
        after = self.analyze(after_fen, depth=depth, movetime=movetime)
        before_cp = before.get("centipawns")
        after_cp = after.get("centipawns")
        result = {"before": before, "after": after, "engine": "Stockfish"}
        if before_cp is not None and after_cp is not None:
            loss = max(0, before_cp + after_cp)
            result["centipawnLoss"] = loss
            result["classification"] = classify_loss(loss)
        return result
