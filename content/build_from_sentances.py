"""
Generate lessons.json, quizzes.json, trends.json from content/sentances.json.
Run from project root: python -m content.build_from_sentances
"""
import json
import random
from pathlib import Path


CONTENT_DIR = Path(__file__).resolve().parent
SENTANCES_PATH = CONTENT_DIR / "sentances.json"
LESSONS_PATH = CONTENT_DIR / "lessons.json"
QUIZZES_PATH = CONTENT_DIR / "quizzes.json"
TRENDS_PATH = CONTENT_DIR / "trends.json"


def load_sentances() -> dict:
    with open(SENTANCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def level_list(data: dict, level: str) -> list[tuple[str, str]]:
    """Return [(kz_sentence, ru_translation), ...] for level."""
    d = data.get(level) or {}
    return [(k, v) for k, v in d.items()]


def build_lessons(data: dict) -> list[dict]:
    lessons = []
    for level in ("A1", "A2", "B1", "B2"):
        pairs = level_list(data, level)
        for i in range(0, len(pairs), 3):
            chunk = pairs[i : i + 3]
            if not chunk:
                continue
            lesson_id = f"{level}-{len(lessons) + 1}"
            words = [
                {"word": kz, "translation": ru, "example": kz}
                for kz, ru in chunk
            ]
            s0, s1 = chunk[0][0], chunk[1][0] if len(chunk) > 1 else chunk[0][0]
            dialog = [f"— {s0}", f"— {s1}"]
            correct_ru = chunk[0][1]
            others = [p[1] for p in pairs if p[1] != correct_ru]
            options = [correct_ru] + random.sample(others, min(2, len(others)))
            random.shuffle(options)
            correct_idx = options.index(correct_ru)
            task = {
                "question": f"«{chunk[0][0]}» нені білдіреді?",
                "options": options,
                "correct": correct_idx,
            }
            lessons.append({
                "id": lesson_id,
                "level": level,
                "topic": f"Сөйлемдер ({level})",
                "words": words,
                "dialog": dialog,
                "task": task,
            })
    return lessons


def build_quizzes(data: dict) -> list[dict]:
    quizzes = []
    for level in ("A1", "A2", "B1", "B2"):
        pairs = level_list(data, level)
        if len(pairs) < 3:
            continue
        questions = []
        used = set()
        for _ in range(min(15, len(pairs))):
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
        if questions:
            quizzes.append({"id": f"{level}-quiz-1", "level": level, "questions": questions})
    return quizzes


def build_trends(data: dict) -> dict:
    trends = {}
    for level in ("A1", "A2", "B1", "B2"):
        pairs = level_list(data, level)
        sample = random.sample(pairs, min(10, len(pairs))) if pairs else []
        trends[level] = [
            {"phrase": kz, "meaning": ru, "example": kz}
            for kz, ru in sample
        ]
    return trends


def main():
    random.seed(42)
    data = load_sentances()
    lessons = build_lessons(data)
    random.seed(43)
    quizzes = build_quizzes(data)
    random.seed(44)
    trends = build_trends(data)
    with open(LESSONS_PATH, "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)
    with open(QUIZZES_PATH, "w", encoding="utf-8") as f:
        json.dump(quizzes, f, ensure_ascii=False, indent=2)
    with open(TRENDS_PATH, "w", encoding="utf-8") as f:
        json.dump(trends, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(lessons)} lessons, {len(quizzes)} quizzes, {sum(len(v) for v in trends.values())} trend phrases.")


if __name__ == "__main__":
    main()
