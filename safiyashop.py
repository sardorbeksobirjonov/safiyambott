import logging
import asyncio
import uuid

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# =================== CONFIG ===================
API_TOKEN = "8338086151:AAGqxGNEpKVScrRXQJa9JkAZVcaXavm9G2E"  # <- bu yerga tokenni qo'ying
ADMIN_ID = 6674217656          # <- bu yerga admin telegram ID yozing

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# =================== TEMP DATABASE ===================
products = {
    "koylaklar": [],
    "main_menu": []
}

# =================== STATE CLASSES ===================
class BuyState(StatesGroup):
    choosing_category = State()
    choosing_product = State()
    choosing_size = State()
    asking_quantity = State()
    asking_more = State()
    asking_phone = State()
    confirming_order = State()

class AdminState(StatesGroup):
    choosing_section = State()
    adding_mainmenu_name = State()
    renaming_mainmenu = State()
    adding_name = State()
    adding_price = State()
    adding_sizes = State()
    adding_image = State()

# =================== TEMP STORAGE ===================
admin_temp_data = {}
user_cart = {}

# =================== HELPERS ===================
def new_menu_id() -> str:
    return "menu_" + uuid.uuid4().hex[:8]

def get_category_label(key: str) -> str:
    if key == "koylaklar":
        return "Koylaklar"
    for m in products["main_menu"]:
        if m["id"] == key:
            return m["name"]
    return key

# =================== USER PART ===================
@dp.message(F.text == "/start")
async def cmd_start(msg: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="1. Koylaklar", callback_data="category_koylaklar")

    if products["main_menu"]:
        for idx, menu in enumerate(products["main_menu"], start=2):
            builder.button(text=f"{idx}. {menu['name']}", callback_data=f"category_{menu['id']}")

    builder.adjust(1)
    await msg.answer("🛍 <b>Kategoriya tanlang:</b>", reply_markup=builder.as_markup())
    await state.set_state(BuyState.choosing_category)

@dp.callback_query(F.data.startswith("category_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)

    if category not in products:
        return await callback.message.answer("❌ Bu bo‘lim mavjud emas.")

    items = products.get(category, [])
    if not items:
        return await callback.message.answer("❌ Bu bo‘limda mahsulotlar yo‘q.")

    for idx, item in enumerate(items):
        builder = InlineKeyboardBuilder()
        builder.button(text="Tanlash", callback_data=f"product_{idx}")
        builder.adjust(1)
        caption = f"<b>{item['name']}</b>\nNarxi: {item['price']} so'm"
        if item.get("sizes"):
            caption += f"\nRazmerlar: {', '.join(item['sizes'])}"
        if 'image' in item:
            await callback.message.answer_photo(item['image'], caption=caption, reply_markup=builder.as_markup())
        else:
            await callback.message.answer(caption, reply_markup=builder.as_markup())

    await state.set_state(BuyState.choosing_product)

@dp.callback_query(F.data.startswith("product_"))
async def product_selected(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.replace("product_", ""))
    data = await state.get_data()
    category = data.get("category")
    if not category or category not in products:
        return await callback.message.answer("❗ Kategoriya topilmadi. /start ni qayta yuboring.")

    try:
        product = products[category][idx]
    except IndexError:
        return await callback.message.answer("❗ Mahsulot topilmadi.")

    await state.update_data(selected_product=product)

    # Agar mahsulotda razmer bo'lsa - avval razmer tanlattiramiz
    if product.get("sizes"):
        builder = InlineKeyboardBuilder()
        for size in product["sizes"]:
            builder.button(text=size, callback_data=f"size_{size}")
        builder.adjust(3)
        await callback.message.answer("📏 Razmer tanlang:", reply_markup=builder.as_markup())
        await state.set_state(BuyState.choosing_size)
    else:
        await callback.message.answer("📦 Nechta dona olmoqchisiz?\n\n namuna 2")
        await state.set_state(BuyState.asking_quantity)

@dp.callback_query(F.data.startswith("size_"))
async def size_selected(callback: CallbackQuery, state: FSMContext):
    size = callback.data.replace("size_", "")
    await state.update_data(selected_size=size)
    await callback.message.answer(f"📦 {size} razmer tanlandi. Endi nechta dona olmoqchisiz?\n\n namuna 2")
    await state.set_state(BuyState.asking_quantity)

@dp.message(BuyState.asking_quantity)
async def ask_quantity(msg: Message, state: FSMContext):
    try:
        quantity = int(msg.text)
        data = await state.get_data()
        product = data['selected_product']
        size = data.get("selected_size", "-")

        user_cart.setdefault(msg.from_user.id, []).append({
            "name": product['name'],
            "price": product['price'],
            "size": size,
            "quantity": quantity
        })

        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Yana olish", callback_data="more_yes")
        builder.button(text="✅ Yakunlash", callback_data="more_no")
        builder.adjust(1)

        await msg.answer(
            f"🛒 {product['name']} ({size}) - {quantity} dona qo‘shildi.\nYana mahsulot olasizmi?",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BuyState.asking_more)
    except ValueError:
        await msg.answer("❗ Faqat son kiriting!")

@dp.callback_query(F.data.startswith("more_"))
async def ask_more(callback: CallbackQuery, state: FSMContext):
    if callback.data == "more_yes":
        await cmd_start(callback.message, state)
    else:
        await callback.message.answer("📱 Telefon raqamingizni yuboring (99891xxxxxxx):")
        await state.set_state(BuyState.asking_phone)

@dp.message(BuyState.asking_phone)
async def phone_received(msg: Message, state: FSMContext):
    phone = msg.text.strip()
    if not phone.startswith("998") or not phone.isdigit():
        return await msg.answer("❗ To‘g‘ri telefon raqam kiriting (99891xxxxxxx)")

    cart = user_cart.get(msg.from_user.id, [])
    total = sum(i['price'] * i['quantity'] for i in cart)
    summary = "\n".join([f"{i['name']} ({i['size']}) - {i['quantity']} dona - {i['price']*i['quantity']} so'm" for i in cart])

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data="confirm_order")
    builder.adjust(1)

    await state.update_data(phone=phone)
    await msg.answer(
        f"📦 <b>Buyurtma:</b>\n{summary}\n\n<b>Umumiy:</b> {total} so'm\n📞 Tel: {phone}",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BuyState.confirming_order)

@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = user_cart.get(callback.from_user.id, [])
    total = sum(i['price'] * i['quantity'] for i in cart)
    summary = "\n".join([f"{i['name']} ({i['size']}) - {i['quantity']} dona - {i['price']*i['quantity']} so'm" for i in cart])

    message = (
        f"🛒 <b>Yangi buyurtma!</b>\n"
        f"👤 @{callback.from_user.username or callback.from_user.full_name}\n"
        f"📞 {data.get('phone')}\n\n{summary}\n\n<b>Umumiy:</b> {total} so'm"
    )
    await bot.send_message(chat_id=ADMIN_ID, text=message)
    await callback.message.answer("✅ Buyurtmangiz qabul qilindi!")
    await state.clear()
    user_cart[callback.from_user.id] = []

# =================== ADMIN PANEL ===================
@dp.message(F.text == "/admin")
async def admin_panel(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("⛔ Siz admin emassiz.")

    builder = InlineKeyboardBuilder()
    builder.button(text="1. Koylak qo‘shish", callback_data="add_koylaklar")
    builder.button(text="➕ Asosiy menyu qo‘shish", callback_data="add_mainmenu")

    if products["main_menu"]:
        builder.button(text="— Dinamik menyular —", callback_data="noop")
        for menu in products["main_menu"]:
            builder.button(text=f"➕ {menu['name']} mahsulot qo‘shish", callback_data=f"addproduct_{menu['id']}")
            builder.button(text=f"✏️ {menu['name']} nomini o‘zgartirish", callback_data=f"rename_{menu['id']}")

    builder.adjust(1)
    await msg.answer("🔧 <b>Admin panel:</b>", reply_markup=builder.as_markup())
    await state.set_state(AdminState.choosing_section)

@dp.callback_query(F.data.startswith("add_") | F.data.startswith("addproduct_"))
async def admin_choose_section(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return await callback.message.answer("⛔ Ruxsat yo‘q")
    data = callback.data

    if data == "add_mainmenu":
        await callback.message.answer("🆕 Asosiy menyu nomini kiriting:")
        await state.set_state(AdminState.adding_mainmenu_name)
        return

    section = data.replace("add_", "").replace("addproduct_", "")
    admin_temp_data[callback.from_user.id] = {"section": section}
    await callback.message.answer("📝 Mahsulot nomini kiriting:")
    await state.set_state(AdminState.adding_name)

@dp.message(AdminState.adding_mainmenu_name)
async def admin_add_mainmenu(msg: Message, state: FSMContext):
    name = msg.text.strip()
    menu_id = new_menu_id()
    products["main_menu"].append({"id": menu_id, "name": name})
    products[menu_id] = []
    await msg.answer(f"✅ '{name}' qo‘shildi.")
    await admin_panel(msg, state)

@dp.message(AdminState.adding_name)
async def admin_add_name(msg: Message, state: FSMContext):
    admin_temp_data[msg.from_user.id]['name'] = msg.text.strip()
    await msg.answer("💰 Narxini kiriting:")
    await state.set_state(AdminState.adding_price)

@dp.message(AdminState.adding_price)
async def admin_add_price(msg: Message, state: FSMContext):
    try:
        price = int(msg.text)
        admin_temp_data[msg.from_user.id]['price'] = price
        await msg.answer("📏 Razmerlarni kiriting (vergul bilan, masalan: S,M,L,XL):")
        await state.set_state(AdminState.adding_sizes)
    except ValueError:
        await msg.answer("❗ Faqat son kiriting!")

@dp.message(AdminState.adding_sizes)
async def admin_add_sizes(msg: Message, state: FSMContext):
    sizes = [s.strip() for s in msg.text.split(",") if s.strip()]
    admin_temp_data[msg.from_user.id]['sizes'] = sizes
    await msg.answer("📷 Rasm yuboring:")
    await state.set_state(AdminState.adding_image)

@dp.message(AdminState.adding_image)
async def admin_add_image(msg: Message, state: FSMContext):
    if not msg.photo:
        return await msg.answer("❗ Rasm yuboring.")

    file_id = msg.photo[-1].file_id
    data = admin_temp_data[msg.from_user.id]
    section = data['section']
    item = {"name": data['name'], "price": data['price'], "sizes": data['sizes'], "image": file_id}

    if section not in products:
        products[section] = []
    products[section].append(item)

    await msg.answer(f"✅ '{item['name']}' qo‘shildi ({get_category_label(section)}) bo‘limiga.")
    await state.clear()
    await admin_panel(msg, state)

# =================== RUN ===================
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
