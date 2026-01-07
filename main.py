import asyncio
import os
import tempfile
import json
import html
import aiohttp
import requests
from datetime import datetime, timedelta
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
from aiogram.filters import Command
from typing import Optional, Dict, Any

# ================== НАЛАШТУВАННЯ ==================
API_ID = 30210758
API_HASH = "1e9b089b6a38dc9cd5e8978d03f5dd33"
SESSION_NAME = "SambrNewsBot"

BOT_TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"
ADMIN_ID = 6974875043

# API alerts.in.ua
ALERTS_API_TOKEN = "f7f5a126f8865ad43bbd19d522d6c489b11486c9ab2203"
ALERTS_API_BASE_URL = "https://alerts.com.ua/api"

# API для погоди
WEATHER_API_KEY = "ваш_ключ_погоди"  # Замінити на реальний ключ
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_API_URL = "https://api.openweathermap.org/data/2.5/forecast"

# API для курсу валют
CURRENCY_API_URL = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=5"

# DeepSeek API для генерації тексту
DEEPSEEK_API_KEY = "sk-017a205af4b64ef6a1f23171e2c8ddf6"  # Замінити на реальний ключ
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Координати Самбора (приблизні)
SAMBIR_LAT = 49.5167
SAMBIR_LON = 23.2030

# ID області для Львівської області
LVIV_REGION_ID = 25

# Додаємо нові стани для прогнозу
WEATHER_REPORT_TIME = "08:00"  # Час публікації прогнозу
MODERATION_TIME = "22:00"  # Час надсилання на модерацію

# ВИДАЛЕНО тестовий канал з джерел, додано львівські канали
SOURCE_CHANNELS = [
    "dsns_lviv",
    "lviv_region_poluce",
    "lvivpatrolpolice",
    "lvivoblprok",
    "lvivych_news"
]

TARGET_CHANNEL = "@Test_Chenal_0"
TARGET_CHANNEL_USERNAME = "Test_Chenal_0"
TARGET_CHANNEL_TITLE = "🧪 Test Channel"

# Розширені ключові слова для відключень світла та графіків
POWER_KEYWORDS = [
    "відключення", "відключення світла", "відключення електроенергії",
    "аварійне відключення", "планові відключення",
    "графік", "графіка", "графіку", "графіки",
    "графік відключень", "графіки відключень",
    "розклад відключень", "початок відключень",
    "енергетика", "енергопостачання", "енергозабезпечення",
    "електроенергії", "електроенергія", "електропостачання",
    "світло", "світла", "світлу",
    "аварія", "ремонт", "відновлення",
    "обленерго", "енерго", "постачання",
    "подача", "енергокомпанія", "електромережі",
    "ЛЬВІВОБЛЕНЕРГО", "ЛЬВІВЕНЕРГО", "ДТЕК",
    "енергоремонт", "аварійні роботи", "планові роботи"
]

# Словник для визначення джерел новин
SOURCE_NAMES = {
    "dsns_lviv": "ДСНС Львівщини",
    "lviv_region_poluce": "Поліція Львівської області",
    "lvivpatrolpolice": "Патрульна поліція Львова",
    "lvivoblprok": "Львівська обласна прокуратура",
    "lvivych_news": "Львич News"
}

SAMBIR_KEYWORDS = [
    "самбір", "Самборі", "самбірського", "самбірський", "самбірському",
    "самбірська", "самбірські", "самбірських", "самбіряни", "самбірщина",
    "самбірський район", "самбірщини", "самбірську", "самбірським",
    "Львів", "Львова", "Львові", "Львівський"
]

# Файли для зберігання даних
DB_FILE = "database.json"
ALERT_STATE_FILE = "alert_state.json"
LAST_ALERT_CHECK_FILE = "last_alert_check.json"
WEATHER_DATA_FILE = "weather_data.json"  # Для зберігання прогнозів

# Максимальний розмір відео для завантаження
MAX_VIDEO_SIZE = 100 * 1024 * 1024


# ================== FSM ==================
class ShareStates(StatesGroup):
    waiting_info = State()
    waiting_ad = State()


class EditStates(StatesGroup):
    waiting_edit_text = State()
    waiting_edit_media = State()


class WeatherStates(StatesGroup):
    waiting_weather_edit = State()


# ================== ФУНКЦІЇ ДЛЯ ЗБЕРІГАННЯ ПРОГНОЗУ ==================
def load_weather_data():
    """Завантажує дані про прогноз з файлу"""
    if not os.path.exists(WEATHER_DATA_FILE):
        return {
            "pending_forecast": None,
            "published_forecasts": [],
            "last_check": None
        }
    try:
        with open(WEATHER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "pending_forecast": None,
            "published_forecasts": [],
            "last_check": None
        }


def save_weather_data(data):
    """Зберігає дані про прогноз у файл"""
    with open(WEATHER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    if not text:
        return ""
    return html.escape(text)


# ================== API ДЛЯ ПОГОДИ ==================
async def get_weather_forecast():
    """
    Отримує прогноз погоди для Самбора
    Повертає словник з даними або None при помилці
    """
    try:
        # Спроба отримати поточну погоду
        params = {
            'lat': SAMBIR_LAT,
            'lon': SAMBIR_LON,
            'appid': WEATHER_API_KEY,
            'units': 'metric',
            'lang': 'ua'
        }

        # Якщо API ключ не заданий, повертаємо тестові дані
        if WEATHER_API_KEY == "ваш_ключ_погоди":
            return {
                'current': {
                    'temp': -5,
                    'description': 'легкий сніг',
                    'humidity': 85,
                    'pressure': 1013,
                    'wind_speed': 3.5,
                    'wind_direction': 'північно-західний',
                    'clouds': 90,
                    'feels_like': -8
                },
                'forecast': [
                    {'temp': -5, 'description': 'легкий сніг', 'time': 'ранок'},
                    {'temp': -4, 'description': 'сніг', 'time': 'день'},
                    {'temp': -7, 'description': 'хмарно', 'time': 'вечір'}
                ],
                'sunrise': '07:54',
                'sunset': '16:13',
                'day_length': '8:18'
            }

        # Спроба отримати дані з API
        async with aiohttp.ClientSession() as session:
            # Поточна погода
            async with session.get(WEATHER_API_URL, params=params) as response:
                if response.status != 200:
                    print(f"Помилка API погоди: {response.status}")
                    return None
                weather_data = await response.json()

            # Прогноз
            async with session.get(FORECAST_API_URL, params=params) as response:
                if response.status != 200:
                    print(f"Помилка API прогнозу: {response.status}")
                    return None
                forecast_data = await response.json()

            # Обробка поточної погоди
            current_temp = weather_data['main']['temp']
            feels_like = weather_data['main']['feels_like']
            weather_desc = weather_data['weather'][0]['description']
            humidity = weather_data['main']['humidity']
            pressure = weather_data['main']['pressure']
            wind_speed = weather_data['wind']['speed']
            wind_deg = weather_data['wind'].get('deg', 0)
            clouds = weather_data['clouds']['all']

            # Конвертація градусів вітру в напрямок
            wind_directions = ['північний', 'північно-східний', 'східний', 'південно-східний',
                               'південний', 'південно-західний', 'західний', 'північно-західний']
            wind_dir_index = round(wind_deg / 45) % 8
            wind_direction = wind_directions[wind_dir_index]

            # Розрахунок сходу/заходу сонця
            sunrise = datetime.fromtimestamp(weather_data['sys']['sunrise']).strftime('%H:%M')
            sunset = datetime.fromtimestamp(weather_data['sys']['sunset']).strftime('%H:%M')

            # Розрахунок тривалості дня
            sunrise_dt = datetime.fromtimestamp(weather_data['sys']['sunrise'])
            sunset_dt = datetime.fromtimestamp(weather_data['sys']['sunset'])
            day_length = sunset_dt - sunrise_dt
            hours = day_length.seconds // 3600
            minutes = (day_length.seconds % 3600) // 60
            day_length_str = f"{hours}:{minutes:02d}"

            # Обробка прогнозу
            forecast_list = []
            time_periods = ['ранок', 'день', 'вечір', 'ніч']

            for i, item in enumerate(forecast_data['list'][:4]):  # Перші 4 періоди
                forecast_list.append({
                    'temp': item['main']['temp'],
                    'description': item['weather'][0]['description'],
                    'time': time_periods[i] if i < len(time_periods) else 'день'
                })

            return {
                'current': {
                    'temp': round(current_temp),
                    'feels_like': round(feels_like),
                    'description': weather_desc.capitalize(),
                    'humidity': humidity,
                    'pressure': pressure,
                    'wind_speed': wind_speed,
                    'wind_direction': wind_direction,
                    'clouds': clouds
                },
                'forecast': forecast_list,
                'sunrise': sunrise,
                'sunset': sunset,
                'day_length': day_length_str
            }

    except Exception as e:
        print(f"Помилка при отриманні погоди: {e}")
        return None


async def get_currency_rates():
    """
    Отримує курс валют
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CURRENCY_API_URL) as response:
                if response.status != 200:
                    print(f"Помилка API валют: {response.status}")
                    return None

                data = await response.json()
                rates = {}

                for currency in data:
                    if currency['ccy'] == 'USD':
                        rates['USD'] = {
                            'buy': float(currency['buy']),
                            'sale': float(currency['sale'])
                        }
                    elif currency['ccy'] == 'EUR':
                        rates['EUR'] = {
                            'buy': float(currency['buy']),
                            'sale': float(currency['sale'])
                        }
                    elif currency['ccy'] == 'PLN':
                        rates['PLN'] = {
                            'buy': float(currency['buy']),
                            'sale': float(currency['sale'])
                        }

                return rates
    except Exception as e:
        print(f"Помилка при отриманні курсів валют: {e}")
        return None


# ================== DEEPSEEK API ДЛЯ ГЕНЕРАЦІЇ ТЕКСТУ ==================
async def generate_weather_description(weather_data: dict) -> str:
    """
    Генерує креативний опис погоди через DeepSeek API
    """
    try:
        # Якщо API ключ не заданий, повертаємо стандартний опис
        if DEEPSEEK_API_KEY == "ваш_deepseek_ключ":
            return await generate_default_description(weather_data)

        # Готуємо промпт для AI
        current = weather_data['current']
        forecast_items = weather_data['forecast']

        prompt = f"""Створи креативний, короткий опис погоди для міста Самбір на основі таких даних:

Поточна погода:
- Температура: {current['temp']}°C
- Відчувається як: {current['feels_like']}°C
- Опис: {current['description']}
- Вологість: {current['humidity']}%
- Хмарність: {current['clouds']}%
- Вітер: {current['wind_speed']} м/с, {current['wind_direction']}

Прогноз на день:
{chr(10).join([f"- {item['time']}: {item['description']}, {item['temp']}°C" for item in forecast_items])}

Вимоги до тексту:
1. Почни з "Доброго ранку Самбірчани!"
2. Опиши погоду цікаво, природно, без повторів
3. Використовуй українську мову
4. Максимум 3-4 речення
5. Не використовуй маркери списків
6. Закінчи фразою про середню температуру

Приклад хорошого опису:
"Доброго ранку Самбірчани! У Самборі протягом усього дня небо буде затягнуте хмарами. Сильний сніг, що розпочнеться вранці, поступово слабшатиме впродовж дня. Температура — до -5°."

Тепер створи опис на основі наданих даних:"""

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system",
                 "content": "Ти креативний метеоролог, який пише цікаві описи погоди українською мовою."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.7
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload) as response:
                if response.status != 200:
                    print(f"Помилка DeepSeek API: {response.status}")
                    return await generate_default_description(weather_data)

                result = await response.json()
                description = result['choices'][0]['message']['content'].strip()

                # Очищаємо текст від можливих артефактів
                description = description.replace('```', '').replace('**', '').strip()

                return description

    except Exception as e:
        print(f"Помилка при генерації опису через DeepSeek: {e}")
        return await generate_default_description(weather_data)


async def generate_default_description(weather_data: dict) -> str:
    """
    Генерує стандартний опис погоди, якщо API недоступне
    """
    current = weather_data['current']
    forecast = weather_data['forecast']

    descriptions = []

    # Основний опис
    if current['clouds'] > 70:
        descriptions.append(f"У Самборі протягом усього дня небо буде затягнуте хмарами.")
    elif current['clouds'] > 30:
        descriptions.append(f"У Самборі переважно хмарно.")
    else:
        descriptions.append(f"У Самборі сьогодні переважно ясно.")

    # Опис опадів/явищ
    weather_lower = current['description'].lower()
    if 'сніг' in weather_lower:
        if 'легкий' in weather_lower:
            descriptions.append(f"Легкий сніг триватиме протягом дня.")
        elif 'сильний' in weather_lower or 'інтенсивний' in weather_lower:
            descriptions.append(f"Сильний сніг поступово слабшатиме впродовж дня.")
        else:
            descriptions.append(f"Сніг періодично посилюватиметься.")
    elif 'дощ' in weather_lower:
        if 'легкий' in weather_lower:
            descriptions.append(f"Легкий дощ час від часу накрапатиме.")
        elif 'сильний' in weather_lower:
            descriptions.append(f"Сильний дощ триватиме з перервами.")
        else:
            descriptions.append(f"Дощові хмари періодично накриватимуть місто.")
    elif 'туман' in weather_lower:
        descriptions.append(f"Туман розсіється до середини дня.")

    # Температурний опис
    if current['temp'] < -10:
        descriptions.append(f"Мороз посилюватиметься, температура опуститься до {current['temp']}°.")
    elif current['temp'] < 0:
        descriptions.append(f"Температура триматиметься на рівні {current['temp']}°.")
    else:
        descriptions.append(f"Температура сягатиме {current['temp']}°.")

    return f"Доброго ранку Самбірчани!\n\n" + " ".join(descriptions)


# ================== ГЕНЕРАЦІЯ ПОВНОГО ПОВІДОМЛЕННЯ ПРО ПОГОДУ ==================
async def generate_weather_message(weather_data: dict, currency_data: dict = None) -> str:
    """
    Генерує повний текст ранкового прогнозу з AI-описом
    """
    try:
        # Генеруємо креативний опис через DeepSeek
        weather_description = await generate_weather_description(weather_data)

        # Додаємо технічні деталі
        current = weather_data['current']

        message = f"{weather_description}\n\n"

        # Температура
        message += f"☀️Температура в день: {current['temp']}°\n"
        # Припустимо, що нічна температура на 3-4 градуси нижча
        night_temp = current['temp'] - 3
        message += f"🌕Температура в ночі: {night_temp}°\n\n"

        # Сонце
        message += f"🌅Схід сонця {weather_data['sunrise']}\n"
        message += f"☀️Сонце в зеніті 12:04\n"
        message += f"🌥Захід сонця {weather_data['sunset']}\n"
        message += f"⏱ Тривалість дня {weather_data['day_length']}\n\n"

    except Exception as e:
        print(f"Помилка при генерації повного повідомлення: {e}")
        # Резервний варіант
        message = "Доброго ранку Самбірчани!\n\n"
        if weather_data:
            current = weather_data['current']
            message += f"У Самборі сьогодні {current['description'].lower()}, середня температура {current['temp']}°.\n\n"
            message += f"☀️Температура в день: {current['temp']}°\n"
            night_temp = current['temp'] - 3
            message += f"🌕Температура в ночі: {night_temp}°\n\n"
            message += f"🌅Схід сонця {weather_data['sunrise']}\n"
            message += f"☀️Сонце в зеніті 12:04\n"
            message += f"🌥Захід сонця {weather_data['sunset']}\n"
            message += f"⏱ Тривалість дня {weather_data['day_length']}\n\n"
        else:
            message += "У Самборі сьогодні весь день хмарно, ближче до середини дня можливий дощ, середня температура 5°.\n\n"
            message += "☀️Температура в день: 5°\n"
            message += "🌕Температура в ночі: 1°\n\n"
            message += "🌅Схід сонця 07:54\n"
            message += "☀️Сонце в зеніті 12:04\n"
            message += "🌥Захід сонця 16:13\n"
            message += "⏱ Тривалість дня 8:18\n\n"

    # Курс валют
    message += "Курс валют:\n"
    if currency_data:
        if 'USD' in currency_data:
            message += f"🇺🇸: {currency_data['USD']['buy']:.2f}- {currency_data['USD']['sale']:.2f}\n"
        else:
            message += "🇺🇸: 42.50- 43.20\n"

        if 'EUR' in currency_data:
            message += f"🇪🇺: {currency_data['EUR']['buy']:.2f}- {currency_data['EUR']['sale']:.2f}\n"
        else:
            message += "🇪🇺: 49.80- 50.50\n"

        if 'PLN' in currency_data:
            message += f"🇵🇱: {currency_data['PLN']['buy']:.2f}- {currency_data['PLN']['sale']:.2f}\n"
        else:
            message += "🇵🇱: 11.75- 11.90\n"
    else:
        message += "🇺🇸: 42.50- 43.20\n"
        message += "🇪🇺: 49.80- 50.50\n"
        message += "🇵🇱: 11.75- 11.90\n"

    # Додаємо футер
    message += f"\n<b>{TARGET_CHANNEL_TITLE}</b>"

    return message


# ================== ФУНКЦІЯ ДЛЯ АВТОМАТИЧНОГО ПУБЛІКУВАННЯ ==================
async def publish_scheduled_weather():
    """
    Автоматично публікує прогноз погоди о 08:00
    """
    print(f"⏰ Запущено задачу автоматичного публікування прогнозу на {WEATHER_REPORT_TIME}")

    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            # Перевіряємо, чи настав час публікації
            if current_time == WEATHER_REPORT_TIME:
                print(f"🕗 {WEATHER_REPORT_TIME} - час публікації прогнозу")

                # Отримуємо дані про погоду
                weather_data = await get_weather_forecast()

                # Отримуємо курс валют за 10 хвилин до публікації
                print("💱 Отримуємо курс валют...")
                currency_data = await get_currency_rates()

                # Генеруємо повідомлення з AI-описом
                print("🤖 Генеруємо опис погоди через DeepSeek...")
                message_text = await generate_weather_message(weather_data, currency_data)

                # Публікуємо в канал
                try:
                    await bot.send_message(TARGET_CHANNEL, message_text)
                    print(f"✅ Прогноз успішно опубліковано в {TARGET_CHANNEL}")

                    # Зберігаємо інформацію про публікацію
                    weather_db = load_weather_data()
                    if not weather_db.get("published_forecasts"):
                        weather_db["published_forecasts"] = []

                    weather_db["published_forecasts"].append({
                        "date": now.strftime("%Y-%m-%d"),
                        "time": current_time,
                        "message": message_text,
                        "weather_data": weather_data
                    })

                    # Обмежуємо кількість збережених прогнозів
                    if len(weather_db["published_forecasts"]) > 30:
                        weather_db["published_forecasts"] = weather_db["published_forecasts"][-30:]

                    save_weather_data(weather_db)

                except Exception as e:
                    print(f"❌ Помилка при публікації прогнозу: {e}")

                # Чекаємо 60 секунд, щоб уникнути повторної публікації
                await asyncio.sleep(60)

            # Чекаємо 30 секунд перед наступною перевіркою
            await asyncio.sleep(30)

        except Exception as e:
            print(f"❌ Помилка в задачі публікації прогнозу: {e}")
            await asyncio.sleep(60)


# ================== ФУНКЦІЯ ДЛЯ МОДЕРАЦІЇ ПРОГНОЗУ ==================
async def send_weather_for_moderation():
    """
    Надсилає прогноз на модерацію адміну о 21:00
    """
    print(f"⏰ Запущено задачу модерації прогнозу на {MODERATION_TIME}")

    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            # Перевіряємо, чи настав час модерації
            if current_time == MODERATION_TIME:
                print(f"🕘 {MODERATION_TIME} - час модерації прогнозу")

                # Отримуємо дані про погоду
                weather_data = await get_weather_forecast()

                # Генеруємо повідомлення з AI-описом
                print("🤖 Генеруємо опис погоди для модерації...")
                message_text = await generate_weather_message(weather_data)

                # Створюємо унікальний ID для цього прогнозу
                forecast_id = int(datetime.now().timestamp())

                # Зберігаємо прогноз в очікуванні
                weather_db = load_weather_data()
                weather_db["pending_forecast"] = {
                    "id": forecast_id,
                    "date": now.strftime("%Y-%m-%d"),
                    "time": current_time,
                    "message": message_text,
                    "weather_data": weather_data
                }
                weather_db["last_check"] = now.isoformat()
                save_weather_data(weather_db)

                # Створюємо клавіатуру для модерації
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Опублікувати завтра в 08:00",
                                callback_data=f"weather_publish:{forecast_id}"
                            ),
                            InlineKeyboardButton(
                                text="✏️ Редагувати",
                                callback_data=f"weather_edit:{forecast_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="❌ Відмінити",
                                callback_data=f"weather_cancel:{forecast_id}"
                            )
                        ]
                    ]
                )

                # Надсилаємо адміну на модерацію
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"🌤 <b>Прогноз погоди на завтра ({now.day + 1}.{now.month}.{now.year})</b>\n\n"
                        f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
                        f"Попередній перегляд:\n\n{message_text}",
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                    print(f"📨 Прогноз надіслано на модерацію адміну {ADMIN_ID}")
                except Exception as e:
                    print(f"❌ Помилка при надсиланні прогнозу на модерацію: {e}")

                # Чекаємо 60 секунд, щоб уникнути повторного надсилання
                await asyncio.sleep(60)

            # Чекаємо 30 секунд перед наступною перевіркою
            await asyncio.sleep(30)

        except Exception as e:
            print(f"❌ Помилка в задачі модерації прогнозу: {e}")
            await asyncio.sleep(60)


# ================== API alerts.in.ua ==================
async def check_alerts_in_ua():
    headers = {
        "X-API-Key": ALERTS_API_TOKEN,
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ALERTS_API_BASE_URL}/states", headers=headers) as response:
                if response.status != 200:
                    print(f"Помилка API: {response.status}")
                    return None

                data = await response.json()
                lviv_region = None

                for region in data.get("states", []):
                    if region.get("id") == LVIV_REGION_ID:
                        lviv_region = region
                        break

                if not lviv_region:
                    print("Не знайдено Львівську область в даних API")
                    return None

                alert_active = lviv_region.get("alert", False)
                alert_state = load_alert_state()
                last_check_data = load_last_alert_check()
                changed = False

                if alert_active != alert_state["active"]:
                    changed = True

                    if alert_active:
                        alert_state["active"] = True
                        alert_state["start_time"] = datetime.now().isoformat()
                        print(f"🚨 Тривога почалася у Львівській області")
                    else:
                        alert_state["active"] = False
                        alert_state["start_time"] = None
                        print(f"✅ Відбій тривоги у Львівській області")

                    save_alert_state(alert_state)

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
    footer = f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    if is_start:
        message_text = f"🚨УВАГА, повітряна тривога у Львівській області!{footer}"
        await bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про початок тривоги")
    else:
        if duration_seconds:
            duration = format_duration(duration_seconds)
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!\n\n⏱ <b>Тривалість:</b> {duration}{footer}"
        else:
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!{footer}"

        await bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про відбій тривоги")


# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ТРИВОГ ==================
async def alerts_monitoring_task():
    print("🔍 Запущено моніторинг тривог через API alerts.in.ua")

    while True:
        try:
            await asyncio.sleep(10)
            alert_status = await check_alerts_in_ua()

            if alert_status and alert_status["changed"]:
                if alert_status["active"]:
                    await send_alert_to_channel(is_start=True)
                else:
                    if alert_status["state"]["start_time"]:
                        start = datetime.fromisoformat(alert_status["state"]["start_time"])
                        seconds = int((datetime.now() - start).total_seconds())
                        await send_alert_to_channel(is_start=False, duration_seconds=seconds)
                    else:
                        await send_alert_to_channel(is_start=False)

        except Exception as e:
            print(f"Помилка в задачі моніторингу тривог: {e}")
            await asyncio.sleep(30)


# ================== TELETHON ==================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
pending_posts = {}

# ================== AIROGRAM ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ================== ПАНЕЛЬ МЕНЮ ==================
def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📤 Поділитися інформацією")],
        [KeyboardButton(text="📢 Розмістити рекламу")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="👑 Адмін-панель")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть опцію з меню"
    )


def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📋 Очікуючі пости")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🌤 Прогноз погоди")],
        [KeyboardButton(text="🔙 Головне меню")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію в адмін-панелі"
    )


# ================== КЛАВІАТУРИ ДЛЯ ПРОГНОЗУ ==================
def weather_moderation_keyboard(forecast_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опублікувати завтра", callback_data=f"weather_publish:{forecast_id}"),
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"weather_edit:{forecast_id}")
            ],
            [
                InlineKeyboardButton(text="❌ Відмінити", callback_data=f"weather_cancel:{forecast_id}")
            ]
        ]
    )


def weather_edit_options_keyboard(forecast_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Текст", callback_data=f"weather_edit_text:{forecast_id}"),
                InlineKeyboardButton(text="🔄 Оновити дані", callback_data=f"weather_refresh:{forecast_id}"),
                InlineKeyboardButton(text="🤖 Згенерувати новий", callback_data=f"weather_regenerate:{forecast_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"weather_back:{forecast_id}")
            ]
        ]
    )


# ================== ФУНКЦІЇ ДЛЯ ОЧИСТКИ ТЕКСТУ ==================
def clean_text(text: str) -> str:
    """
    Очищає текст від зайвих посилань та рекламних слів
    """
    if not text:
        return ""

    lines = text.splitlines()
    result = []

    for line in lines:
        low = line.lower()
        # Видаляємо рекламні рядки
        if "підписатися" in low:
            continue
        if "перейти" in low and "канал" in low:
            continue
        if "наш канал" in low:
            continue
        if "наш сайт" in low:
            continue
        if "|" in line and "@" not in line:
            continue
        # Видаляємо посилання на соцмережі
        if any(x in low for x in ["facebook", "instagram", "twitter", "t.me/", "https://"]):
            # Залишаємо тільки якщо це основне повідомлення
            if len(lines) > 1:
                continue

        result.append(line)

    return "\n".join(result).strip()


def contains_sambir(text: str) -> bool:
    """Перевіряє чи містить текст ключові слова про Самбір"""
    if not text:
        return False
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in SAMBIR_KEYWORDS)


def contains_power_keywords(text: str) -> bool:
    """Перевіряє чи містить текст ключові слова про відключення світла"""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in POWER_KEYWORDS)


# ================== КНОПКИ ДЛЯ МОДЕРАЦІЇ (INLINE) ==================
def moderation_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опублікувати", callback_data=f"publish:{post_id}"),
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit:{post_id}")
            ],
            [
                InlineKeyboardButton(text="❌ Відмінити", callback_data=f"cancel:{post_id}")
            ]
        ]
    )


def edit_options_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Текст", callback_data=f"edit_text:{post_id}"),
                InlineKeyboardButton(text="🖼 Медіа", callback_data=f"edit_media:{post_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_edit:{post_id}")
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


# ================== МОНІТОРИНГ (оновлена функція - не моніторить тривоги) ==================
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def new_message_handler(event):
    # Отримуємо інформацію про канал-джерело
    source_channel = ""
    if hasattr(event.chat, 'username') and event.chat.username:
        source_channel = event.chat.username
    elif hasattr(event.chat, 'title'):
        source_channel = event.chat.title

    # Отримуємо текст з повідомлення
    text = event.message.message or ""

    # Перевіряємо чи є медіа
    media_type = get_media_type(event)
    has_media = media_type is not None

    # Якщо немає тексту і немає медіа - пропускаємо
    if not text and not has_media:
        return

    text_lower = text.lower() if text else ""

    # Перевіряємо ключові слова
    is_power = contains_power_keywords(text)
    is_sambir = contains_sambir(text)

    # СПЕЦІАЛЬНА ЛОГІКА ДЛЯ ВІДКЛЮЧЕНЬ СВІТЛА:
    # Відключення світла моніторяться ТІЛЬКИ з каналу lvivych_news
    if is_power:
        # Якщо це канал lvivych_news - обробляємо відключення
        if source_channel == "lvivych_news":
            print(f"⚡ Знайдено відключення світла з Lvivych_news: {text[:50]}...")
            # Продовжуємо обробку
        else:
            # Якщо це інший канал - пропускаємо відключення світла
            print(f"⏭ Пропускаємо відключення світла з {source_channel} (тільки з Lvivych_news)")
            # Перевіряємо, чи є інші ключові слова (Самбір)
            if not is_sambir:
                return
            # Якщо є ключові слова про Самбір - обнуляємо прапор відключень
            is_power = False

    # Якщо не підходить під жодну категорію - пропускаємо
    if not (is_power or is_sambir):
        return

    # Перевіряємо чи вже обробляли це повідомлення
    db = load_db()
    msg_uid = f"{event.chat_id}_{event.message.id}"
    if msg_uid in db:
        return
    db.append(msg_uid)
    save_db(db)

    # Очищуємо текст
    cleaned = clean_text(text) if text else ""

    # Додаємо джерело до тексту (якщо можемо ідентифікувати)
    source_info = ""
    if source_channel in SOURCE_NAMES:
        source_info = f"\n\n📰 <b>Джерело:</b> {SOURCE_NAMES[source_channel]}"

    # Створюємо футер
    footer = f"{source_info}\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    # Готуємо текст для публікації
    final_text = cleaned + footer if cleaned else footer

    # Завантажуємо медіа (якщо є)
    media_file = None
    if has_media:
        media_file, _ = await download_media(event, media_type)

    # Зберігаємо пост в очікуючі
    pending_posts[event.message.id] = {
        "text": final_text,
        "media": media_file,
        "media_type": media_type,
        "source": source_channel,
        "is_power": is_power,
        "is_sambir": is_sambir,
        "admin_message_id": None
    }

    # Готуємо прев'ю для адміна
    if is_power:
        preview_type = "⚡ Відключення світла / графіки"
    else:
        preview_type = "📍 Новина з Самбірщини"

    if source_channel in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[source_channel]}"

    preview = f"{preview_type}\n\n{cleaned}" if cleaned else preview_type

    # Надсилаємо адміну на перевірку
    if media_file:
        if media_type == "photo":
            sent_message = await bot.send_photo(ADMIN_ID, FSInputFile(media_file), caption=preview,
                                                reply_markup=moderation_keyboard(event.message.id))
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

    print(f"📥 Отримано нове повідомлення з {source_channel}: {'🔋 Відключення' if is_power else '📍 Самбір'}")


# ================== CALLBACK ДЛЯ INLINE КНОПОК ==================
@dp.callback_query(F.data)
async def handle_callbacks(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = call.data

    # ===== ОБРОБКА КНОПОК ПРОГНОЗУ ПОГОДИ =====
    if data.startswith("weather_"):
        await handle_weather_callbacks(call, state)
        return

    # ===== ПУБЛІКАЦІЯ =====
    if data.startswith("publish"):
        pid = int(data.split(":")[1])
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

            print(f"📤 Опубліковано пост у {TARGET_CHANNEL}: {'🔋 Відключення' if item.get('is_power') else '📍 Самбір'}")

        except Exception as e:
            await call.answer(f"❌ Помилка при публікації: {str(e)}", show_alert=True)

        return

    # ===== ВІДМІНА =====
    if data.startswith("cancel"):
        pid = int(data.split(":")[1])
        item = pending_posts.pop(pid, None)
        if item and item["media"]:
            if os.path.exists(item["media"]):
                os.remove(item["media"])

        # Видаляємо кнопки з повідомлення
        await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
        await call.answer("❌ Відмінено", show_alert=True)
        return

    # ===== РЕДАГУВАННЯ =====
    if data.startswith("edit:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        # Змінюємо клавіатуру на опції редагування
        await call.message.edit_reply_markup(reply_markup=edit_options_keyboard(pid))
        await call.answer("✏️ Оберіть що редагувати", show_alert=False)
        return

    # ===== НАЗАД ПРИ РЕДАГУВАННІ =====
    if data.startswith("back_edit:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        # Повертаємо початкову клавіатуру
        await call.message.edit_reply_markup(reply_markup=moderation_keyboard(pid))
        await call.answer("🔙 Повернуто", show_alert=False)
        return

    # ===== РЕДАГУВАННЯ ТЕКСТУ =====
    if data.startswith("edit_text:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        # Зберігаємо ID повідомлення для редагування
        await state.update_data(edit_post_id=pid, edit_message_id=call.message.message_id)
        await call.message.answer(
            "📝 <b>Редагування тексту</b>\n\n"
            "Надішліть новий текст для посту. Ви можете використовувати HTML-розмітку.\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(EditStates.waiting_edit_text)
        await call.answer("✏️ Надішліть новий текст", show_alert=False)
        return

    # ===== РЕДАГУВАННЯ МЕДІА =====
    if data.startswith("edit_media:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        # Зберігаємо ID повідомлення для редагування
        await state.update_data(edit_post_id=pid, edit_message_id=call.message.message_id)
        await call.message.answer(
            "🖼 <b>Редагування медіа</b>\n\n"
            "Надішліть нове фото або відео. Якщо хочете видалити медіа, надішліть текст 'видалити'.\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(EditStates.waiting_edit_media)
        await call.answer("🖼 Надішліть нове медіа", show_alert=False)
        return


# ================== ОБРОБКА КНОПОК ПРОГНОЗУ ==================
async def handle_weather_callbacks(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = call.data

    # Перевіряємо права адміна
    if user_id != ADMIN_ID:
        await call.answer("⛔ У вас немає доступу до цієї функції", show_alert=True)
        return

    # ===== ПУБЛІКАЦІЯ ПРОГНОЗУ =====
    if data.startswith("weather_publish:"):
        forecast_id = int(data.split(":")[1])

        # Завантажуємо дані
        weather_db = load_weather_data()
        forecast = weather_db.get("pending_forecast")

        if not forecast or forecast.get("id") != forecast_id:
            await call.answer("⚠️ Прогноз не знайдено", show_alert=True)
            return

        # Зберігаємо прогноз для публікації завтра
        weather_db["pending_forecast"] = forecast
        weather_db["last_check"] = datetime.now().isoformat()
        save_weather_data(weather_db)

        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("✅ Прогноз заплановано на публікацію завтра о 08:00", show_alert=True)

        # Редагуємо повідомлення
        await call.message.edit_text(
            f"✅ <b>Прогноз погоди заплановано на публікацію</b>\n\n"
            f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
            f"Текст прогнозу:\n\n{forecast['message']}",
            parse_mode=ParseMode.HTML
        )
        return

    # ===== РЕДАГУВАННЯ ПРОГНОЗУ =====
    elif data.startswith("weather_edit:"):
        forecast_id = int(data.split(":")[1])

        # Змінюємо клавіатуру на опції редагування
        await call.message.edit_reply_markup(reply_markup=weather_edit_options_keyboard(forecast_id))
        await call.answer("✏️ Оберіть опцію редагування", show_alert=False)
        return

    # ===== СКАСУВАННЯ ПРОГНОЗУ =====
    elif data.startswith("weather_cancel:"):
        forecast_id = int(data.split(":")[1])

        # Видаляємо прогноз з очікування
        weather_db = load_weather_data()
        if weather_db.get("pending_forecast", {}).get("id") == forecast_id:
            weather_db["pending_forecast"] = None
            save_weather_data(weather_db)

        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("❌ Прогноз скасовано", show_alert=True)

        # Редагуємо повідомлення
        await call.message.edit_text(
            "❌ <b>Прогноз погоди скасовано</b>",
            parse_mode=ParseMode.HTML
        )
        return

    # ===== НАЗАД ПРИ РЕДАГУВАННІ =====
    elif data.startswith("weather_back:"):
        forecast_id = int(data.split(":")[1])

        # Повертаємо початкову клавіатуру
        await call.message.edit_reply_markup(reply_markup=weather_moderation_keyboard(forecast_id))
        await call.answer("🔙 Повернуто", show_alert=False)
        return

    # ===== РЕДАГУВАННЯ ТЕКСТУ ПРОГНОЗУ =====
    elif data.startswith("weather_edit_text:"):
        forecast_id = int(data.split(":")[1])

        # Завантажуємо дані
        weather_db = load_weather_data()
        forecast = weather_db.get("pending_forecast")

        if not forecast or forecast.get("id") != forecast_id:
            await call.answer("⚠️ Прогноз не знайдено", show_alert=True)
            return

        # Зберігаємо ID для редагування
        await state.update_data(
            weather_edit_id=forecast_id,
            weather_message_id=call.message.message_id
        )

        await call.message.answer(
            "📝 <b>Редагування тексту прогнозу</b>\n\n"
            "Надішліть новий текст прогнозу. Ви можете використовувати HTML-розмітку.\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(WeatherStates.waiting_weather_edit)
        await call.answer("✏️ Надішліть новий текст", show_alert=False)
        return

    # ===== ОНОВЛЕННЯ ДАНИХ ПРОГНОЗУ =====
    elif data.startswith("weather_refresh:"):
        forecast_id = int(data.split(":")[1])

        await call.answer("🔄 Оновлюємо дані прогнозу...", show_alert=False)

        # Отримуємо нові дані про погоду
        weather_data = await get_weather_forecast()
        currency_data = await get_currency_rates()

        # Генеруємо нове повідомлення з AI
        new_message = await generate_weather_message(weather_data, currency_data)

        # Оновлюємо дані
        weather_db = load_weather_data()
        if weather_db.get("pending_forecast", {}).get("id") == forecast_id:
            weather_db["pending_forecast"]["message"] = new_message
            if weather_data:
                weather_db["pending_forecast"]["weather_data"] = weather_data
            save_weather_data(weather_db)

        # Оновлюємо повідомлення
        now = datetime.now()
        await call.message.edit_text(
            f"🌤 <b>Прогноз погоди на завтра ({now.day + 1}.{now.month}.{now.year})</b>\n\n"
            f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
            f"Попередній перегляд (оновлено з AI):\n\n{new_message}",
            reply_markup=weather_moderation_keyboard(forecast_id),
            parse_mode=ParseMode.HTML
        )

        await call.answer("✅ Дані прогнозу оновлено з AI", show_alert=True)
        return

    # ===== ПЕРЕГЕНЕРАЦІЯ ТЕКСТУ ЧЕРЕЗ AI =====
    elif data.startswith("weather_regenerate:"):
        forecast_id = int(data.split(":")[1])

        await call.answer("🤖 Генеруємо новий опис через AI...", show_alert=False)

        # Отримуємо дані прогнозу
        weather_db = load_weather_data()
        forecast = weather_db.get("pending_forecast")

        if not forecast or forecast.get("id") != forecast_id:
            await call.answer("⚠️ Прогноз не знайдено", show_alert=True)
            return

        # Генеруємо новий опис через AI
        weather_data = forecast.get("weather_data")
        if weather_data:
            # Отримуємо курс валют
            currency_data = await get_currency_rates()

            # Генеруємо нове повідомлення
            new_message = await generate_weather_message(weather_data, currency_data)

            # Оновлюємо дані
            weather_db["pending_forecast"]["message"] = new_message
            save_weather_data(weather_db)

            # Оновлюємо повідомлення
            now = datetime.now()
            await call.message.edit_text(
                f"🌤 <b>Прогноз погоди на завтра ({now.day + 1}.{now.month}.{now.year})</b>\n\n"
                f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
                f"Попередній перегляд (перегенеровано через AI):\n\n{new_message}",
                reply_markup=weather_moderation_keyboard(forecast_id),
                parse_mode=ParseMode.HTML
            )

            await call.answer("✅ Текст прогнозу перегенеровано через AI", show_alert=True)
        else:
            await call.answer("⚠️ Немає даних погоди для генерації", show_alert=True)
        return


# ================== ОБРОБКА РЕДАГУВАННЯ ТЕКСТУ ПРОГНОЗУ ==================
@dp.message(WeatherStates.waiting_weather_edit)
async def handle_weather_edit_text(message: Message, state: FSMContext):
    # Перевіряємо, чи це команда скасування
    if message.text and message.text == "/cancel":
        await message.answer("❌ Редагування прогнозу скасовано.")
        await state.clear()
        return

    data = await state.get_data()
    forecast_id = data.get("weather_edit_id")
    message_id = data.get("weather_message_id")

    if not forecast_id:
        await message.answer("⚠️ Дані не знайдено. Редагування скасовано.")
        await state.clear()
        return

    # Оновлюємо текст прогнозу
    weather_db = load_weather_data()
    if weather_db.get("pending_forecast", {}).get("id") == forecast_id:
        weather_db["pending_forecast"]["message"] = message.text
        save_weather_data(weather_db)

    # Оновлюємо повідомлення
    now = datetime.now()
    try:
        await bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=message_id,
            text=f"🌤 <b>Прогноз погоди на завтра ({now.day + 1}.{now.month}.{now.year})</b>\n\n"
                 f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
                 f"Попередній перегляд (відредаговано вручну):\n\n{message.text}",
            reply_markup=weather_moderation_keyboard(forecast_id),
            parse_mode=ParseMode.HTML
        )
        await message.answer("✅ Текст прогнозу успішно оновлено!")
    except Exception as e:
        await message.answer(f"❌ Помилка при оновленні: {str(e)}")

    await state.clear()


# ================== ОБРОБКА РЕДАГУВАННЯ ТЕКСТУ ==================
@dp.message(EditStates.waiting_edit_text)
async def handle_edit_text(message: Message, state: FSMContext):
    # Перевіряємо, чи це команда скасування
    if message.text and message.text == "/cancel":
        await message.answer("❌ Редагування тексту скасовано.")
        await state.clear()
        return

    data = await state.get_data()
    pid = data.get("edit_post_id")
    edit_message_id = data.get("edit_message_id")

    if pid not in pending_posts:
        await message.answer("⚠️ Пост не знайдено. Редагування скасовано.")
        await state.clear()
        return

    # Оновлюємо текст поста
    pending_posts[pid]["text"] = message.text or message.caption or ""

    # Оновлюємо повідомлення з попереднім переглядом
    item = pending_posts[pid]
    preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"

    if item.get("source") in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

    # Отримуємо текст без футера для попереднього перегляду
    full_text = item["text"]
    # Знаходимо джерело у тексті та відокремлюємо основний текст
    lines = full_text.split('\n')
    main_text_lines = []
    for line in lines:
        if not (line.startswith('📰 <b>Джерело:') or line.startswith('<b>🧪 Test Channel</b>')):
            main_text_lines.append(line)
    cleaned_text = '\n'.join(main_text_lines).strip()

    preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

    try:
        # Оновлюємо повідомлення адміну
        if item["media"] and os.path.exists(item["media"]):
            if item["media_type"] == "photo":
                # Видаляємо старе повідомлення і надсилаємо нове
                await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(item["media"]),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
            elif item["media_type"] == "video":
                await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(item["media"]),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )

            # Оновлюємо ID повідомлення
            if sent_message:
                pending_posts[pid]["admin_message_id"] = sent_message.message_id
        else:
            # Оновлюємо текст повідомлення
            await bot.edit_message_caption(
                chat_id=ADMIN_ID,
                message_id=edit_message_id,
                caption=preview,
                reply_markup=moderation_keyboard(pid)
            )

        await message.answer("✅ Текст успішно оновлено!")

    except Exception as e:
        await message.answer(f"❌ Помилка при оновленні: {str(e)}")

    await state.clear()


# ================== ОБРОБКА РЕДАГУВАННЯ МЕДІА ==================
@dp.message(EditStates.waiting_edit_media)
async def handle_edit_media(message: Message, state: FSMContext):
    # Перевіряємо, чи це команда скасування
    if message.text and message.text == "/cancel":
        await message.answer("❌ Редагування медіа скасовано.")
        await state.clear()
        return

    data = await state.get_data()
    pid = data.get("edit_post_id")
    edit_message_id = data.get("edit_message_id")

    if pid not in pending_posts:
        await message.answer("⚠️ Пост не знайдено. Редагування скасовано.")
        await state.clear()
        return

    item = pending_posts[pid]
    old_media = item.get("media")

    # Перевіряємо, чи користувач хоче видалити медіа
    if message.text and message.text.lower() == "видалити":
        # Видаляємо старе медіа
        if old_media and os.path.exists(old_media):
            os.remove(old_media)

        # Оновлюємо дані поста
        item["media"] = None
        item["media_type"] = None

        # Оновлюємо повідомлення адміну (тепер це текстовий пост)
        preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"
        if item.get("source") in SOURCE_NAMES:
            preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

        # Отримуємо текст без футера для попереднього перегляду
        full_text = item["text"]
        lines = full_text.split('\n')
        main_text_lines = []
        for line in lines:
            if not (line.startswith('📰 <b>Джерело:') or line.startswith('<b>🧪 Test Channel</b>')):
                main_text_lines.append(line)
        cleaned_text = '\n'.join(main_text_lines).strip()

        preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

        try:
            # Видаляємо старе повідомлення і надсилаємо нове (текстове)
            await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
            sent_message = await bot.send_message(
                ADMIN_ID,
                preview,
                reply_markup=moderation_keyboard(pid)
            )

            if sent_message:
                pending_posts[pid]["admin_message_id"] = sent_message.message_id

            await message.answer("✅ Медіа успішно видалено!")

        except Exception as e:
            await message.answer(f"❌ Помилка при видаленні медіа: {str(e)}")

        await state.clear()
        return

    # Обробляємо нове медіа
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

    else:
        await message.answer("❌ Будь ласка, надішліть фото або відео. Для видалення медіа напишіть 'видалити'.")
        return

    # Видаляємо старе медіа, якщо воно існує
    if old_media and os.path.exists(old_media):
        os.remove(old_media)

    # Оновлюємо дані поста
    item["media"] = media_file
    item["media_type"] = media_type

    # Оновлюємо повідомлення адміну
    preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"
    if item.get("source") in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

    # Отримуємо текст без футера для попереднього перегляду
    full_text = item["text"]
    lines = full_text.split('\n')
    main_text_lines = []
    for line in lines:
        if not (line.startswith('📰 <b>Джерело:') or line.startswith('<b>🧪 Test Channel</b>')):
            main_text_lines.append(line)
    cleaned_text = '\n'.join(main_text_lines).strip()

    preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

    try:
        # Видаляємо старе повідомлення і надсилаємо нове
        await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)

        if media_file and os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
            elif media_type == "video":
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
        else:
            sent_message = await bot.send_message(
                ADMIN_ID,
                f"{preview}\n\n⚠️ Медіа не вдалося завантажити",
                reply_markup=moderation_keyboard(pid)
            )

        if sent_message:
            pending_posts[pid]["admin_message_id"] = sent_message.message_id

        await message.answer("✅ Медіа успішно оновлено!")

    except Exception as e:
        await message.answer(f"❌ Помилка при оновленні медіа: {str(e)}")
        # Якщо не вдалося оновити, видаляємо нове медіа
        if media_file and os.path.exists(media_file):
            os.remove(media_file)

    await state.clear()


# ================== АДМІН-ПАНЕЛЬ: ПРОГНОЗ ПОГОДИ ==================
@dp.message(F.text == "🌤 Прогноз погоди")
async def handle_weather_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    # Отримуємо дані про погоду
    weather_data = await get_weather_forecast()
    currency_data = await get_currency_rates()

    # Генеруємо повідомлення з AI
    forecast_message = await generate_weather_message(weather_data, currency_data)

    # Отримуємо інформацію про наступний прогноз
    weather_db = load_weather_data()
    next_forecast = weather_db.get("pending_forecast")

    now = datetime.now()
    tomorrow = now + timedelta(days=1)

    info_text = (
        f"🌤 <b>Керування прогнозом погоди</b>\n\n"
        f"⏰ <b>Час модерації:</b> {MODERATION_TIME}\n"
        f"🕗 <b>Час публікації:</b> {WEATHER_REPORT_TIME}\n\n"
    )

    if next_forecast:
        info_text += (
            f"✅ <b>Наступний прогноз заплановано на:</b>\n"
            f"   📅 {tomorrow.strftime('%d.%m.%Y')}\n"
            f"   ⏰ {WEATHER_REPORT_TIME}\n\n"
            f"📝 <b>Текст прогнозу (згенеровано AI):</b>\n"
        )
    else:
        info_text += (
            f"⏳ <b>Наступний прогноз:</b> Буде надіслано на модерацію о {MODERATION_TIME}\n\n"
            f"📝 <b>Поточний перегляд (згенеровано AI):</b>\n"
        )

    # Додаємо кнопки керування
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Оновити зараз", callback_data="weather_refresh_now"),
                InlineKeyboardButton(text="📝 Згенерувати новий", callback_data="weather_generate_now")
            ]
        ]
    )

    await message.answer(
        f"{info_text}\n{forecast_message}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


# ================== ІНШІ ОБРОБНИКИ ПРОГНОЗУ ==================
@dp.callback_query(F.data == "weather_refresh_now")
async def handle_refresh_now(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔ У вас немає доступу", show_alert=True)
        return

    await call.answer("🔄 Оновлюємо дані...", show_alert=False)

    # Отримуємо нові дані
    weather_data = await get_weather_forecast()
    currency_data = await get_currency_rates()

    # Генеруємо нове повідомлення з AI
    new_message = await generate_weather_message(weather_data, currency_data)

    # Оновлюємо повідомлення
    now = datetime.now()
    tomorrow = now + timedelta(days=1)

    info_text = (
        f"🌤 <b>Керування прогнозом погоди</b>\n\n"
        f"⏰ <b>Час модерації:</b> {MODERATION_TIME}\n"
        f"🕗 <b>Час публікації:</b> {WEATHER_REPORT_TIME}\n\n"
        f"⏳ <b>Наступний прогноз:</b> Буде надіслано на модерацію о {MODERATION_TIME}\n\n"
        f"📝 <b>Поточний перегляд (оновлено з AI):</b>\n"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Оновити зараз", callback_data="weather_refresh_now"),
                InlineKeyboardButton(text="📝 Згенерувати новий", callback_data="weather_generate_now")
            ]
        ]
    )

    await call.message.edit_text(
        f"{info_text}\n{new_message}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

    await call.answer("✅ Дані оновлено з AI", show_alert=True)


@dp.callback_query(F.data == "weather_generate_now")
async def handle_generate_now(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔ У вас немає доступу", show_alert=True)
        return

    await call.answer("📝 Генеруємо новий прогноз...", show_alert=False)

    # Отримуємо дані про погоду
    weather_data = await get_weather_forecast()

    # Створюємо унікальний ID
    forecast_id = int(datetime.now().timestamp())

    # Генеруємо повідомлення з AI
    currency_data = await get_currency_rates()
    message_text = await generate_weather_message(weather_data, currency_data)

    # Зберігаємо прогноз
    weather_db = load_weather_data()
    weather_db["pending_forecast"] = {
        "id": forecast_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "message": message_text,
        "weather_data": weather_data
    }
    save_weather_data(weather_db)

    # Надсилаємо на модерацію
    now = datetime.now()
    keyboard = weather_moderation_keyboard(forecast_id)

    await bot.send_message(
        ADMIN_ID,
        f"🌤 <b>Прогноз погоди на завтра ({now.day + 1}.{now.month}.{now.year})</b>\n\n"
        f"Час публікації: {WEATHER_REPORT_TIME}\n\n"
        f"Попередній перегляд (згенеровано AI):\n\n{message_text}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

    await call.answer("✅ Новий прогноз згенеровано через AI та надіслано на модерацію", show_alert=True)


# ================== ОБРОБКА ПОВІДОМЛЕНЬ З ПАНЕЛІ МЕНЮ ==================
@dp.message(F.text == "📤 Поділитися інформацією")
async def handle_share_info(message: Message, state: FSMContext):
    await message.answer(
        "📤 <b>Поділитися інформацією</b>\n\n"
        "Надішліть вашу інформацію (текст, фото, відео з описом), я передам адміну для перевірки та публікації.\n\n"
        "❗️ Надсилаючи матеріали, ви підтверджуєте згоду на їх публікацію в нашому Telegram-каналі. (Самбірчанин | Новини.)\n\n"
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
        category_stats = {"power": 0, "sambir": 0}

        for post in pending_posts.values():
            if post.get("media_type") == "photo":
                media_stats["photo"] += 1
            elif post.get("media_type") == "video":
                media_stats["video"] += 1
            else:
                media_stats["text_only"] += 1

            if post.get("is_power"):
                category_stats["power"] += 1
            if post.get("is_sambir"):
                category_stats["sambir"] += 1

        stats_text = f"📋 <b>Постів в очікуванні:</b> {count}\n\n"
        stats_text += f"<b>Категорії:</b>\n"
        stats_text += f"  ⚡ Відключення світла: {category_stats['power']}\n"
        stats_text += f"  📍 Самбірські новини: {category_stats['sambir']}\n\n"
        stats_text += f"<b>Типи медіа:</b>\n"
        stats_text += f"  📷 Фото: {media_stats['photo']}\n"
        stats_text += f"  🎬 Відео: {media_stats['video']}\n"
        stats_text += f"  📝 Текст: {media_stats['text_only']}\n\n"

        # Список джерел
        sources = {}
        for post in pending_posts.values():
            source = post.get("source", "Невідомо")
            sources[source] = sources.get(source, 0) + 1

        if sources:
            stats_text += "<b>Джерела:</b>\n"
            for source, count in sources.items():
                source_name = SOURCE_NAMES.get(source, source)
                stats_text += f"  • {source_name}: {count}\n"

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

    # Статистика по типах медіа та категоріях
    media_stats = {"photo": 0, "video": 0, "text_only": 0}
    category_stats = {"power": 0, "sambir": 0}

    for post in pending_posts.values():
        if post.get("media_type") == "photo":
            media_stats["photo"] += 1
        elif post.get("media_type") == "video":
            media_stats["video"] += 1
        else:
            media_stats["text_only"] += 1

        if post.get("is_power"):
            category_stats["power"] += 1
        if post.get("is_sambir"):
            category_stats["sambir"] += 1

    stats_text += f"\n<b>Категорії:</b>\n"
    stats_text += f"  ⚡ Відключення світла: {category_stats['power']}\n"
    stats_text += f"  📍 Самбірські новини: {category_stats['sambir']}\n\n"

    stats_text += f"<b>Типи медіа:</b>\n"
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
    welcome_text = (
        "🏠 <b>Головне меню</b>\n\n"
        "Оберіть одну з опцій:\n\n"
        "• 📤 <b>Поділитися інформацією</b> - надіслати новину чи інформацію для публікації\n"
        "• 📢 <b>Розмістити рекламу</b> - залишити заявку на розміщення реклами\n"
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


@dp.message(F.text == "/cancel")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("ℹ️ Немає активної операції для скасування.")
        return

    # Отримуємо поточний стан
    if current_state.startswith("EditStates"):
        await message.answer("❌ Редагування скасовано.")
    elif current_state.startswith("ShareStates"):
        await message.answer("❌ Операція скасована.")

    await state.clear()
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
    print("🧪 Бот запущений. Моніторинг новин Львівщини та Самбірщини")
    print(f"📡 Моніторинг каналів: {len(SOURCE_CHANNELS)} джерел")
    print(f"🎯 Цільовий канал: {TARGET_CHANNEL}")
    print("🚨 Тривоги та відбої: моніторинг через API alerts.in.ua")
    print("⚡ Відключення світла: моніторяться ТІЛЬКИ з lvivych_news")
    print("📍 Самбірські новини: моніторяться з усіх каналів")
    print("🌤 Ранковий прогноз: автоматична публікація о 08:00")
    print("🤖 Генерація опису: через DeepSeek API")
    print("🕘 Модерація прогнозу: надсилання адміну о 21:00")
    print("✏️ Додано функцію редагування постів перед публікацією")
    print("📱 Бот готовий до роботи")

    # Запускаємо фоновий моніторинг тривог
    asyncio.create_task(alerts_monitoring_task())

    # Запускаємо задачу для публікації прогнозу
    asyncio.create_task(publish_scheduled_weather())

    # Запускаємо задачу для модерації прогнозу
    asyncio.create_task(send_weather_for_moderation())

    await client.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
