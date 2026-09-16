import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# ======================================================================
# CONFIG — set these as environment variables, or just hardcode here
# ======================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # your Telegram numeric user id
DB_PATH = os.getenv("DB_PATH", "laptop_store.db")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
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
    conn.commit()
    conn.close()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ======================================================================
# STATES
# ======================================================================
class AddLaptop(StatesGroup):
    category = State()
    brand = State()
    model = State()
    price = State()
    config = State()
    photo = State()
    stock_qty = State()


class EditField(StatesGroup):
    waiting_value = State()


class BookLaptop(StatesGroup):
    name = State()
    phone = State()
    address = State()


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
    rows = [[InlineKeyboardButton(text="💻 Browse Laptops", callback_data="browse")]]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ======================================================================
# START
# ======================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Welcome!\nYahan aapko laptops dikhenge category-wise, price aur config ke saath.\n\n"
        "Neeche se browse karo:",
        reply_markup=main_menu_kb(message.from_user.id),
    )


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
    laptops = conn.execute(
        "SELECT * FROM laptops WHERE category = ?", (category,)
    ).fetchall()
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

    kb_rows = []
    if lap["in_stock"] and lap["stock_qty"] > 0:
        kb_rows.append([InlineKeyboardButton(text="🛒 Book Now", callback_data=f"book:{lap['id']}")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"cat:{lap['category']}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    caption = laptop_caption(lap)
    if lap["photo_id"]:
        await callback.message.answer_photo(photo=lap["photo_id"], caption=caption, reply_markup=kb)
        await callback.message.delete()
    else:
        await callback.message.edit_text(caption, reply_markup=kb)


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
    await callback.message.edit_text(
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
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")],
        ]
    )
    await callback.message.edit_text("⚙️ Admin Panel", reply_markup=kb)


@router.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AddLaptop.category)
    await callback.message.answer("📂 Category likho (e.g. Gaming, Business, Student):")


@router.message(AddLaptop.category)
async def add_category(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
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
    await state.update_data(config=message.text.strip())
    await state.set_state(AddLaptop.photo)
    await message.answer("📸 Laptop ki photo bhejo:")


@router.message(AddLaptop.photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await state.set_state(AddLaptop.stock_qty)
    await message.answer("📦 Stock quantity likho (e.g. 3):")


@router.message(AddLaptop.photo)
async def add_photo_invalid(message: Message):
    await message.answer("Photo bhejo (image file), text nahi.")


@router.message(AddLaptop.stock_qty)
async def add_stock_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
    except ValueError:
        await message.answer("Number likho, jaise 3.")
        return

    data = await state.update_data(stock_qty=qty)
    await state.clear()

    conn = db()
    conn.execute(
        """INSERT INTO laptops (category, brand, model, price, config, photo_id, stock_qty, in_stock)
           VALUES (?,?,?,?,?,?,?,1)""",
        (
            data["category"],
            data["brand"],
            data["model"],
            data["price"],
            data["config"],
            data["photo_id"],
            qty,
        ),
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ {data['brand']} {data['model']} add ho gaya!",
        reply_markup=main_menu_kb(message.from_user.id),
    )


# ---------------- MANAGE / EDIT / DELETE ----------------
@router.callback_query(F.data == "admin_list")
async def admin_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    conn = db()
    laptops = conn.execute("SELECT * FROM laptops").fetchall()
    conn.close()

    if not laptops:
        await callback.message.edit_text("Koi laptop add nahi hui abhi tak.")
        return

    kb = [
        [InlineKeyboardButton(text=f"{l['brand']} {l['model']}", callback_data=f"admin_edit:{l['id']}")]
        for l in laptops
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel")])
    await callback.message.edit_text("📋 Manage Laptops:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("admin_edit:"))
async def admin_edit_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    laptop_id = int(callback.data.split(":", 1)[1])
    conn = db()
    lap = conn.execute("SELECT * FROM laptops WHERE id = ?", (laptop_id,)).fetchone()
    conn.close()
    if not lap:
        await callback.answer("Ye laptop mil nahi raha.", show_alert=True)
        return

    toggle_label = "❌ Mark Out of Stock" if lap["in_stock"] else "✅ Mark In Stock"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Edit Price", callback_data=f"admin_ef:{laptop_id}:price")],
            [InlineKeyboardButton(text="✏️ Edit Config", callback_data=f"admin_ef:{laptop_id}:config")],
            [InlineKeyboardButton(text="✏️ Edit Stock Qty", callback_data=f"admin_ef:{laptop_id}:stock_qty")],
            [InlineKeyboardButton(text="📸 Edit Photo", callback_data=f"admin_ef:{laptop_id}:photo_id")],
            [InlineKeyboardButton(text=toggle_label, callback_data=f"admin_toggle:{laptop_id}")],
            [InlineKeyboardButton(text="🗑 Delete", callback_data=f"admin_delete:{laptop_id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_list")],
        ]
    )
    await callback.message.answer(laptop_caption(lap), reply_markup=kb)


@router.callback_query(F.data.startswith("admin_ef:"))
async def admin_edit_field_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    _, laptop_id, field = callback.data.split(":")
    await state.update_data(laptop_id=int(laptop_id), field=field)
    await state.set_state(EditField.waiting_value)

    prompts = {
        "price": "💰 Naya price likho:",
        "config": "⚙️ Naya config likho:",
        "stock_qty": "📦 Nayi stock quantity likho:",
        "photo_id": "📸 Nayi photo bhejo:",
    }
    await callback.message.answer(prompts[field])


@router.message(EditField.waiting_value)
async def admin_edit_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data["field"]
    laptop_id = data["laptop_id"]

    if field == "photo_id":
        if not message.photo:
            await message.answer("Photo bhejo, text nahi.")
            return
        value = message.photo[-1].file_id
    elif field == "stock_qty":
        try:
            value = int(message.text.strip())
        except ValueError:
            await message.answer("Number likho.")
            return
    else:
        value = message.text.strip()

    conn = db()
    conn.execute(f"UPDATE laptops SET {field} = ? WHERE id = ?", (value, laptop_id))
    # if stock qty set above 0, auto mark in_stock true
    if field == "stock_qty" and value > 0:
        conn.execute("UPDATE laptops SET in_stock = 1 WHERE id = ?", (laptop_id,))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ Update ho gaya.", reply_markup=main_menu_kb(message.from_user.id))


@router.callback_query(F.data.startswith("admin_toggle:"))
async def admin_toggle_stock(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    laptop_id = int(callback.data.split(":", 1)[1])
    conn = db()
    lap = conn.execute("SELECT in_stock FROM laptops WHERE id = ?", (laptop_id,)).fetchone()
    new_val = 0 if lap["in_stock"] else 1
    conn.execute("UPDATE laptops SET in_stock = ? WHERE id = ?", (new_val, laptop_id))
    conn.commit()
    conn.close()
    await callback.answer("Status update ho gaya.")
    await admin_edit_menu(callback)


@router.callback_query(F.data.startswith("admin_delete:"))
async def admin_delete_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    laptop_id = int(callback.data.split(":", 1)[1])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Haan, Delete karo", callback_data=f"admin_delete_yes:{laptop_id}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin_edit:{laptop_id}")],
        ]
    )
    await callback.message.answer("Pakka delete karna hai?", reply_markup=kb)


@router.callback_query(F.data.startswith("admin_delete_yes:"))
async def admin_delete_do(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    laptop_id = int(callback.data.split(":", 1)[1])
    conn = db()
    conn.execute("DELETE FROM laptops WHERE id = ?", (laptop_id,))
    conn.commit()
    conn.close()
    await callback.message.answer("🗑 Delete ho gaya.", reply_markup=main_menu_kb(callback.from_user.id))


# ---------------- ORDERS (admin) ----------------
@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    conn = db()
    orders = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    if not orders:
        await message.answer("Koi order abhi tak nahi hai.")
        return
    text = "🧾 <b>Recent Orders</b>\n\n"
    for o in orders:
        text += (
            f"#{o['id']} — {o['laptop_label']}\n"
            f"👤 {o['customer_name']} | 📞 {o['phone']}\n"
            f"🏠 {o['address']}\n"
            f"🕒 {o['created_at']}\n\n"
        )
    await message.answer(text)


# ======================================================================
# MAIN
# ======================================================================
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
