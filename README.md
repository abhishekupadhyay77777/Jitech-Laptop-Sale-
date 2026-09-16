# Laptop Stock Bot

Telegram bot jisme sirf tum (admin) laptops add/edit/delete kar sakte ho — price, config, photo, stock qty ke saath. Customers sirf browse aur book kar sakte hain. Admin controls kisi aur ko nahi dikhte.

## 1. Bot Token lo
1. Telegram pe `@BotFather` ko message karo
2. `/newbot` bhejo, naam aur username do
3. Jo token milega (kuch aisa: `123456789:ABCdefGhIJKlmNoPQRstuVWxyz`) usse copy karo

## 2. Apna Telegram User ID lo
1. Telegram pe `@userinfobot` ko message karo
2. Wo tumhara numeric user ID dega (e.g. `987654321`) — yahi ADMIN_ID hai

## 3. Local pe test karna (optional)
```bash
pip install -r requirements.txt

# Windows (cmd):
set BOT_TOKEN=your_token_here
set ADMIN_ID=your_id_here

# Mac/Linux:
export BOT_TOKEN=your_token_here
export ADMIN_ID=your_id_here

python bot.py
```
Ya seedha `bot.py` ke top mein `BOT_TOKEN` aur `ADMIN_ID` values daal do (env variables ki zaroorat nahi padegi).

## 4. Free hosting (Railway.app se — sabse aasan)
1. GitHub pe naya repo banao, ye 3 files (`bot.py`, `requirements.txt`, `README.md`) push karo
2. [railway.app](https://railway.app) pe sign up karo (GitHub se login)
3. "New Project" → "Deploy from GitHub repo" → apna repo select karo
4. Project ke "Variables" tab mein `BOT_TOKEN` aur `ADMIN_ID` add karo
5. Start command automatically `python bot.py` detect ho jayega (agar nahi to Settings mein manually daal do)
6. Deploy hote hi bot 24/7 live ho jayega

(Render.com pe bhi same tarike se free deploy ho sakta hai — "Background Worker" service banake.)

## Kaise use karna hai

### Customer side
- `/start` → "Browse Laptops" → category choose karo → laptop select karo → photo, price, config, stock status dikhega
- Agar stock hai to "Book Now" button milega → naam, number, address maangega → submit hote hi tumhe (admin ko) turant message aayega poori detail ke saath
- Agar stock khatam hai to laptop list mein "(Out of Stock)" likha aayega aur Book Now button nahi dikhega

### Admin side (sirf tumhare ADMIN_ID se hi dikhega)
- `/start` → "⚙️ Admin Panel"
- **Add Laptop** — step by step category, brand, model, price, config, photo, stock quantity poochega
- **Manage Laptops** — har laptop ke liye: price/config/stock/photo edit karo, in-stock/out-of-stock toggle karo, ya delete karo
- `/orders` — last 15 booking requests ek saath dekh sakte ho

## Notes / limitations
- Ek hi admin support karta hai (ADMIN_ID). Multiple admins chahiye ho to bata dena, add kar dunga.
- Payment integration nahi hai — jaisa maanga tha, sirf details collect hoti hain, payment tum khud customer se baat karke handle karoge.
- Database SQLite file (`laptop_store.db`) hai jo automatically ban jayegi jahan bot chal raha hai. Railway/Render pe restart hone se data safe rehta hai jab tak persistent volume use karo (free tier pe kabhi kabhi reset ho sakta hai — zaroorat pade to bata dena, Postgres pe switch kar dunga).
