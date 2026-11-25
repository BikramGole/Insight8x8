"""Local-first chess coaching with an optional LLM adapter."""

import csv
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from intelligence import recurring_weaknesses, why_is_better

LLM_URL_ENV = "INSIGHT8X8_LLM_URL"
LLM_KEY_ENV = "INSIGHT8X8_LLM_KEY"
LLM_MODEL_ENV = "INSIGHT8X8_LLM_MODEL"
LLM_TIMEOUT_ENV = "INSIGHT8X8_LLM_TIMEOUT"
ENV_FILE_ENV = "INSIGHT8X8_ENV_FILE"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"


def load_env_file(path=None):
    candidate = Path(
        path or os.environ.get(ENV_FILE_ENV, Path(__file__).resolve().parent / ".env")
    )
    if not candidate.is_file():
        return False
    loaded = False
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded = True
    return loaded


class LLMCoach:
    """Minimal OpenAI-compatible adapter; never active without configuration."""

    def __init__(self, url=None, key=None, model=None, timeout=None):
        self.url = str(url or os.environ.get(LLM_URL_ENV, "")).strip()
        self.key = str(key or os.environ.get(LLM_KEY_ENV, "")).strip()
        configured_model = model if model is not None else os.environ.get(LLM_MODEL_ENV, "")
        default_model = GROQ_MODEL if self.key.startswith("gsk_") else "gpt-4o-mini"
        self.model = str(configured_model or default_model).strip() or default_model
        if not self.url and self.key.startswith("gsk_"):
            self.url = GROQ_URL
        try:
            self.timeout = float(timeout or os.environ.get(LLM_TIMEOUT_ENV, 8))
        except (TypeError, ValueError):
            self.timeout = 8.0
        self.last_error = ""

    @property
    def available(self):
        return bool(self.url and self.key)

    def generate(self, prompt):
        if not self.available:
            raise RuntimeError("No LLM endpoint configured.")
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
            return (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError, OSError) as error:
            status = getattr(error, "code", "")
            self.last_error = f"{type(error).__name__}{f' {status}' if status else ''}"
            raise RuntimeError(f"LLM request failed ({self.last_error}).") from error


def build_lesson_prompt(weaknesses):
    lines = ["You are a chess coach. Return JSON only with a lessons array."]
    lines.append("Each lesson has title, summary, focus and steps (array of short strings).")
    lines.append("Player weaknesses:")
    for item in weaknesses[:8]:
        lines.append(
            f"- {item['title']} ({item['count']} occurrences): {item['detail']}"
        )
    return "\n".join(lines)


def _extract_json_object(text):
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("No JSON object found.")
    return json.loads(match.group(0))


def generate_lessons(weaknesses, llm=None):
    local = local_lessons(weaknesses)
    if llm is None or not getattr(llm, "available", False):
        return local
    try:
        data = _extract_json_object(llm.generate(build_lesson_prompt(weaknesses)))
        items = data.get("lessons") or []
        enriched = []
        for index, item in enumerate(items[:len(local) + 2]):
            if not isinstance(item, dict):
                continue
            steps = item.get("steps") or []
            enriched.append(
                {
                    "id": f"llm-{index + 1}",
                    "title": str(item.get("title") or f"Lesson {index + 1}"),
                    "summary": str(item.get("summary") or ""),
                    "focus": str(item.get("focus") or "mixed"),
                    "steps": [str(step) for step in steps[:5]],
                    "severity": (weaknesses[index % len(weaknesses)]["severity"] if weaknesses else "medium"),
                    "source": "LLM",
                }
            )
        return enriched or local
    except (RuntimeError, ValueError, TypeError):
        for lesson in local:
            lesson["source"] = "local fallback"
        return local


def local_lessons(weaknesses):
    playbook = {
        "decision_quality": (
            "Think before you commit",
            "Blunders cluster when moves are played too quickly.",
            "Name the opponent's threat, list each candidate, then verify the final move.",
        ),
        "opening": (
            "Rebuild your first ten moves",
            "Opening inaccuracies repeat across games.",
            "Learn one main line, practise the first ten moves, and review why each move is played.",
        ),
        "centre": (
            "Fight for the centre",
            "Central squares determine mobility and piece activity.",
            "Add a central pawn break, develop towards d4/e4/d5/e5, and punish space-grabbing moves.",
        ),
        "king_safety": (
            "Protect your king",
            "Weak pawn cover turns small mistakes into tactics.",
            "Castle early, keep the pawn shield intact, and avoid unnecessary pawn pushes near your king.",
        ),
        "development": (
            "Develop before attacking",
            "Undeveloped minors leave the position disconnected.",
            "Move each minor once, connect the rooks, then look for a plan.",
        ),
    }
    lessons = []
    for index, weakness in enumerate(weaknesses[:6], start=1):
        key = weakness["key"]
        title, summary, step = playbook.get(
            key,
            (
                weakness["title"],
                weakness["detail"],
                "Review the sample positions and replay the best move before repeating the mistake.",
            ),
        )
        lessons.append(
            {
                "id": f"lesson-{index}",
                "title": title,
                "summary": summary,
                "focus": weakness["title"],
                "steps": [
                    step,
                    f"Review the {weakness['count']} related mistakes in your analysed games.",
                    "Play a short training game and deliberately apply this idea.",
                ],
                "severity": weakness["severity"],
                "source": "local",
            }
        )
    if not lessons:
        lessons.append(
            {
                "id": "lesson-start",
                "title": "Analyse your games",
                "summary": "Run Stockfish analysis to unlock personalised lessons.",
                "focus": "analysis",
                "steps": ["Open a game", "Choose Analyze all moves", "Return here for lessons"],
                "severity": "low",
                "source": "local",
            }
        )
    return lessons


def generate_exercises(analyses, limit=12):
    exercises = []
    seen = set()
    for item in analyses or []:
        if not isinstance(item, dict):
            continue
        analysis = item.get("analysis") or {}
        metadata = {
            "game_id": item.get("game_id"),
            "date": item.get("date"),
            "opponent": item.get("opponent"),
        }
        raw_moves = analysis.get("moves") or []
        move_entries = raw_moves.values() if isinstance(raw_moves, dict) else raw_moves
        for entry in sorted(
            (item for item in move_entries if isinstance(item, dict)),
            key=lambda value: value.get("ply") or 0,
        ):
            if not isinstance(entry, dict):
                continue
            classification = entry.get("classification")
            if classification not in ("inaccuracy", "mistake", "blunder"):
                continue
            fen = entry.get("fen")
            answer = entry.get("bestMoveSan") or "—"
            played = entry.get("move") or "—"
            if not fen or answer == "—":
                continue
            fingerprint = (fen, entry.get("bestMove"))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            options = [answer]
            for candidate in played, answer:
                if candidate and candidate != "—" and candidate not in options:
                    options.append(candidate)
            exercises.append(
                {
                    "id": f"exercise-{len(exercises) + 1}",
                    "fen": fen,
                    "prompt": f"What is the strongest move here? You played {played}.",
                    "answer": answer,
                    "options": options[:3],
                    "classification": classification,
                    "explanation": entry.get("explanation") or "",
                    "whyBetter": entry.get("whyBetter") or why_is_better(entry),
                    "motifs": entry.get("motifs") or [],
                    "phase": entry.get("phase") or "",
                    "source": metadata,
                }
            )
            if len(exercises) >= limit:
                return exercises
    return exercises


def explain_why_better(entry):
    if not entry:
        return ""
    return entry.get("whyBetter") or why_is_better(entry)


def record_progress(store, username, session):
    history = progress_history(store, username)
    record = dict(session or {})
    record.setdefault("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    record.setdefault("timestamp", time.time())
    history.append(record)
    store.set_training(username, "progress", history[-200:])
    return history[-200:]


def progress_history(store, username):
    value = store.get_training(username, "progress", [])
    return value if isinstance(value, list) else []


def improvement_summary(history):
    sessions = [item for item in (history or []) if isinstance(item, dict)]
    if not sessions:
        return {
            "sessions": 0,
            "accuracy": 0,
            "trend": 0,
            "questions": 0,
            "labels": [],
            "accuracySeries": [],
            "focus": [],
            "bestStreak": 0,
        }
    accuracies = []
    focus_counts = {}
    for item in sessions:
        total = int(item.get("total") or 0)
        correct = int(item.get("correct") or 0)
        accuracies.append(round(100 * correct / total, 1) if total else 0.0)
        key = item.get("focus") or "mixed"
        focus_counts[key] = focus_counts.get(key, 0) + 1
    trend = 0.0
    if len(accuracies) >= 2:
        window = accuracies[-5:]
        midpoint = len(window) // 2
        trend = round(
            sum(window[midpoint:]) / len(window[midpoint:])
            - sum(window[:midpoint]) / max(1, midpoint),
            1,
        ) if midpoint else 0.0
    streak = best = 0
    for item in sessions:
        total = int(item.get("total") or 0)
        correct = int(item.get("correct") or 0)
        if total and correct / total >= 0.8:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return {
        "sessions": len(sessions),
        "accuracy": round(sum(accuracies) / len(accuracies), 1),
        "trend": trend,
        "questions": sum(int(item.get("total") or 0) for item in sessions),
        "labels": [str(item.get("date") or "")[-5:] for item in sessions],
        "accuracySeries": accuracies,
        "focus": [
            {"label": key, "count": count}
            for key, count in sorted(focus_counts.items(), key=lambda pair: pair[1], reverse=True)
        ],
        "bestStreak": best,
    }


def build_coaching_data(analyses, store=None, username="", llm=None):
    weaknesses = recurring_weaknesses(analyses)
    lessons = generate_lessons(weaknesses, llm=llm)
    exercises = generate_exercises(analyses)
    history = progress_history(store, username) if store else []
    return {
        "weaknesses": weaknesses,
        "lessons": lessons,
        "exercises": exercises,
        "history": history,
        "summary": improvement_summary(history),
    }


def training_report(store, username, lessons=None, exercises=None, history=None):
    history = history if history is not None else progress_history(store, username)
    lessons = lessons or []
    exercises = exercises or []
    summary = improvement_summary(history)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Insight8x8 training report", username])
    writer.writerow(["Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Sessions", summary["sessions"]])
    writer.writerow(["Average accuracy (%)", summary["accuracy"]])
    writer.writerow(["Recent trend (%)", summary["trend"]])
    writer.writerow(["Questions answered", summary["questions"]])
    writer.writerow(["Best streak", summary["bestStreak"]])
    writer.writerow([])
    writer.writerow(["Session history"])
    writer.writerow(["Date", "Focus", "Correct", "Total", "Accuracy (%)"])
    for item in history:
        total = int(item.get("total") or 0)
        correct = int(item.get("correct") or 0)
        writer.writerow(
            [
                item.get("date", ""),
                item.get("focus", ""),
                correct,
                total,
                round(100 * correct / total, 1) if total else 0,
            ]
        )
    writer.writerow([])
    writer.writerow(["Lessons"])
    writer.writerow(["Title", "Focus", "Severity", "Summary"])
    for lesson in lessons:
        writer.writerow(
            [lesson.get("title", ""), lesson.get("focus", ""), lesson.get("severity", ""), lesson.get("summary", "")]
        )
    writer.writerow([])
    writer.writerow(["Recommended exercises"])
    writer.writerow(["Prompt", "Answer", "Classification", "Explanation"])
    for exercise in exercises[:30]:
        writer.writerow(
            [
                exercise.get("prompt", ""),
                exercise.get("answer", ""),
                exercise.get("classification", ""),
                exercise.get("explanation", ""),
            ]
        )
    return output.getvalue()
