import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def _lessons_path() -> Path:
    return Path(__file__).resolve().parent / "lessons.json"


def _quizzes_path() -> Path:
    return Path(__file__).resolve().parent / "quizzes.json"


def _trends_path() -> Path:
    return Path(__file__).resolve().parent / "trends.json"


def _sentances_path() -> Path:
    return Path(__file__).resolve().parent / "sentances.json"


def load_sentances() -> Dict[str, Dict[str, str]]:
    """Load sentances.json: {level: {kz_sentence: ru_translation}}. Returns {} on error."""
    path = _sentances_path()
    if not path.exists():
        logger.warning("Sentances file %s not found.", path)
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.exception("Failed to read sentances file %s.", path)
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("Failed to parse sentances JSON from %s.", path)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def get_quiz_questions_from_sentances(level: str, count: int = 15) -> List[Dict[str, Any]]:
    """Build quiz questions from sentances.json for level. Each: question, options, correct."""
    data = load_sentances()
    level_data = data.get(level) or {}
    pairs = [(k, v) for k, v in level_data.items()]
    if len(pairs) < 3:
        return []
    questions = []
    used = set()
    for _ in range(min(count, len(pairs))):
        kz, correct_ru = random.choice(pairs)
        if kz in used:
            continue
        used.add(kz)
        others = [ru for k, ru in pairs if ru != correct_ru]
        options = [correct_ru] + random.sample(others, min(2, len(others)))
        random.shuffle(options)
        correct_idx = options.index(correct_ru)
        questions.append({
            "question": f"«{kz}» нені білдіреді?",
            "options": options,
            "correct": correct_idx,
        })
    return questions


def load_lessons() -> List[Dict[str, Any]]:
    """Load lessons list from content/lessons.json.

    Returns an empty list and logs a warning on errors.
    """
    path = _lessons_path()
    if not path.exists():
        logger.warning("Lessons file %s not found.", path)
        return []

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.exception("Failed to read lessons file %s.", path)
        return []

    if not raw:
        logger.warning("Lessons file %s is empty.", path)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("Failed to parse lessons JSON from %s.", path)
        return []

    if not isinstance(data, list):
        logger.warning("Lessons file %s does not contain a list at root.", path)
        return []

    return data


def get_lesson_for_user(
    level: str, last_lesson_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Return next lesson for user level based on last_lesson_id.

    Lessons are ordered by their 'id' field. If last_lesson_id is not found,
    the first lesson for that level is returned. If no lessons for level, None.
    """
    lessons = [l for l in load_lessons() if l.get("level") == level]
    if not lessons:
        return None

    lessons_sorted = sorted(lessons, key=lambda l: str(l.get("id", "")))

    if not last_lesson_id:
        return lessons_sorted[0]

    current_index = None
    for idx, lesson in enumerate(lessons_sorted):
        if str(lesson.get("id")) == str(last_lesson_id):
            current_index = idx
            break

    if current_index is None:
        return lessons_sorted[0]

    next_index = (current_index + 1) % len(lessons_sorted)
    return lessons_sorted[next_index]


def load_quizzes() -> List[Dict[str, Any]]:
    """Load quizzes list from content/quizzes.json. Returns [] on error."""
    path = _quizzes_path()
    if not path.exists():
        logger.warning("Quizzes file %s not found.", path)
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.exception("Failed to read quizzes file %s.", path)
        return []
    if not raw:
        logger.warning("Quizzes file %s is empty.", path)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("Failed to parse quizzes JSON from %s.", path)
        return []
    if not isinstance(data, list):
        logger.warning("Quizzes file %s does not contain a list at root.", path)
        return []
    return data


def get_quiz(level: str) -> Optional[Dict[str, Any]]:
    """Return first quiz for level, or None. Quiz has id, level, questions[]."""
    quizzes = [q for q in load_quizzes() if q.get("level") == level]
    return quizzes[0] if quizzes else None


def load_trends() -> Dict[str, List[Dict[str, Any]]]:
    """Load trends from content/trends.json. Keys: level, values: list of {phrase, meaning, example}."""
    path = _trends_path()
    if not path.exists():
        logger.warning("Trends file %s not found.", path)
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.exception("Failed to read trends file %s.", path)
        return {}
    if not raw:
        logger.warning("Trends file %s is empty.", path)
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("Failed to parse trends JSON from %s.", path)
        return {}
    if not isinstance(data, dict):
        logger.warning("Trends file %s does not contain an object at root.", path)
        return {}
    return data


def get_trend_phrases(level: str, count: int = 3) -> List[Dict[str, Any]]:
    """Return up to `count` random phrases for level. Each item: phrase, meaning, example."""
    trends = load_trends()
    level_phrases = trends.get(level) or []
    if not level_phrases:
        return []
    return random.sample(level_phrases, min(count, len(level_phrases)))

