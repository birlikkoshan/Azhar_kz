import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from telegram import (  # type: ignore[import]
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (  # type: ignore[import]
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from content.loader import (
    get_lesson_for_user,
    get_quiz_questions_from_sentances,
    get_trend_phrases,
    load_lessons,
)
from storage.db import init_db
from storage.repositories import user_repo, vocab_repo


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


MAIN_MENU_BUTTONS = [
    ["Бүгінгі сабақ", "Мини-тест"],
    ["Сөздік", "Тренд сөздер"],
    ["Баптау"],
    ["Меню"],
]


def get_bot_token() -> str:
    """Read bot token from environment."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set. "
            "Create a .env file based on .env.example or export BOT_TOKEN in your shell."
        )
    return token


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Single place for main menu reply keyboard layout."""
    keyboard = [
        [KeyboardButton(text=label) for label in row] for row in MAIN_MENU_BUTTONS
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


CONTENT_ERROR_MSG = "Контент табылмады, әкімшіге хабарласыңыз."


async def _reply_content_error(message) -> None:
    """Send content-error message with main menu keyboard."""
    await message.reply_text(CONTENT_ERROR_MSG, reply_markup=build_main_menu_keyboard())


async def _send_main_menu(update: Update, text: str) -> None:
    keyboard = build_main_menu_keyboard()
    if update.message:
        await update.message.reply_text(text=text, reply_markup=keyboard)
    elif update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(text=text, reply_markup=keyboard)


def _build_lesson_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("Сөздерді сақта", callback_data="lesson:save"),
            InlineKeyboardButton("Келесі сабақ", callback_data="lesson:next"),
        ],
        [InlineKeyboardButton("Меню", callback_data="lesson:menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _format_lesson_text(lesson: Dict[str, Any]) -> str:
    title = str(lesson.get("topic") or "")
    words: List[Dict[str, Any]] = lesson.get("words") or []
    dialog_lines: List[str] = lesson.get("dialog") or []
    task: Dict[str, Any] = lesson.get("task") or {}

    lines: List[str] = []
    if title:
        lines.append(f"📚 {title}")
        lines.append("")

    if words:
        lines.append("Сөздер:")
        for item in words[:3]:
            word = item.get("word") or ""
            translation = item.get("translation") or ""
            example = item.get("example") or ""
            line = f"- {word} — {translation}"
            if example:
                line += f" ({example})"
            lines.append(line)
        lines.append("")

    if dialog_lines:
        lines.append("Диалог:")
        lines.extend(dialog_lines)
        lines.append("")

    question = task.get("question")
    if question:
        lines.append("Тапсырма:")
        lines.append(question)

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command: ensure user exists and show main menu keyboard."""
    user = update.effective_user
    if user is not None:
        try:
            user_repo.upsert_user(telegram_id=user.id)
        except Exception:
            logger.exception("Failed to upsert user in database")
        logger.info("User %s started", user.id)
    await _send_main_menu(update, "Сәлем! Бұл боттың басты мәзірі.")


HELP_TEXT = """Қол жетімді командалар:
/start — Старт және басты мәзір
/lesson — Бүгінгі сабақ
/quiz — Мини-тест
/vocab — Сөздік
/trend — Тренд сөздер
/help — Бұл көмек"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(HELP_TEXT)


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show level selection inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("A1", callback_data="level:A1"),
            InlineKeyboardButton("A2", callback_data="level:A2"),
        ],
        [
            InlineKeyboardButton("B1", callback_data="level:B1"),
            InlineKeyboardButton("B2", callback_data="level:B2"),
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Деңгейіңізді таңдаңыз:", reply_markup=markup)


async def level_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle level selection from inline keyboard."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    if not query.data.startswith("level:"):
        return

    level = query.data.split(":", 1)[1]
    user = query.from_user
    try:
        user_repo.set_level(telegram_id=user.id, level=level)
    except Exception:
        logger.exception("Failed to set user level")

    await _send_main_menu(update, f"Деңгей сақталды: {level}")


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Меню' button: just show main menu."""
    await _send_main_menu(update, "Негізгі мәзір.")


async def today_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Бүгінгі сабақ' button: show lesson for current level.

    We treat users.last_lesson_id as the last lesson that was displayed;
    each time we show a lesson we update this field.
    """
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return

    user = user_repo.get_user(tg_user.id)
    if user is None:
        user_repo.upsert_user(telegram_id=tg_user.id)
        user = user_repo.get_user(tg_user.id)

    level = (user or {}).get("level") or "A1"
    if not (user or {}).get("level"):
        try:
            user_repo.set_level(tg_user.id, level)
        except Exception:
            logger.exception("Failed to set default level for user")

    last_lesson_id = (user or {}).get("last_lesson_id")
    try:
        lesson = get_lesson_for_user(level, last_lesson_id)
    except Exception:
        logger.warning("Content load failed (lesson)", exc_info=True)
        await _reply_content_error(update.message)
        return
    if lesson is None:
        await update.message.reply_text(
            "Сабақ табылмады. Кейінірек қайталап көріңіз.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    try:
        user_repo.upsert_user(
            telegram_id=tg_user.id,
            level=level,
            last_lesson_id=str(lesson.get("id")),
        )
    except Exception:
        logger.exception("Failed to update last_lesson_id for user")

    logger.info("Lesson shown for user %s level %s", tg_user.id, level)
    text = _format_lesson_text(lesson)
    await update.message.reply_text(text, reply_markup=_build_lesson_keyboard())


async def lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle lesson-related inline buttons."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    data = query.data
    tg_user = query.from_user
    if not tg_user or not query.message:
        return

    if data == "lesson:menu":
        await _send_main_menu(update, "Негізгі мәзір.")
        return

    user = user_repo.get_user(tg_user.id)
    level = (user or {}).get("level") or "A1"
    last_lesson_id = (user or {}).get("last_lesson_id")

    if data == "lesson:next":
        try:
            lesson = get_lesson_for_user(level, last_lesson_id)
        except Exception:
            logger.warning("Content load failed (lesson)", exc_info=True)
            await _reply_content_error(query.message)
            return
        if lesson is None:
            await query.message.reply_text(
                "Сабақ табылмады. Кейінірек қайталап көріңіз.",
                reply_markup=build_main_menu_keyboard(),
            )
            return

        try:
            user_repo.upsert_user(
                telegram_id=tg_user.id,
                level=level,
                last_lesson_id=str(lesson.get("id")),
            )
        except Exception:
            logger.exception("Failed to update last_lesson_id for user")

        text = _format_lesson_text(lesson)
        await query.message.reply_text(text, reply_markup=_build_lesson_keyboard())
        return

    if data == "lesson:save":
        if not last_lesson_id:
            await query.message.reply_text("Алдымен сабақты ашыңыз.")
            return
        try:
            lessons = load_lessons()
        except Exception:
            logger.warning("Content load failed (lessons)", exc_info=True)
            await _reply_content_error(query.message)
            return
        current = None
        for item in lessons:
            if str(item.get("id")) == str(last_lesson_id):
                current = item
                break

        if not current:
            await query.message.reply_text("Сабақты табу мүмкін болмады.")
            return

        words = (current.get("words") or [])[:3]
        try:
            vocab_repo.add_words(tg_user.id, words)
        except Exception:
            logger.exception("Failed to save vocab words")
            await query.message.reply_text("Сөздерді сақтау кезінде қате кетті.")
            return

        count = len(words)
        await query.message.reply_text(f"Сақталды: {count} сөз")


# In-memory quiz state: quiz_questions, quiz_index, quiz_score, quiz_correct_index,
# quiz_answer_log (for result review), quiz_current_question, quiz_current_options.
def _quiz_state(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    return context.user_data


def _shuffle_question_options(question: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Return (question with shuffled options, new correct index in 0..n-1)."""
    options: List[str] = question.get("options") or []
    correct = question.get("correct", 0)
    if len(options) <= 1:
        return (question, correct)
    pairs = list(zip(options, range(len(options))))
    random.shuffle(pairs)
    shuffled_options = [p[0] for p in pairs]
    new_correct = next(i for i, p in enumerate(pairs) if p[1] == correct)
    return ({**question, "options": shuffled_options}, new_correct)


def _build_quiz_keyboard(question: Dict[str, Any]) -> InlineKeyboardMarkup:
    options: List[str] = question.get("options") or []
    # One button per row (column layout); Telegram button text limit 64 chars
    rows = [
        [
            InlineKeyboardButton(
                (opt[:64] if len(opt) > 64 else opt) or str(i),
                callback_data=f"quiz:ans:{i}",
            )
        ]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(rows)


def _build_quiz_questions_from_vocab(vocab_items: List[Dict[str, Any]], count: int = 15) -> List[Dict[str, Any]]:
    """Build quiz questions from user's vocab (word -> translation). Needs at least 3 items."""
    if len(vocab_items) < 3:
        return []
    translations = [v.get("translation") or "" for v in vocab_items]
    questions = []
    used = set()
    for _ in range(min(count, len(vocab_items))):
        item = random.choice(vocab_items)
        word = item.get("word") or ""
        correct_ru = item.get("translation") or ""
        if word in used:
            continue
        used.add(word)
        others = [t for t in translations if t != correct_ru]
        options = [correct_ru] + random.sample(others, min(2, len(others)))
        random.shuffle(options)
        correct_idx = options.index(correct_ru)
        questions.append({
            "question": f"«{word}» нені білдіреді?",
            "options": options,
            "correct": correct_idx,
        })
    return questions


def _get_quiz_questions_for_user(telegram_id: int, level: str) -> List[Dict[str, Any]]:
    """Mini-test from user's vocab (сөздік) or from sentances.json. Prefer vocab if >= 5 words."""
    vocab = vocab_repo.random_words(telegram_id, 20)
    if len(vocab) >= 5:
        return _build_quiz_questions_from_vocab(vocab, count=15)
    try:
        return get_quiz_questions_from_sentances(level, count=15)
    except Exception:
        logger.warning("Failed to load quiz from sentances", exc_info=True)
        return []


async def mini_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start mini quiz from user's vocab (сөздік) or sentances. State kept in user_data."""
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return
    user = user_repo.get_user(tg_user.id)
    level = (user or {}).get("level") or "A1"
    try:
        questions = _get_quiz_questions_for_user(tg_user.id, level)
    except Exception:
        logger.warning("Content load failed (quiz)", exc_info=True)
        await _reply_content_error(update.message)
        return
    if not questions:
        await update.message.reply_text(
            "Сөздікте немесе сөйлемдерде жеткілікті материал жоқ. Алдымен сөздерді сақтаңыз немесе сабақ өтіңіз.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    logger.info("Quiz started for user %s (from vocab/sentances)", tg_user.id)
    state = _quiz_state(context)
    state["quiz_questions"] = questions
    state["quiz_index"] = 0
    state["quiz_score"] = 0
    state["quiz_answer_log"] = []
    q_display, new_correct = _shuffle_question_options(questions[0])
    state["quiz_correct_index"] = new_correct
    state["quiz_current_question"] = q_display.get("question") or ""
    state["quiz_current_options"] = q_display.get("options") or []
    text = f"1/{len(questions)}. {q_display.get('question') or ''}"
    await update.message.reply_text(text, reply_markup=_build_quiz_keyboard(q_display))


def _format_quiz_result(score: int, total: int, answer_log: List[Dict[str, Any]]) -> str:
    """Score and review with emojis; for wrong answers show user choice and right answer."""
    pct = (100 * score // total) if total else 0
    if pct == 100:
        head = f"🎉 Сіз: {score}/{total} — тамаша!"
    elif pct >= 70:
        head = f"👍 Сіз: {score}/{total} — жақсы!"
    else:
        head = f"📊 Сіз: {score}/{total}"
    lines = [head, ""]
    for entry in answer_log:
        q = entry.get("question") or ""
        opts = entry.get("options") or []
        ci = entry.get("correct_idx", 0)
        ch = entry.get("chosen_idx", 0)
        if ci >= len(opts) or ch >= len(opts):
            continue
        q_short = q[:45] + "…" if len(q) > 45 else q
        if ch == ci:
            lines.append(f"✅ {q_short}")
            lines.append(f"   → {opts[ci][:50]}{'…' if len(opts[ci]) > 50 else ''}")
        else:
            lines.append(f"❌ {q_short}")
            lines.append(f"   Сіз таңдадыңыз: {opts[ch][:40]}{'…' if len(opts[ch]) > 40 else ''}")
            lines.append(f"   Дұрыс жауап: {opts[ci][:40]}{'…' if len(opts[ci]) > 40 else ''}")
        lines.append("")
    return "\n".join(lines).strip()


async def _edit_to_quiz_question(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    questions: List[Dict[str, Any]],
    index: int,
) -> None:
    """Replace message with next question (same message, no new one)."""
    q = questions[index]
    q_display, new_correct = _shuffle_question_options(q)
    state = _quiz_state(context)
    state["quiz_correct_index"] = new_correct
    state["quiz_current_question"] = q_display.get("question") or ""
    state["quiz_current_options"] = q_display.get("options") or []
    num = index + 1
    text = f"{num}/{len(questions)}. {q_display.get('question') or ''}"
    await message.edit_text(text, reply_markup=_build_quiz_keyboard(q_display))


async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quiz answer and navigation (quiz:ans:N, quiz:retry, quiz:menu)."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data
    tg_user = query.from_user
    if not tg_user or not query.message:
        return
    if data == "quiz:menu":
        await _send_main_menu(update, "Негізгі мәзір.")
        return
    if data == "quiz:retry":
        user = user_repo.get_user(tg_user.id)
        level = (user or {}).get("level") or "A1"
        try:
            questions = _get_quiz_questions_for_user(tg_user.id, level)
        except Exception:
            logger.warning("Content load failed (quiz retry)", exc_info=True)
            await _reply_content_error(query.message)
            return
        if not questions:
            await query.message.edit_text(
                "Сөздікте немесе сөйлемдерде жеткілікті материал жоқ. Алдымен сөздерді сақтаңыз немесе сабақ өтіңіз."
            )
            return
        state = _quiz_state(context)
        state["quiz_questions"] = questions
        state["quiz_index"] = 0
        state["quiz_score"] = 0
        state["quiz_answer_log"] = []
        q_display, new_correct = _shuffle_question_options(questions[0])
        state["quiz_correct_index"] = new_correct
        state["quiz_current_question"] = q_display.get("question") or ""
        state["quiz_current_options"] = q_display.get("options") or []
        text = f"1/{len(questions)}. {q_display.get('question') or ''}"
        await query.message.edit_text(text, reply_markup=_build_quiz_keyboard(q_display))
        return
    if not data.startswith("quiz:ans:"):
        return
    state = _quiz_state(context)
    questions = state.get("quiz_questions")
    index = state.get("quiz_index", 0)
    score = state.get("quiz_score", 0)
    if not questions or index >= len(questions):
        await query.message.reply_text("Тест аяқталды. Қайта бастау үшін «Мини-тест» басыңыз.")
        return
    chosen = int(data.split(":")[-1])
    correct_idx = state.get("quiz_correct_index", 0)
    # Log for result review (user choice vs right answer)
    log = state.get("quiz_answer_log") or []
    log.append({
        "question": state.get("quiz_current_question") or "",
        "options": list(state.get("quiz_current_options") or []),
        "correct_idx": correct_idx,
        "chosen_idx": chosen,
    })
    state["quiz_answer_log"] = log
    if chosen == correct_idx:
        score += 1
    state["quiz_score"] = score
    state["quiz_index"] = index + 1
    if index + 1 >= len(questions):
        total = len(questions)
        text = _format_quiz_result(score, total, log)
        keyboard = [
            [
                InlineKeyboardButton("Қайта тапсыру", callback_data="quiz:retry"),
                InlineKeyboardButton("Меню", callback_data="quiz:menu"),
            ]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    await _edit_to_quiz_question(query.message, context, questions, index + 1)


async def vocab_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show vocab actions menu."""
    keyboard = [
        [InlineKeyboardButton("📄 Менің сөздерім", callback_data="vocab:list")],
        [InlineKeyboardButton("🔁 Қайталау", callback_data="vocab:review")],
        [InlineKeyboardButton("🗑 Тазалау", callback_data="vocab:clear")],
        [InlineKeyboardButton("Меню", callback_data="vocab:menu")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Сөздік мәзірі:", reply_markup=markup)


async def vocab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle vocab-related inline buttons."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    data = query.data
    tg_user = query.from_user
    if not tg_user or not query.message:
        return

    if data == "vocab:menu":
        await _send_main_menu(update, "Негізгі мәзір.")
        return

    if data == "vocab:list":
        words = vocab_repo.list_words(tg_user.id)[:20]
        if not words:
            await query.message.reply_text("Сөздік бос.")
            return

        lines = ["📄 Менің сөздерім (соңғы 20):", ""]
        for item in words:
            word = item.get("word") or ""
            translation = item.get("translation") or ""
            lines.append(f"- {word} — {translation}")

        await query.message.reply_text("\n".join(lines))
        return

    if data == "vocab:review":
        words = vocab_repo.random_words(tg_user.id, 5)
        if not words:
            await query.message.reply_text("Сөздік бос.")
            return

        context.user_data["vocab_review_words"] = words
        lines = ["🔁 Қайталау:", ""]
        for item in words:
            word = item.get("word") or ""
            lines.append(f"- {word}")

        keyboard = [
            [
                InlineKeyboardButton(
                    "Көрсету аударма", callback_data="vocab:review_show"
                )
            ],
            [InlineKeyboardButton("Меню", callback_data="vocab:menu")],
        ]
        await query.message.reply_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "vocab:review_show":
        words = context.user_data.get("vocab_review_words") or []
        if not words:
            await query.message.reply_text("Қайталау үшін сөздер табылмады.")
            return

        lines = ["Аударма мен мысалдар:", ""]
        for item in words:
            word = item.get("word") or ""
            translation = item.get("translation") or ""
            example = item.get("example") or ""
            line = f"- {word} — {translation}"
            if example:
                line += f" ({example})"
            lines.append(line)

        await query.message.reply_text("\n".join(lines))
        return

    if data == "vocab:clear":
        keyboard = [
            [
                InlineKeyboardButton("Иә", callback_data="vocab:clear_yes"),
                InlineKeyboardButton("Жоқ", callback_data="vocab:clear_no"),
            ]
        ]
        await query.message.reply_text(
            "Барлық сөздерді өшіруді қалайсыз ба?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "vocab:clear_yes":
        try:
            vocab_repo.clear_all(tg_user.id)
        except Exception:
            logger.exception("Failed to clear vocab")
            await query.message.reply_text("Сөздерді өшіру кезінде қате кетті.")
            return

        await query.message.reply_text("Сөздік тазаланды.")
        return

    if data == "vocab:clear_no":
        await query.message.reply_text("Өшіру болдырылмады.")


def _format_trends_message(phrases: List[Dict[str, Any]]) -> str:
    lines = ["🔥 Тренд сөздер:", ""]
    for i, p in enumerate(phrases, 1):
        phrase = p.get("phrase") or ""
        meaning = p.get("meaning") or ""
        example = p.get("example") or ""
        lines.append(f"{i}. {phrase} — {meaning}")
        if example:
            lines.append(f"   {example}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_trends_keyboard(phrase_count: int) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton("Сөздікке қосу", callback_data=f"trend:add:{i}")
        for i in range(phrase_count)
    ]
    keyboard = [row] if phrase_count <= 3 else [row[:3], row[3:]]
    keyboard.append([InlineKeyboardButton("Көбірек", callback_data="trend:more")])
    keyboard.append([InlineKeyboardButton("Меню", callback_data="trend:menu")])
    return InlineKeyboardMarkup(keyboard)


async def trend_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show 3 random trend phrases for user level."""
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return
    user = user_repo.get_user(tg_user.id)
    level = (user or {}).get("level") or "A1"
    try:
        phrases = get_trend_phrases(level, 3)
    except Exception:
        logger.warning("Content load failed (trends)", exc_info=True)
        await _reply_content_error(update.message)
        return
    if not phrases:
        await update.message.reply_text(
            "Сіздің деңгейіңізге тренд сөздер табылмады.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    logger.info("Trends shown for user %s level %s", tg_user.id, level)
    context.user_data["trend_phrases"] = phrases
    await update.message.reply_text(
        _format_trends_message(phrases),
        reply_markup=_build_trends_keyboard(len(phrases)),
    )


async def trend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trend buttons: add to vocab, more, menu."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data
    tg_user = query.from_user
    if not tg_user or not query.message:
        return
    if data == "trend:menu":
        await _send_main_menu(update, "Негізгі мәзір.")
        return
    if data == "trend:more":
        user = user_repo.get_user(tg_user.id)
        level = (user or {}).get("level") or "A1"
        try:
            phrases = get_trend_phrases(level, 3)
        except Exception:
            logger.warning("Content load failed (trends more)", exc_info=True)
            await _reply_content_error(query.message)
            return
        if not phrases:
            await query.message.reply_text("Тренд сөздер табылмады.")
            return
        context.user_data["trend_phrases"] = phrases
        await query.message.reply_text(
            _format_trends_message(phrases),
            reply_markup=_build_trends_keyboard(len(phrases)),
        )
        return
    if data.startswith("trend:add:"):
        idx = int(data.split(":")[-1])
        phrases = context.user_data.get("trend_phrases") or []
        if idx < 0 or idx >= len(phrases):
            await query.message.reply_text("Сөз табылмады.")
            return
        p = phrases[idx]
        word = {"word": p.get("phrase"), "translation": p.get("meaning"), "example": p.get("example")}
        try:
            vocab_repo.add_words(tg_user.id, [word])
        except Exception:
            logger.exception("Failed to add trend word to vocab")
            await query.message.reply_text("Сөзді сақтау кезінде қате кетті.")
            return
        await query.message.reply_text("Сақталды.")


async def _set_bot_commands(application) -> None:
    """Register command list in Telegram menu (visible when user taps /)."""
    await application.bot.set_my_commands([
        BotCommand("start", "Старт және мәзір"),
        BotCommand("lesson", "Бүгінгі сабақ"),
        BotCommand("quiz", "Мини-тест"),
        BotCommand("vocab", "Сөздік"),
        BotCommand("trend", "Тренд сөздер"),
        BotCommand("help", "Көмек"),
    ])


def main() -> None:
    init_db()
    token = get_bot_token()
    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(_set_bot_commands)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("lesson", today_lesson))
    application.add_handler(CommandHandler("quiz", mini_test))
    application.add_handler(CommandHandler("vocab", vocab_menu))
    application.add_handler(CommandHandler("trend", trend_menu))
    application.add_handler(MessageHandler(filters.Regex("^Баптау$"), settings_menu))
    application.add_handler(MessageHandler(filters.Regex("^Меню$"), menu_button))
    application.add_handler(MessageHandler(filters.Regex("^Сөздік$"), vocab_menu))
    application.add_handler(MessageHandler(filters.Regex("^Тренд сөздер$"), trend_menu))
    application.add_handler(
        CallbackQueryHandler(level_callback, pattern=r"^level:")
    )
    application.add_handler(
        MessageHandler(filters.Regex("^Бүгінгі сабақ$"), today_lesson)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^Мини-тест$"), mini_test)
    )
    application.add_handler(CallbackQueryHandler(lesson_callback, pattern=r"^lesson:"))
    application.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz:"))
    application.add_handler(CallbackQueryHandler(vocab_callback, pattern=r"^vocab:"))
    application.add_handler(CallbackQueryHandler(trend_callback, pattern=r"^trend:"))

    application.run_polling()


if __name__ == "__main__":
    main()

