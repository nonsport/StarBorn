import asyncio
import random
import logging
import re
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, html
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Загружаем переменные окружения из файла .env
load_dotenv()

# Включаем логирование
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
NASA_API_KEY = os.getenv("NASA_API_KEY")

if not BOT_TOKEN or not NASA_API_KEY:
    raise ValueError("Убедитесь, что BOT_TOKEN и NASA_API_KEY добавлены в файл .env")

# Базы данных в оперативной памяти (для production лучше использовать SQLite/PostgreSQL)
users_db: Dict[int, Dict[str, Any]] = {}
users_favorites: Dict[int, List[Dict[str, str]]] = {}
users_last_viewed: Dict[int, Dict[str, str]] = {}

# FSM Состояния
class AskSpace(StatesGroup):
    waiting_for_query = State()

# --- СЛОВАРИ ТЕКСТОВ И ВОПРОСОВ ---

TEXTS = {
    "ru": {
        "welcome": "🌌 <b>Добро пожаловать в StarBorn!</b>\n\nТвой гид по космосу. Никакие данные не сохраняются.",
        "choose_lang": "🌍 Выбери язык / Choose language",
        "menu": "✨ Главное меню",
        "birth": "🪐 Мой объект",
        "random": "🎲 Случайный",
        "today": "🌠 Фото дня",
        "about": "ℹ️ О проекте",
        "search": "🔍 Спросить / Поиск",
        "weather": "☀️ Погода",
        "favorites": "❤️ Избранное",
        "quiz": "🧠 Викторина",
        "send_date": "📅 <b>Отправь дату своего рождения:</b>\n<code>DD.MM.YYYY</code> (например: 12.04.1961)",
        "ask_prompt": "📝 <b>Что ты хочешь узнать?</b>\nНапиши название объекта или вопрос (например: <i>Черная дыра, Марс, Млечный путь</i>):",
        "searching": "🛰 Ищу в архивах...",
        "no_answer": "Космос пока хранит молчание... Я не нашел информацию об этом.",
        "weather_loading": "📡 Считываю данные солнечной активности NASA...",
        "fav_added": "✅ Сохранено в твою коллекцию!",
        "fav_empty": "Твоя космическая коллекция пока пуста.",
        "quiz_correct": "✅ Верно! Ты настоящий астроном.",
        "quiz_wrong": "❌ Ошибка. Правильный ответ: {ans}",
        "loading": "🛰 Связь с телескопами NASA...",
        "main_menu": "🏠 Главное меню",
        "change_lang": "🌍 Сменить язык",
        "about_text": "🚀 <b>StarBorn</b> — анонимный астрономический ассистент.",
        "error_date": "❌ Неверный формат даты: <code>DD.MM.YYYY</code>",
        "save_btn": "❤️ Сохранить",
    },
    "en": {
        "welcome": "🌌 <b>Welcome to StarBorn!</b>\n\nYour cosmic guide. No data is logged.",
        "choose_lang": "🌍 Choose language",
        "menu": "✨ Main menu",
        "birth": "🪐 My object",
        "random": "🎲 Random",
        "today": "🌠 APOD",
        "about": "ℹ️ About",
        "search": "🔍 Ask / Search",
        "weather": "☀️ Weather",
        "favorites": "❤️ Favorites",
        "quiz": "🧠 Quiz",
        "send_date": "📅 <b>Send your birth date:</b>\n<code>DD.MM.YYYY</code>",
        "ask_prompt": "📝 <b>What do you want to know?</b>\nType an object or question (e.g., <i>Black hole, Mars</i>):",
        "searching": "🛰 Scanning archives...",
        "no_answer": "The cosmos remains silent... No data found.",
        "weather_loading": "📡 Fetching NASA solar activity data...",
        "fav_added": "✅ Saved to favorites!",
        "fav_empty": "Your collection is empty.",
        "quiz_correct": "✅ Correct! You're a true astronomer.",
        "quiz_wrong": "❌ Wrong. The correct answer is: {ans}",
        "loading": "🛰 Connecting to telescopes...",
        "main_menu": "🏠 Main menu",
        "change_lang": "🌍 Change language",
        "about_text": "🚀 <b>StarBorn</b> — an anonymous space assistant.",
        "error_date": "❌ Invalid format: <code>DD.MM.YYYY</code>",
        "save_btn": "❤️ Save",
    }
}

QUIZ = [
    {"q_ru": "Какая планета самая горячая?", "q_en": "Which planet is the hottest?", "opts_ru": ["Венера", "Меркурий", "Марс", "Юпитер"], "opts_en": ["Venus", "Mercury", "Mars", "Jupiter"], "ans": 0},
    {"q_ru": "Как называется наша галактика?", "q_en": "What is our galaxy called?", "opts_ru": ["Андромеда", "Млечный Путь", "Сомбреро", "Сигара"], "opts_en": ["Andromeda", "Milky Way", "Sombrero", "Cigar"], "ans": 1},
    {"q_ru": "Что находится в центре Млечного Пути?", "q_en": "What is at the center of the Milky Way?", "opts_ru": ["Пульсар", "Нейтронная звезда", "Сверхмассивная черная дыра", "Квазар"], "opts_en": ["Pulsar", "Neutron Star", "Supermassive Black Hole", "Quasar"], "ans": 2}
]

FALLBACK_OBJECTS = [
    {"name": "TRAPPIST-1", "distance": "40 light-years", "wiki_title": "TRAPPIST-1"},
    {"name": "Europa", "distance": "628 million km", "wiki_title": "Europa (moon)"},
    {"name": "Kepler-22b", "distance": "600 light-years", "wiki_title": "Kepler-22b"},
]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И КНОПКИ ---

def get_lang(user_id: int) -> str:
    return users_db.get(user_id, {}).get("lang", "en")

def get_safe_text(title: str, body: str, max_len: int = 800) -> str:
    clean_body = re.sub(r'<[^>]+>', '', body if body else "")
    if len(clean_body) > max_len:
        clean_body = clean_body[:max_len] + "..."
    return f"<b>{html.quote(title)}</b>\n\n{html.quote(clean_body)}"

def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
    ])

def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["birth"], callback_data="birth"), InlineKeyboardButton(text=t["random"], callback_data="random")],
        [InlineKeyboardButton(text=t["today"], callback_data="today"), InlineKeyboardButton(text=t["search"], callback_data="search")],
        [InlineKeyboardButton(text=t["weather"], callback_data="weather"), InlineKeyboardButton(text=t["favorites"], callback_data="favorites")],
        [InlineKeyboardButton(text=t["quiz"], callback_data="quiz"), InlineKeyboardButton(text=t["about"], callback_data="about")]
    ])

def reply_keyboard(lang: str) -> ReplyKeyboardMarkup:
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t["main_menu"]), KeyboardButton(text=t["change_lang"])]], resize_keyboard=True)

def object_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXTS[lang]["save_btn"], callback_data="save_fav")]])

# --- API КЛИЕНТ (NASA, WIKIPEDIA, GOOGLE TRANSLATE) ---

class SpaceAPI:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.headers = {"User-Agent": "StarBornBot/3.0"}

    async def translate(self, text: str, target: str = "ru") -> str:
        if not text: return ""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": target, "dt": "t"}
        try:
            async with self.session.post(url, params=params, data={"q": text}, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return "".join([chunk[0] for chunk in data[0] if chunk[0]])
        except Exception:
            pass
        return text

    async def search_wiki(self, query: str, lang: str) -> Optional[Dict[str, str]]:
        """Ищет статью (Fuzzy Search) и возвращает ее заголовок и summary"""
        url_search = f"https://{lang}.wikipedia.org/w/api.php"
        params = {"action": "opensearch", "search": query, "limit": 1, "format": "json"}
        try:
            async with self.session.get(url_search, params=params, timeout=5) as resp:
                data = await resp.json()
                if len(data[1]) > 0:
                    title = data[1][0]
                    # Получаем выжимку статьи
                    url_summary = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
                    async with self.session.get(url_summary, headers=self.headers) as s_resp:
                        if s_resp.status == 200:
                            s_data = await s_resp.json()
                            return {"title": title, "summary": s_data.get("extract", "")}
        except Exception:
            pass
        return None

    async def get_space_weather(self, lang: str) -> str:
        """Получает отчет о солнечных вспышках из NASA DONKI"""
        url = f"https://api.nasa.gov/DONKI/notifications?type=all&api_key={NASA_API_KEY}"
        try:
            async with self.session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list):
                        msg = data[0].get("messageBody", "").split("##")[0] # Берем основную суть
                        if lang == "ru":
                            msg = await self.translate(msg, "ru")
                        return f"⚠️ <b>Space Weather Alert (DONKI)</b>\n\n{html.quote(msg[:800])}..."
        except Exception:
            pass
        return "☀️ Активности не зафиксировано. Геомагнитное поле в норме." if lang == "ru" else "☀️ No significant solar activity. Geomagnetic field is quiet."

    async def get_apod(self, date: Optional[str] = None, is_random: bool = False) -> Optional[dict]:
        url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
        if date: url += f"&date={date}"
        elif is_random: url += "&count=1"
        try:
            async with self.session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[0] if isinstance(data, list) else data
        except Exception:
            pass
        return None

# --- ОТПРАВЩИК МЕДИА ---

async def send_apod_media(message: Message, apod_data: dict, caption: str, user_id: int):
    media_url = apod_data.get("hdurl") or apod_data.get("url")
    media_type = apod_data.get("media_type", "image")
    lang = get_lang(user_id)
    kb = object_keyboard(lang)

    # Сохраняем в кэш для кнопки "В избранное"
    users_last_viewed[user_id] = {"caption": caption, "url": media_url, "type": media_type}

    if media_url and media_type == "image":
        await message.answer_photo(photo=media_url, caption=caption, reply_markup=kb)
    else:
        video_note = f"\n\n🎥 <b>Video Link:</b> {media_url}" if media_url else ""
        await message.answer(caption + video_note, reply_markup=kb)

# --- ХЕНДЛЕРЫ МЕНЮ И FSM ---

dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🌌 <b>StarBorn</b>", reply_markup=language_keyboard())

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = callback.data.split("_")[1]
    users_db[callback.from_user.id] = {"lang": lang}
    await callback.message.answer(TEXTS[lang]["welcome"], reply_markup=reply_keyboard(lang))
    await callback.message.answer(TEXTS[lang]["menu"], reply_markup=menu_keyboard(lang))
    await callback.answer()

@dp.message(F.text.in_({"🏠 Главное меню", "🏠 Main menu"}))
async def main_menu(message: Message, state: FSMContext):
    await state.clear()
    lang = get_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["menu"], reply_markup=menu_keyboard(lang))

@dp.message(F.text.in_({"🌍 Сменить язык", "🌍 Change language"}))
async def change_language(message: Message, state: FSMContext):
    await state.clear()
    lang = get_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["choose_lang"], reply_markup=language_keyboard())

# --- НОВЫЕ ФИЧИ ---

@dp.callback_query(F.data == "search")
async def search_init(callback: CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await callback.message.answer(TEXTS[lang]["ask_prompt"])
    await state.set_state(AskSpace.waiting_for_query)
    await callback.answer()

@dp.message(StateFilter(AskSpace.waiting_for_query))
async def search_process(message: Message, api: SpaceAPI, state: FSMContext):
    await state.clear()
    lang = get_lang(message.from_user.id)
    await message.answer(TEXTS[lang]["searching"])
    
    # Ищем в википедии (если RU - ищем в русской, чтобы было точнее)
    wiki_lang = "ru" if lang == "ru" else "en"
    wiki_data = await api.search_wiki(message.text.strip(), wiki_lang)
    
    if wiki_data:
        caption = get_safe_text(wiki_data['title'], wiki_data['summary'])
        # Сохраняем текстовый ответ в кэш для Избранного (без картинки)
        users_last_viewed[message.from_user.id] = {"caption": f"🔍 {caption}", "url": "", "type": "text"}
        await message.answer(f"🔍 {caption}", reply_markup=object_keyboard(lang))
    else:
        await message.answer(TEXTS[lang]["no_answer"])

@dp.callback_query(F.data == "weather")
async def weather_handler(callback: CallbackQuery, api: SpaceAPI):
    lang = get_lang(callback.from_user.id)
    await callback.message.answer(TEXTS[lang]["weather_loading"])
    weather_report = await api.get_space_weather(lang)
    await callback.message.answer(weather_report)
    await callback.answer()

@dp.callback_query(F.data == "save_fav")
async def save_to_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    item = users_last_viewed.get(user_id)
    
    if item:
        if user_id not in users_favorites:
            users_favorites[user_id] = []
        # Не сохраняем дубликаты
        if item not in users_favorites[user_id]:
            users_favorites[user_id].append(item)
        await callback.answer(TEXTS[lang]["fav_added"], show_alert=True)
    else:
        await callback.answer()

@dp.callback_query(F.data == "favorites")
async def show_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = get_lang(user_id)
    favs = users_favorites.get(user_id, [])
    
    if not favs:
        await callback.message.answer(TEXTS[lang]["fav_empty"])
    else:
        for item in favs[-3:]: # Показываем последние 3 сохраненных
            if item["type"] == "image" and item["url"]:
                await callback.message.answer_photo(photo=item["url"], caption=item["caption"])
            else:
                await callback.message.answer(item["caption"])
    await callback.answer()

@dp.callback_query(F.data == "quiz")
async def quiz_handler(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    q_data = random.choice(QUIZ)
    
    question = q_data[f"q_{lang}"]
    options = q_data[f"opts_{lang}"]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"qans_{QUIZ.index(q_data)}_{i}")]
        for i, opt in enumerate(options)
    ])
    
    await callback.message.answer(f"🧠 <b>{question}</b>", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("qans_"))
async def quiz_answer(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    data = callback.data.split("_")
    q_idx, ans_idx = int(data[1]), int(data[2])
    
    correct_ans = QUIZ[q_idx]["ans"]
    correct_text = QUIZ[q_idx][f"opts_{lang}"][correct_ans]
    
    if ans_idx == correct_ans:
        await callback.message.answer(TEXTS[lang]["quiz_correct"])
    else:
        await callback.message.answer(TEXTS[lang]["quiz_wrong"].format(ans=correct_text))
    await callback.answer()

# --- СТАРЫЕ ХЕНДЛЕРЫ ---

@dp.callback_query(F.data == "about")
async def about_handler(callback: CallbackQuery):
    await callback.message.answer(TEXTS[get_lang(callback.from_user.id)]["about_text"])
    await callback.answer()

@dp.callback_query(F.data == "birth")
async def birth_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(TEXTS[get_lang(callback.from_user.id)]["send_date"])
    await callback.answer()

@dp.callback_query(F.data == "today")
async def today_handler(callback: CallbackQuery, api: SpaceAPI):
    lang = get_lang(callback.from_user.id)
    apod_data = await api.get_apod()
    if apod_data:
        title = await api.translate(apod_data.get("title", ""), lang) if lang == "ru" else apod_data.get("title", "")
        exp = await api.translate(apod_data.get("explanation", ""), lang) if lang == "ru" else apod_data.get("explanation", "")
        await send_apod_media(callback.message, apod_data, f"🌠 <b>APOD</b>\n\n" + get_safe_text(title, exp), callback.from_user.id)
    await callback.answer()

@dp.callback_query(F.data == "random")
async def random_object_handler(callback: CallbackQuery, api: SpaceAPI):
    lang = get_lang(callback.from_user.id)
    apod_data = await api.get_apod(is_random=True)
    if apod_data:
        title = await api.translate(apod_data.get("title", ""), lang) if lang == "ru" else apod_data.get("title", "")
        exp = await api.translate(apod_data.get("explanation", ""), lang) if lang == "ru" else apod_data.get("explanation", "")
        await send_apod_media(callback.message, apod_data, f"🎲 <b>Random</b>\n\n" + get_safe_text(title, exp), callback.from_user.id)
    else:
        obj = random.choice(FALLBACK_OBJECTS)
        wiki = await api.search_wiki(obj["wiki_title"], "ru" if lang == "ru" else "en")
        caption = get_safe_text(obj["name"], wiki["summary"] if wiki else "No data")
        users_last_viewed[callback.from_user.id] = {"caption": caption, "url": "", "type": "text"}
        await callback.message.answer(caption, reply_markup=object_keyboard(lang))
    await callback.answer()

@dp.message()
async def process_birth_date(message: Message, api: SpaceAPI):
    lang = get_lang(message.from_user.id)
    try:
        birth_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        return # Игнорируем обычный текст, если не в состоянии поиска
    
    await message.answer(TEXTS[lang]["loading"])
    apod_data = await api.get_apod(date=birth_date.strftime("%Y-%m-%d"))
    
    if apod_data:
        title = await api.translate(apod_data.get("title", ""), lang) if lang == "ru" else apod_data.get("title", "")
        exp = await api.translate(apod_data.get("explanation", ""), lang) if lang == "ru" else apod_data.get("explanation", "")
        await send_apod_media(message, apod_data, f"🪐 <b>{message.text}</b>\n\n" + get_safe_text(title, exp), message.from_user.id)
    else:
        await message.answer("Архивы за этот день недоступны.")

# --- ИНИЦИАЛИЗАЦИЯ ---

async def on_startup(dispatcher: Dispatcher, bot: Bot):
    session = aiohttp.ClientSession()
    api = SpaceAPI(session)
    dispatcher["session"] = session
    dispatcher.workflow_data.update(api=api)

async def on_shutdown(dispatcher: Dispatcher):
    session = dispatcher.get("session")
    if session: await session.close()

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

