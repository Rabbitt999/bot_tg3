import asyncio
import os
import tempfile
import json
import html
import aiohttp
from datetime import datetime
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ================== НАЛАШТУВАННЯ ==================
API_ID = 30210758
API_HASH = "1e9b089b6a38dc9cd5e8978d03f5dd33"
SESSION_NAME = "SambrNewsBot"

BOT_TOKEN = "7991439480:AAGR8KyC3RnBEVlYpP8-39ExcI-SSAhmPC0"
ADMIN_ID = 6974875043

# API alerts.in.ua
ALERTS_API_TOKEN = "f7f5a126f8865ad43bbd19d522d6c489b11486c9ab2203"  # Замініть на ваш токен з https://alerts.in.ua/
ALERTS_API_BASE_URL = "https://alerts.com.ua/api"

# ID області для Львівської області (25 - Львівська область)
LVIV_REGION_ID = 25

SOURCE_CHANNELS = [
    "Test_Chenal_0",
    "dsns_lviv",
    "lviv_region_poluce",
    "lvivpatrolpolice"
]
TARGET_CHANNEL = "@Test_Chenal_0"
TARGET_CHANNEL_USERNAME = "Test_Chenal_0"
TARGET_CHANNEL_TITLE = "🧪 Test Channel"

POWER_KEYWORDS = [
    "світло", "світла", "світлу",
    "графік", "графіка", "графіку",
    "оновлений", "оновлення"
]

ALERT_START_KEYWORDS = [
    "повітряна тривога у львівській області",
    "львів повітряна тривога"
]

ALERT_END_KEYWORDS = [
    "відбій повітряної тривоги",
    "львів відбій повітряної тривоги"
]

SAMBIR_KEYWORDS = [
    "самбір", "Самборі", "самбірського", "самбірський", "самбірському"
]

DB_FILE = "database.json"
ALERT_STATE_FILE = "alert_state.json"
LAST_ALERT_CHECK_FILE = "last_alert_check.json"

# Максимальний розмір відео для завантаження (100 МБ)
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # Змінено з 50 МБ на 100 МБ


# ================== FSM ==================
class ShareStates(StatesGroup):
    waiting_info = State()
    waiting_ad = State()


# ================== СТАН ТРИВОГИ ==================
def load_alert_state():
    if not os.path.exists(ALERT_STATE_FILE):
        return {"active": False, "start_time": None}
    with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_alert_state(state: dict):
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_last_alert_check():
    if not os.path.exists(LAST_ALERT_CHECK_FILE):
        return {"last_check": datetime.now().isoformat()}
    with open(LAST_ALERT_CHECK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_last_alert_check(state: dict):
    with open(LAST_ALERT_CHECK_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours} год {minutes} хв" if hours else f"{minutes} хв"


# ================== БАЗА ==================
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================== ФУНКЦІЯ ЕКРАНУВАННЯ HTML ==================
def escape_html(text: str) -> str:
    """
    Екранує спеціальні символи для HTML
    """
    if not text:
        return ""
    return html.escape(text)


# ================== ФУНКЦІЯ ОЧИСТКИ ТРИВОГИ ==================
def clean_alert_text(text: str, is_start: bool) -> str:
    """
    Очищає текст тривоги від дублюючих емоційних символів
    """
    if not text:
        return text

    # Видаляємо зайві емоційні символи на початку
    if is_start:
        # Якщо текст вже починається з 🚨, видаляємо його з нашого форматування
        if text.strip().startswith('🚨'):
            # Повертаємо текст без додавання зайвого 🚨
            return text.strip()
    else:
        # Якщо текст вже починається з ✅, видаляємо його з нашого форматування
        if text.strip().startswith('✅'):
            # Повертаємо текст без додавання зайвого ✅
            return text.strip()

    return text.strip()


# ================== API alerts.in.ua ==================
async def check_alerts_in_ua():
    """
    Перевіряє статус повітряної тривоги через API alerts.in.ua
    Повертає:
    - None якщо помилка
    - {"active": True/False, "changed": True/False} якщо успішно
    """
    headers = {
        "X-API-Key": ALERTS_API_TOKEN,
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Отримуємо стан тривог для всіх областей
            async with session.get(f"{ALERTS_API_BASE_URL}/states", headers=headers) as response:
                if response.status != 200:
                    print(f"Помилка API: {response.status}")
                    return None

                data = await response.json()

                # Знаходимо Львівську область
                lviv_region = None
                for region in data.get("states", []):
                    if region.get("id") == LVIV_REGION_ID:
                        lviv_region = region
                        break

                if not lviv_region:
                    print("Не знайдено Львівську область в даних API")
                    return None

                # Перевіряємо чи є активна тривога
                alert_active = lviv_region.get("alert", False)

                # Завантажуємо попередній стан
                alert_state = load_alert_state()
                last_check_data = load_last_alert_check()

                changed = False

                # Якщо стан змінився
                if alert_active != alert_state["active"]:
                    changed = True

                    if alert_active:
                        # Тривога почалася
                        alert_state["active"] = True
                        alert_state["start_time"] = datetime.now().isoformat()
                        print(f"🚨 Тривога почалася у Львівській області")
                    else:
                        # Тривога закінчилася
                        alert_state["active"] = False
                        alert_state["start_time"] = None
                        print(f"✅ Відбій тривоги у Львівській області")

                    save_alert_state(alert_state)

                # Оновлюємо час останньої перевірки
                last_check_data["last_check"] = datetime.now().isoformat()
                save_last_alert_check(last_check_data)

                return {
                    "active": alert_active,
                    "changed": changed,
                    "state": alert_state
                }

    except Exception as e:
        print(f"Помилка при перевірці API alerts.in.ua: {e}")
        return None


async def send_alert_to_channel(is_start: bool, duration_seconds: int = None):
    """
    Надсилає повідомлення про тривогу або відбій у канал
    """
    footer = f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    if is_start:
        # Повідомлення про початок тривоги
        message_text = f"🚨УВАГА, повітряна тривога у Львівській області!{footer}"
        await bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про початок тривоги")
    else:
        # Повідомлення про відбій тривоги
        if duration_seconds:
            duration = format_duration(duration_seconds)
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!\n\n⏱ <b>Тривалість:</b> {duration}{footer}"
        else:
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!{footer}"

        await bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про відбій тривоги")


# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ТРИВОГ ==================
async def alerts_monitoring_task():
    """
    Фонова задача для регулярної перевірки статусу тривоги
    """
    print("🔍 Запущено моніторинг тривог через API alerts.in.ua")

    while True:
        try:
            # Чекаємо 10 секунд між перевірками
            await asyncio.sleep(10)

            # Перевіряємо статус тривоги
            alert_status = await check_alerts_in_ua()

            if alert_status and alert_status["changed"]:
                # Якщо статус змінився, надсилаємо повідомлення
                if alert_status["active"]:
                    # Тривога почалася
                    await send_alert_to_channel(is_start=True)
                else:
                    # Тривога закінчилася - розраховуємо тривалість
                    if alert_status["state"]["start_time"]:
                        start = datetime.fromisoformat(alert_status["state"]["start_time"])
                        seconds = int((datetime.now() - start).total_seconds())
                        await send_alert_to_channel(is_start=False, duration_seconds=seconds)
                    else:
                        await send_alert_to_channel(is_start=False)

        except Exception as e:
            print(f"Помилка в задачі моніторингу тривог: {e}")
            await asyncio.sleep(30)  # Чекаємо довше при помилці


# ================== TELETHON ==================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
pending_posts = {}

# ================== AIROGRAM ==================
# Змінюємо на HTML parse_mode для уникнення проблем з Markdown
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ================== ПАНЕЛЬ МЕНЮ (REPLY KEYBOARD) ==================
def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    Створює головне меню як панель під полем вводу тексту
    """
    keyboard = [
        [KeyboardButton(text="📤 Поділитися інформацією")],
        [KeyboardButton(text="📢 Розмістити рекламу")]
    ]

    # Додаємо кнопку адмін-панелі тільки для адміна
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="👑 Адмін-панель")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,  # Розтягується під розмір екрану
        one_time_keyboard=False,  # Не сховається після натискання
        input_field_placeholder="Оберіть опцію з меню"  # Підказка в полі вводу
    )


def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавіатура для адмін-панелі
    """
    keyboard = [
        [KeyboardButton(text="📋 Очікуючі пости")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔙 Головне меню")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію в адмін-панелі"
    )


# ================== ОЧИСТКА ТЕКСТУ ==================
def clean_text(text: str) -> str:
    lines = text.splitlines()
    result = []
    for line in lines:
        low = line.lower()
        if "підписатися" in low:
            continue
        if "|" in line and "@" not in line:
            continue
        result.append(line)
    return "\n".join(result).strip()


def contains_sambir(text: str) -> bool:
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in SAMBIR_KEYWORDS)


# ================== КНОПКИ ДЛЯ МОДЕРАЦІЇ (INLINE) ==================
def moderation_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опублікувати", callback_data=f"publish:{post_id}"),
                InlineKeyboardButton(text="❌ Відмінити", callback_data=f"cancel:{post_id}")
            ]
        ]
    )


# ================== ФУНКЦІЯ ДЛЯ ЗАВАНТАЖЕННЯ МЕДІА ==================
async def download_media(event, media_type: str):
    """
    Завантажує медіа з повідомлення
    Повертає шлях до файлу та його розширення
    """
    if not event.message.media:
        return None, None

    # Створюємо унікальне ім'я файлу
    file_ext = ""

    if media_type == "photo":
        file_ext = ".jpg"
    elif media_type == "video":
        # Отримуємо атрибути відео
        if hasattr(event.message, 'video') and event.message.video:
            # Спробуємо отримати розширення з mime_type
            mime_type = event.message.video.mime_type
            if mime_type:
                if 'mp4' in mime_type:
                    file_ext = ".mp4"
                elif 'avi' in mime_type:
                    file_ext = ".avi"
                elif 'mov' in mime_type:
                    file_ext = ".mov"
                else:
                    file_ext = ".mp4"  # За замовчуванням
            else:
                file_ext = ".mp4"
    elif media_type == "document":
        # Для документів (наприклад, відео як документ)
        if hasattr(event.message, 'document') and event.message.document:
            mime_type = event.message.document.mime_type
            if mime_type and 'video' in mime_type:
                # Отримуємо ім'я файлу з атрибутів
                file_name = event.message.document.attributes[
                    0].file_name if event.message.document.attributes else f"video_{event.message.id}"
                # Виділяємо розширення
                if '.' in file_name:
                    file_ext = '.' + file_name.split('.')[-1]
                else:
                    file_ext = ".mp4"

    file_name = f"{event.message.id}_{media_type}{file_ext}"
    file_path = os.path.join(tempfile.gettempdir(), file_name)

    try:
        await event.message.download_media(file_path)
        return file_path, file_ext
    except Exception as e:
        print(f"Помилка завантаження {media_type}: {e}")
        return None, None


# ================== ФУНКЦІЯ ДЛЯ ОПРИДІЛЕННЯ ТИПУ МЕДІА ==================
def get_media_type(event):
    """
    Визначає тип медіа у повідомленні
    """
    if event.message.photo:
        return "photo"
    elif event.message.video:
        return "video"
    elif event.message.document:
        # Перевіряємо чи це відео-документ
        if hasattr(event.message, 'document') and event.message.document:
            mime_type = event.message.document.mime_type
            if mime_type and 'video' in mime_type:
                return "video"
    return None


# ================== ФУНКЦІЯ ДЛЯ ВИДАЛЕННЯ КНОПОК ПІСЛЯ ДІЇ ==================
async def remove_buttons_after_action(bot: Bot, chat_id: int, message_id: int):
    """
    Видаляє inline кнопки з повідомлення після виконання дії
    """
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
    except Exception as e:
        # Якщо не вдалося оновити повідомлення (можливо, воно вже було видалене)
        print(f"Не вдалося видалити кнопки: {e}")


# ================== МОНІТОРИНГ (оригінальна функція для телеграм каналів) ==================
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def new_message_handler(event):
    # Отримуємо текст з повідомлення
    text = event.message.message or ""

    # Перевіряємо чи є медіа
    media_type = get_media_type(event)
    has_media = media_type is not None

    # Якщо немає тексту і немає медіа - пропускаємо
    if not text and not has_media:
        return

    text_lower = text.lower() if text else ""
    is_power = any(k in text_lower for k in POWER_KEYWORDS)
    is_alert_start = any(k in text_lower for k in ALERT_START_KEYWORDS)
    is_alert_end = any(k in text_lower for k in ALERT_END_KEYWORDS)
    is_sambir = contains_sambir(text)

    # ВИДАЛЕНО: автоматичну обробку тривог з телеграм каналів
    # Тепер тривоги обробляються тільки через API alerts.in.ua
    if not (is_power or is_sambir):  # Видалено is_alert_start та is_alert_end
        return

    db = load_db()
    msg_uid = f"{event.chat_id}_{event.message.id}"
    if msg_uid in db:
        return
    db.append(msg_uid)
    save_db(db)

    cleaned = clean_text(text) if text else ""
    # Для цільового каналу залишаємо Markdown, але екрануємо
    escaped_for_channel = cleaned.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
    footer = f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    # ВИДАЛЕНО: обробку тривог з телеграм каналів
    # Тривоги тепер обробляються тільки через API alerts.in.ua

    if is_power or is_sambir:
        media_file = None
        media_type_str = None

        if has_media:
            media_file, _ = await download_media(event, media_type)

        pending_posts[event.message.id] = {
            "text": cleaned + footer,
            "media": media_file,
            "media_type": media_type
        }

        preview_type = "💡 Світло / графіки" if is_power else "📰 Новина з Самбірщини"
        preview = f"{preview_type}\n\n{cleaned}" if cleaned else preview_type

        if media_file:
            if media_type == "photo":
                sent_message = await bot.send_photo(ADMIN_ID, FSInputFile(media_file), caption=preview,
                                                    reply_markup=moderation_keyboard(event.message.id))
                # Зберігаємо ID повідомлення
                if sent_message:
                    pending_posts[event.message.id]["admin_message_id"] = sent_message.message_id
            elif media_type == "video":
                sent_message = await bot.send_video(ADMIN_ID, FSInputFile(media_file), caption=preview,
                                                    reply_markup=moderation_keyboard(event.message.id))
                # Зберігаємо ID повідомлення
                if sent_message:
                    pending_posts[event.message.id]["admin_message_id"] = sent_message.message_id
        else:
            sent_message = await bot.send_message(ADMIN_ID, preview, reply_markup=moderation_keyboard(event.message.id))
            # Зберігаємо ID повідомлення
            if sent_message:
                pending_posts[event.message.id]["admin_message_id"] = sent_message.message_id


# ================== CALLBACK ДЛЯ INLINE КНОПОК ==================
@dp.callback_query(F.data)
async def handle_callbacks(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id

    # ===== ПУБЛІКАЦІЯ =====
    if call.data.startswith("publish"):
        pid = int(call.data.split(":")[1])
        item = pending_posts.pop(pid, None)
        if not item:
            # Видаляємо кнопки з повідомлення
            await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        try:
            if item["media"]:
                # Екрануємо текст для каналу
                escaped_text = item["text"].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')

                if item["media_type"] == "photo":
                    await bot.send_photo(TARGET_CHANNEL, FSInputFile(item["media"]), caption=escaped_text)
                elif item["media_type"] == "video":
                    await bot.send_video(TARGET_CHANNEL, FSInputFile(item["media"]), caption=escaped_text)

                # Видаляємо тимчасовий файл
                if os.path.exists(item["media"]):
                    os.remove(item["media"])
            else:
                escaped_text = item["text"].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                await bot.send_message(TARGET_CHANNEL, escaped_text)

            # Видаляємо кнопки з повідомлення
            await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
            await call.answer("✅ Опубліковано", show_alert=True)

        except Exception as e:
            await call.answer(f"❌ Помилка при публікації: {str(e)}", show_alert=True)

        return

    # ===== ВІДМІНА =====
    if call.data.startswith("cancel"):
        pid = int(call.data.split(":")[1])
        item = pending_posts.pop(pid, None)
        if item and item["media"]:
            if os.path.exists(item["media"]):
                os.remove(item["media"])

        # Видаляємо кнопки з повідомлення
        await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
        await call.answer("❌ Відмінено", show_alert=True)
        return


# ================== ОБРОБКА ПОВІДОМЛЕНЬ З ПАНЕЛІ МЕНЮ ==================
@dp.message(F.text == "📤 Поділитися інформацією")
async def handle_share_info(message: Message, state: FSMContext):
    await message.answer(
        "📤 <b>Поділитися інформацією</b>\n\n"
        "Надішліть вашу інформацію (текст, фото, відео з описом), я передам адміну для перевірки та публікації.\n\n"
        "⚠️ <b>Обмеження для відео:</b> максимум 100 МБ\n\n"
        "Щоб відмінити, напишіть /menu",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(ShareStates.waiting_info)


@dp.message(F.text == "📢 Розмістити рекламу")
async def handle_advertise(message: Message, state: FSMContext):
    await message.answer(
        "📢 <b>Розмістити рекламу</b>\n\n"
        "Опишіть коротко, що ви хочете прорекламувати в нашому каналі.\n\n"
        "Обв'язково, залиште ваші контактні дані (наприклад Telegram), щоб ми могли з вами зв'язатися.\n\n"
        "⚠️ <b>Можна додати фото або відео</b> (макс. 100 МБ для відео)\n\n"
        "Щоб відмінити, напишіть /menu",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(ShareStates.waiting_ad)


@dp.message(F.text == "👑 Адмін-панель")
async def handle_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return

    await message.answer(
        "👑 <b>Адмін-панель</b>\n\n"
        "Оберіть дію з меню нижче:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )


@dp.message(F.text == "📋 Очікуючі пости")
async def handle_pending_posts(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    if not pending_posts:
        await message.answer("📭 Немає постів, які очікують на модерацію.")
    else:
        count = len(pending_posts)
        media_stats = {"photo": 0, "video": 0, "text_only": 0}
        for post in pending_posts.values():
            if post.get("media_type") == "photo":
                media_stats["photo"] += 1
            elif post.get("media_type") == "video":
                media_stats["video"] += 1
            else:
                media_stats["text_only"] += 1

        stats_text = f"📋 <b>Постів в очікуванні:</b> {count}\n"
        stats_text += f"📷 Фото: {media_stats['photo']}\n"
        stats_text += f"🎬 Відео: {media_stats['video']}\n"
        stats_text += f"📝 Текст: {media_stats['text_only']}\n\n"
        stats_text += f"<b>ID постів:</b> {', '.join(map(str, pending_posts.keys()))}"

        await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "📊 Статистика")
async def handle_admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    # Проста статистика
    alert_state = load_alert_state()
    stats_text = "📊 <b>Статистика:</b>\n\n"
    stats_text += f"📝 <b>Постів в очікуванні:</b> {len(pending_posts)}\n"

    # Статистика по типам медіа
    media_stats = {"photo": 0, "video": 0, "text_only": 0}
    for post in pending_posts.values():
        if post.get("media_type") == "photo":
            media_stats["photo"] += 1
        elif post.get("media_type") == "video":
            media_stats["video"] += 1
        else:
            media_stats["text_only"] += 1

    stats_text += f"  📷 Фото: {media_stats['photo']}\n"
    stats_text += f"  🎬 Відео: {media_stats['video']}\n"
    stats_text += f"  📝 Текст: {media_stats['text_only']}\n\n"

    stats_text += f"🚨 <b>Тривога активна (API):</b> {'Так' if alert_state['active'] else 'Ні'}\n"
    if alert_state['active'] and alert_state['start_time']:
        start = datetime.fromisoformat(alert_state["start_time"])
        seconds = int((datetime.now() - start).total_seconds())
        duration = format_duration(seconds)
        stats_text += f"⏱ <b>Тривалість тривоги:</b> {duration}\n"

    # Додаємо інформацію про метод отримання тривог
    stats_text += f"\n🔍 <b>Джерело тривог:</b> API alerts.in.ua"

    await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "🔙 Головне меню")
async def handle_back_to_menu(message: Message):
    await show_main_menu(message)


# ================== ОТРИМАННЯ ПОВІДОМЛЕНЬ ВІД КОРИСТУВАЧА В СТАНАХ ==================
@dp.message(ShareStates.waiting_info)
async def receive_info(message: Message, state: FSMContext):
    # Перевіряємо, чи це команда скасування
    if message.text and message.text == "/menu":
        await message.answer("📤 Поділення інформації скасовано.")
        await show_main_menu(message)
        await state.clear()
        return

    # Отримуємо текст або з повідомлення, або з підпису до медіа
    text = message.text or message.caption or ""
    media_file = None
    media_type = None

    # Обробляємо фото
    if message.photo:
        media_type = "photo"
        # Створюємо тимчасовий файл з унікальним ім'ям
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        # Завантажуємо фото
        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )

    # Обробляємо відео
    elif message.video:
        # Перевіряємо розмір відео
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        # Створюємо тимчасовий файл
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        # Завантажуємо відео
        await message.bot.download(
            message.video,
            destination=media_file
        )

    # Обробляємо документ (наприклад, відео як документ)
    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
        # Перевіряємо розмір
        if message.document.file_size and message.document.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.document.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        # Визначаємо розширення файлу
        file_name = message.document.file_name or "video.mp4"
        if '.' in file_name:
            ext = '.' + file_name.split('.')[-1]
        else:
            ext = '.mp4'

        # Створюємо тимчасовий файл
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        media_file = temp_file.name

        # Завантажуємо відео
        await message.bot.download(
            message.document,
            destination=media_file
        )

    post_id = message.message_id
    pending_posts[post_id] = {"text": text, "media": media_file, "media_type": media_type}

    # Готуємо текст для адміна з HTML екрануванням
    username = message.from_user.username or message.from_user.full_name
    user_info = f"👤 Від: @{username} (ID: {message.from_user.id})"

    # Екрануємо текст HTML
    escaped_text = escape_html(text) if text else '📁 Медіа без тексту'
    caption_text = f"{user_info}\n\n📤 Інформація:\n{escaped_text}"

    # Додаємо тип медіа до опису
    if media_type:
        caption_text += f"\n\n📁 Тип: {media_type.upper()}"

    if media_file:
        # Перевіряємо чи файл існує та не порожній
        if os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=caption_text,
                    reply_markup=moderation_keyboard(post_id)
                )
            elif media_type == "video":
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=caption_text,
                    reply_markup=moderation_keyboard(post_id)
                )

            # Зберігаємо ID повідомлення для можливості видалення кнопок пізніше
            if sent_message:
                pending_posts[post_id]["admin_message_id"] = sent_message.message_id
        else:
            # Якщо файл не завантажився, відправляємо тільки текст
            sent_message = await bot.send_message(
                ADMIN_ID,
                f"{caption_text}\n\n⚠️ Медіа не вдалося завантажити",
                reply_markup=moderation_keyboard(post_id)
            )
            if sent_message:
                pending_posts[post_id]["admin_message_id"] = sent_message.message_id
    else:
        # Якщо тільки текст
        sent_message = await bot.send_message(
            ADMIN_ID,
            caption_text,
            reply_markup=moderation_keyboard(post_id)
        )
        if sent_message:
            pending_posts[post_id]["admin_message_id"] = sent_message.message_id

    await message.answer(
        "✅ Ваша інформація надіслана адміну для перевірки. Дякуємо!\n\n"
        "Меню знову доступне:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )
    await state.clear()


@dp.message(ShareStates.waiting_ad)
async def receive_ad(message: Message, state: FSMContext):
    # Перевіряємо, чи це команда скасування
    if message.text and message.text == "/menu":
        await message.answer("📢 Розміщення реклами скасовано.")
        await show_main_menu(message)
        await state.clear()
        return

    # Отримуємо текст або з повідомлення, або з підпису до медіа
    text = message.text or message.caption or ""
    media_file = None
    media_type = None

    # Обробляємо фото
    if message.photo:
        media_type = "photo"
        # Створюємо тимчасовий файл з унікальним ім'ям
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        # Завантажуємо фото
        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )

    # Обробляємо відео
    elif message.video:
        # Перевіряємо розмір відео
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        # Створюємо тимчасовий файл
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        # Завантажуємо відео
        await message.bot.download(
            message.video,
            destination=media_file
        )

    # Готуємо інформацію про користувача
    username = message.from_user.username or message.from_user.full_name
    user_info = f"👤 Від: @{username} (ID: {message.from_user.id})"

    # Екрануємо текст HTML
    escaped_text = escape_html(text) if text else "📁 Медіа без тексту"

    # Формуємо повідомлення для адміна
    admin_message = f"📢 Реклама:\n{user_info}\n\n{escaped_text}"

    # Додаємо інформацію про тип медіа
    if media_type:
        admin_message += f"\n\n📁 Тип медіа: {media_type.upper()}"

    # Надсилаємо адміну
    if media_file:
        # Перевіряємо чи файл існує та не порожній
        if os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=admin_message
                )
            elif media_type == "video":
                await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=admin_message
                )
            # Видаляємо тимчасовий файл після надсилання
            os.remove(media_file)
        else:
            # Якщо файл не завантажився, відправляємо тільки текст
            await bot.send_message(
                ADMIN_ID,
                f"{admin_message}\n\n⚠️ Медіа не вдалося завантажити"
            )
    else:
        # Якщо тільки текст
        await bot.send_message(
            ADMIN_ID,
            admin_message
        )

    # Відповідь рекламодавцю
    await message.answer(
        "✅ Ваша заявка на рекламу прийнята!\n\n"
        "Адмін розгляне ваше повідомлення і зв'яжеться з вами в найближчий час.\n\n"
        "Будь ласка, не видаляйте і не блокуйте бота поки з вами не зв'яжиться адмін.\n\n"
        "Дякуємо, що обрали наш канал!\n\n"
        "Меню знову доступне:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )

    await state.clear()


# ================== ФУНКЦІЯ ДЛЯ ПОКАЗУ ГОЛОВНОГО МЕНЮ ==================
async def show_main_menu(message: Message):
    if message.from_user.id == ADMIN_ID:
        # ВЕРСІЯ ДЛЯ АДМІНА
        welcome_text = (
            "🏠 <b>Головне меню</b>\n\n"
            "Оберіть одну з опцій:\n\n"
            "• 📤 <b>Поділитися інформацією</b> - надіслати новину чи інформацію для публікації\n"
            "• 📢 <b>Розмістити рекламу</b> - залишити заявку на розміщення реклами\n"
            "• 👑 <b>Адмін-панель</b> - доступна тільки для адміністратора\n\n"
            "⚠️ <b>Підтримка медіа:</b> текст, фото, відео (до 100 МБ)\n"
            "🚨 <b>Тривоги:</b> отримуються з alerts.in.ua"
        )
    else:
        # ВЕРСІЯ ДЛЯ ЗВИЧАЙНИХ КОРИСТУВАЧІВ
        welcome_text = (
            "🏠 <b>Головне меню</b>\n\n"
            "Оберіть одну з опцій:\n\n"
            "• 📤 <b>Поділитися інформацією</b> - надіслати новину чи інформацію для публікації\n"
            "• 📢 <b>Розмістити рекламу</b> - залишити заявку на розміщення реклами\n\n"
            "⚠️ <b>Підтримка медіа:</b> текст, фото, відео (до 100 МБ)\n"
            "🚨 <b>Тривоги:</b> отримуються з alerts.in.ua"
        )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(message.from_user.id),
        parse_mode=ParseMode.HTML
    )


# ================== КОМАНДИ ==================
@dp.message(F.text == "/start")
async def start_handler(message: Message):
    await show_main_menu(message)


@dp.message(F.text == "/menu")
async def menu_handler(message: Message):
    # Перевіряємо, чи меню вже показане
    await show_main_menu(message)


# ================== ОБРОБКА ІНШИХ ПОВІДОМЛЕНЬ ==================
@dp.message()
async def handle_other_messages(message: Message):
    # Перевіряємо, чи користувач в стані FSM
    current_state = await dp.fsm.get_context(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id)
    if not current_state.state:
        # Якщо це команда, яку ми не обробили
        if message.text and message.text.startswith("/"):
            await message.answer("ℹ️ Невідома команда. Використовуйте /menu для відкриття меню.")
        else:
            # Показуємо меню для будь-якого іншого повідомлення
            await show_main_menu(message)


# ================== ЗАПУСК ==================
async def main():
    print("🧪 Бот запущений. Моніторинг Самбірських новин + меню користувача")
    print("📱 Бот готовий до роботи")
    print(f"👑 Адмін ID: {ADMIN_ID}")
    print(f"🎯 Цільовий канал: {TARGET_CHANNEL}")
    print("📋 Меню доступне як панель під полем вводу тексту")
    print("🎥 Підтримка відео: активована (макс. 100 МБ)")
    print("🚨 Моніторинг тривог: через API alerts.in.ua")

    # Запускаємо фоновий моніторинг тривог
    asyncio.create_task(alerts_monitoring_task())

    await client.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
