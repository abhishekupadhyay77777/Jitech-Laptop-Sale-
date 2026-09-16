import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    InputMediaPhoto,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)

# ======================================================================
# CONFIG
# ======================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "laptop_store.db")
MAX_PHOTOS = 4

logging.basicConfig(level=logging.INFO)

# parse_mode="HTML" yahan set kiya hai — isliye ab <b>bold</b> jaisa tag
# sahi se bold dikhega, text mein tag literally nahi dikhega.
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ======================================================================
# DATABASE
# ======================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS laptops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            price TEXT NOT NULL,
            config TEXT NOT NULL,
            photo_id TEXT,
            stock_qty INTEGER DEFAULT 0,
            in_stock INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id INTEGER NOT NULL,
            photo_id TEXT NOT NULL,
            position INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id INTEGER,
            laptop_label TEXT,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            tg_user_id INTEGER,
            tg_username TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            tg_user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_seen TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def track_user(user_id: int, username: str | None):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users (tg_user_id, username, first_seen) VALUES (?,?,?)",
        (user_id, username or "-", datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()


def get_photos(laptop_id: int, legacy_photo_id: str | None) -> list[str]:
    conn = db()
    rows = conn.execute(
        "SELECT photo_id FROM photos WHERE laptop_id = ? ORDER BY position", (laptop_id,)
    ).fetchall()
    conn.close()
    if rows:
        return [r["photo_id"] for r in rows]
    if legacy_photo_id:
        return [legacy_photo_id]
    return []


# ======================================================================
# STATES
# ======================================================================
class AddLaptop(StatesGroup):
    category = State()
    brand = State()
    model = State()
    price = State()
    config = State()
    photos = State()
    stock_qty = State()


class EditField(StatesGroup):
    waiting_value = State()


class EditPhotos(StatesGroup):
    collecting = State()


class BookLaptop(StatesGroup):
    name = State()
    phone = State()
    address = State()


class SearchLaptop(StatesGroup):
    keyword = State()


class Broadcast(StatesGroup):
    waiting_text = State()


# ======================================================================
# HELPERS
# ======================================================================
def laptop_caption(row: sqlite3.Row) -> str:
    status = f"✅ In Stock ({row['stock_qty']})" if row["in_stock"] and row["stock_qty"] > 0 else "❌ Out of Stock"
    return (
        f"💻 <b>{row['brand']} {row['model']}</b>\n"
        f"📂 Category: {row['category']}\n"
        f"💰 Price: ₹{row['price']}\n"
        f"⚙️ Config: {row['config']}\n"
        f"📦 Status: {status}"
    )


def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💻 Browse Laptops", callback_data="browse")],
        [InlineKeyboardButton(text="🔍 Search", callback_data="search_start")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_laptop_detail(target: Message, lap: sqlite3.Row):
    """Sends photos (up to 4, as an album) then the detail + buttons."""
    photos = get_photos(lap["id"], lap["photo_id"])
    if photos:
        if len(photos) == 1:
            await target.answer_photo(photo=photos[0])
        else:
            media = [InputMediaPhoto(media=p) for p in photos[:MAX_PHOTOS]]
            await target.answer_media_group(media=media)

    kb_rows = []
    if lap["in_stock"] and lap["stock_qty"] > 0:
        kb_rows.append([InlineKeyboardButton(text="🛒 Book Now", callback_data=f"book:{lap['id']}")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"cat:{lap['category']}")])
    await target.answer(laptop_caption(lap), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


# ======================================================================
# COMMAND MENU SETUP
# ======================================================================
async def setup_commands():
    customer_cmds = [
        BotCommand(command="start", description="Bot shuru karo"),
        BotCommand(command="search", description="Laptop search karo"),
        BotCommand(command="help", description="Madad"),
    ]
    await bot.set_my_commands(customer_cmds, scope=BotCommandScopeDefault())

    if ADMIN_ID:
        admin_cmds = customer_cmds + [
            BotCommand(command="addlaptop", description="Naya laptop add karo"),
            BotCommand(command="mylaptops", description="Sab laptops manage karo"),
            BotCommand(command="orders", description="Saare orders dekho"),
            BotCommand(command="stats", description="Stock/orders summary"),
            BotCommand(command="broadcast", description="Sabko message bhejo"),
            BotCommand(command="cancel", description="Current process cancel karo"),
        ]
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=ADMIN_ID))


# ======================================================================
# START / HELP / CANCEL
# ======================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    track_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Welcome!\nYahan aapko laptops dikhenge category-wise, price aur config ke saath.\n\n"
        "Neeche se browse karo ya search karo:",
        reply_markup=main_menu_kb(message.from_user.id),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "ℹ️ <b>Kaise use karein</b>\n\n"
        "/start — Menu dekho\n"
        "/search &lt;keyword&gt; — Laptop dhundo, e.g. /search hp\n"
    )
    if is_admin(message.from_user.id):
        text += (
            "\n<b>Admin commands:</b>\n"
            "/addlaptop — Naya laptop add karo\n"
            "/mylaptops — Sab laptops manage karo\n"
            "/orders — Saare booking requests dekho\n"
            "/stats — Summary dekho\n"
            "/broadcast &lt;message&gt; — Sabko ek saath message bhejo\n"
            "/cancel — Chal rahi process rokno\n"
        )
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.", reply_markup=ReplyKeyboardRemove())


# ======================================================================
# CUSTOMER FLOW — BROWSE
# ======================================================================
@router.callback_query(F.data == "browse")
async def browse_categories(callback: CallbackQuery):
    conn = db()
    cats = conn.execute("SELECT DISTINCT category FROM laptops").fetchall()
    conn.close()

    if not cats:
        await callback.message.edit_text("Abhi koi laptop available nahi hai. Baad me check karo.")
        return

    kb = [
        [InlineKeyboardButton(text=c["category"], callback_data=f"cat:{c['category']}")]
        for c in cats
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")])
    await callback.message.edit_text(
        "📂 Category choose karo:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("cat:"))
async def list_laptops_in_category(callback: CallbackQuery):
    category = callback.data.split(":", 1)[1]
    conn = db()
    laptops = conn.execute("SELECT * FROM laptops WHERE category = ?", (category,)).fetchall()
    conn.close()

    if not laptops:
        await callback.answer("Is category me abhi kuch nahi hai.", show_alert=True)
        return

    kb = []
    for lap in laptops:
        tag = "" if (lap["in_stock"] and lap["stock_qty"] > 0) else " (Out of Stock)"
        kb.append(
            [InlineKeyboardButton(text=f"{lap['brand']} {lap['model']}{tag}", callback_data=f"laptop:{lap['id']}")]
        )
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="browse")])
    await callback.message.edit_text(
        f"📂 {category} — available models:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("laptop:"))
async def show_laptop_detail(callback: CallbackQuery):
    laptop_id = int(callback.data.split(":", 1)[1])
    conn = db()
    lap = conn.execute("SELECT * FROM laptops WHERE id = ?", (laptop_id,)).fetchone()
    conn.close()

    if not lap:
        await callback.answer("Ye laptop ab available nahi hai.", show_alert=True)
        return

    await callback.message.delete()
    await send_laptop_detail(callback.message, lap)


# ======================================================================
# SEARCH
# ======================================================================
@router.callback_query(F.data == "search_start")
async def search_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchLaptop.keyword)
    await callback.message.answer("🔍 Kya dhundna hai? Brand, model ya category likho (e.g. HP, Gaming):")


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, command: CommandObject):
    if command.args:
        await run_search(message, command.args.strip())
    else:
        await state.set_state(SearchLaptop.keyword)
        await message.answer("🔍 Kya dhundna hai? Brand, model ya category likho:")


@router.message(SearchLaptop.keyword)
async def search_get_keyword(message: Message, state: FSMContext):
    await state.clear()
    await run_search(message, message.text.strip())


async def run_search(message: Message, keyword: str):
    like = f"%{keyword}%"
    conn = db()
    results = conn.execute(
        "SELECT * FROM laptops WHERE brand LIKE ? OR model LIKE ? OR category LIKE ?",
        (like, like, like),
    ).fetchall()
    conn.close()

    if not results:
        await message.answer(f"'{keyword}' se koi laptop nahi mila. Kuch aur try karo.")
        return

    kb = []
    for lap in results:
        tag = "" if (lap["in_stock"] and lap["stock_qty"] > 0) else " (Out of Stock)"
        kb.append(
            [InlineKeyboardButton(text=f"{lap['brand']} {lap['model']}{tag}", callback_data=f"laptop:{lap['id']}")]
        )
    kb.append([InlineKeyboardButton(text="⬅️ Menu", callback_data="back_main")])
    await message.answer(
        f"🔍 '{keyword}' ke liye {len(results)} result mile:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


# ======================================================================
# CUSTOMER FLOW — BOOKING
# ======================================================================
@router.callback_query(F.data.startswith("book:"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    laptop_id = int(callback.data.split(":", 1)[1])
    conn = db()
    lap = conn.execute("SELECT * FROM laptops WHERE id = ?", (laptop_id,)).fetchone()
    conn.close()

    if not lap or not (lap["in_stock"] and lap["stock_qty"] > 0):
        await callback.answer("Sorry, ye ab out of stock hai.", show_alert=True)
        return

    await state.update_data(laptop_id=laptop_id, laptop_label=f"{lap['brand']} {lap['model']}")
    await state.set_state(BookLaptop.name)
    await callback.message.answer(
        f"📝 Booking: {lap['brand']} {lap['model']}\n\nApna pura naam likho:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(BookLaptop.name)
async def booking_get_name(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(BookLaptop.phone)
    await message.answer("📞 Apna mobile number likho:")


@router.message(BookLaptop.phone)
async def booking_get_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(BookLaptop.address)
    await message.answer("🏠 Apna full address likho:")


@router.message(BookLaptop.address)
async def booking_get_address(message: Message, state: FSMContext):
    data = await state.update_data(address=message.text.strip())
    await state.clear()

    conn = db()
    conn.execute(
        """INSERT INTO orders (laptop_id, laptop_label, customer_name, phone, address,
           tg_user_id, tg_username, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (
            data["laptop_id"],
            data["laptop_label"],
            data["customer_name"],
            data["phone"],
            data["address"],
            message.from_user.id,
            message.from_user.username or "-",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    conn.close()

    await message.answer(
        "✅ Aapki booking request mil gayi hai! Hum jaldi hi aapse contact karenge.",
        reply_markup=main_menu_kb(message.from_user.id),
    )

    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            (
                "🆕 <b>New Booking Request</b>\n\n"
                f"💻 Laptop: {data['laptop_label']}\n"
                f"👤 Name: {data['customer_name']}\n"
                f"📞 Phone: {data['phone']}\n"
                f"🏠 Address: {data['address']}\n"
                f"🔗 Telegram: @{message.from_user.username or 'no-username'} (id: {message.from_user.id})"
            ),
        )


@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.message.answer(
        "👋 Welcome back! Neeche se browse karo:", reply_markup=main_menu_kb(callback.from_user.id)
    )


# ======================================================================
# ADMIN PANEL
# ======================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ye tumhare liye nahi hai.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add Laptop", callback_data="admin_add")],
            [InlineKeyboardButton(text="📋 Manage Laptops", callback_data="admin_list")],
            [InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")],
        ]
    )
    await callback.message.answer("⚙️ Admin Panel", reply_markup=kb)


@router.message(Command("stats"))
@router.callback_query(F.data == "admin_stats")
async def admin_stats(event):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM laptops").fetchone()["c"]
    in_stock = conn.execute("SELECT COUNT(*) c FROM laptops WHERE in_stock=1 AND stock_qty>0").fetchone()["c"]
    out_stock = total - in_stock
    orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    text = (
        "📊 <b>Stats</b>\n\n"
        f"💻 Total Laptops: {total}\n"
        f"✅ In Stock: {in_stock}\n"
        f"❌ Out of Stock: {out_stock}\n"
        f"🧾 Total Orders: {orders}\n"
        f"👥 Total Bot Users: {users}"
    )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
    else:
        await event.answer(text)


@router.callback_query(F.data == "admin_add")
@router.message(Command("addlaptop"))
async def admin_add_start(event, state: FSMContext):
    if not is_admin(event.from_user.id):
        return
    await state.set_state(AddLaptop.category)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("📂 Category likho (e.g. Gaming, Business, Student):")


@router.message(AddLaptop.category)
async def add_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddLaptop.brand)
    await message.answer("🏷 Brand likho (e.g. HP, Dell, Lenovo):")


@router.message(AddLaptop.brand)
async def add_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip())
    await state.set_state(AddLaptop.model)
    await message.answer("📝 Model name likho:")


@router.message(AddLaptop.model)
async def add_model(message: Message, state: FSMContext):
    await state.update_data(model=message.text.strip())
    await state.set_state(AddLaptop.price)
    await message.answer("💰 Price likho (sirf number, e.g. 45000):")


@router.message(AddLaptop.price)
async def add_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(AddLaptop.config)
    await message.answer("⚙️ Configuration likho (RAM, processor, storage, screen etc):")


@router.message(AddLaptop.config)
async def add_config(message: Message, state: FSMContext):
    await state.update_data(config=message.text.strip(), photo_list=[])
    await state.set_state(AddLaptop.photos)
    await message.answer(f"📸 Laptop ki photo bhejo (1 se {MAX_PHOTOS} tak). Sab bhej ke /done likhna:")


@router.message(AddLaptop.photos, F.photo)
async def add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_list = data.get("photo_list", [])
    if len(photo_list) >= MAX_PHOTOS:
        await message.answer(f"Max {MAX_PHOTOS} photos already ho gayi. /done likho aage badhne ke liye.")
        return
    photo_list.append(message.photo[-1].file_id)
    await state.update_data(photo_list=photo_list)

    if len(photo_list) >= MAX_PHOTOS:
        await s
