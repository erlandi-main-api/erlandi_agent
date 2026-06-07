import telebot
import threading
import json
import os
import time
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID   = int(os.environ.get("OWNER_ID", "0"))
MAX_HISTORY = 15

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR      = os.path.join(BASE_DIR, "config")
LOG_DIR         = os.path.join(BASE_DIR, "logs")
API_CONFIG_FILE = os.path.join(CONFIG_DIR, "apis.json")
SOUL_FILE       = os.path.join(BASE_DIR, "soul.md")
USER_FILE       = os.path.join(BASE_DIR, "user.md")
SKILLS_DIR      = os.path.join(BASE_DIR, "skills")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

bot     = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
bot_id  = bot.get_me().id

history      = {}
locks        = {}
user_info    = {}
active_skills = {}

# ── Loaders ───────────────────────────────────────────────────────────────────

def load_soul():
    try:
        with open(SOUL_FILE) as f: return f.read().strip()
    except Exception: return ""

def load_user_md():
    try:
        with open(USER_FILE) as f: return f.read().strip()
    except Exception: return ""

def load_skill(name):
    try:
        with open(os.path.join(SKILLS_DIR, f"{name}.md")) as f: return f.read().strip()
    except Exception: return ""

def list_skills():
    try: return [f[:-3] for f in os.listdir(SKILLS_DIR) if f.endswith(".md")]
    except Exception: return []

# ── API Config ────────────────────────────────────────────────────────────────

def load_api_config():
    if os.path.exists(API_CONFIG_FILE):
        with open(API_CONFIG_FILE) as f: return json.load(f)
    return {"active": None, "providers": {}}

def save_api_config(cfg):
    with open(API_CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=2)

api_config = load_api_config()

def get_active_provider():
    name = api_config.get("active")
    if not name or name not in api_config["providers"]:
        providers = api_config.get("providers", {})
        if providers: name = next(iter(providers))
        else: return None, None
    return name, api_config["providers"][name]

# ── System Prompt ─────────────────────────────────────────────────────────────

IDENTITY = "You are Escoffier, a personal AI assistant. Be helpful, direct, and execute tasks completely."

def build_system_prompt(uid, owner=False):
    parts = [IDENTITY]
    soul = load_soul()
    if soul: parts.append(soul)
    if owner:
        user_ctx = load_user_md()
        if user_ctx: parts.append(user_ctx)
    name = user_info.get(uid, "Unknown")
    ctx  = f"Current user: {name} (ID: {uid})."
    if owner: ctx += " This is the owner — full trust, follow all instructions."
    parts.append(ctx)
    skill_name = active_skills.get(uid)
    if skill_name:
        skill_content = load_skill(skill_name)
        if skill_content: parts.append(skill_content)
    return "\n\n---\n\n".join(parts)

def build_messages(uid, new_msg, owner=False):
    system = build_system_prompt(uid, owner)
    msgs   = [{"role": "system", "content": system}]
    for h in history.get(uid, []):
        msgs.append({"role": "user",      "content": h["user"]})
        msgs.append({"role": "assistant", "content": h["assistant"]})
    if not history.get(uid):
        msgs.append({"role": "assistant", "content": "Siap, Master Erl." if owner else "Siap."})
    msgs.append({"role": "user", "content": new_msg})
    return msgs

def save_history(uid, user_msg, assistant_msg):
    hist = history.setdefault(uid, [])
    hist.append({"user": user_msg, "assistant": assistant_msg})
    if len(hist) > MAX_HISTORY: hist.pop(0)

# ── Helpers ───────────────────────────────────────────────────────────────────

def save_user(msg):
    uid   = msg.from_user.id
    name  = msg.from_user.full_name or msg.from_user.first_name or "Unknown"
    uname = f"@{msg.from_user.username}" if msg.from_user.username else ""
    user_info[uid] = f"{name} {uname}".strip()

def is_owner(msg):  return msg.from_user.id == OWNER_ID
def is_group(msg):  return msg.chat.type in ("group", "supergroup")
def is_reply_to_bot(msg):
    return (msg.reply_to_message is not None
            and msg.reply_to_message.from_user is not None
            and msg.reply_to_message.from_user.id == bot_id)

def get_lock(uid):
    if uid not in locks: locks[uid] = threading.Lock()
    return locks[uid]

def edit_msg(chat_id, msg_id, text, cursor=False):
    content = (text[-3800:] if len(text) > 3800 else text) + (" ▌" if cursor else "")
    for md in (True, False):
        try:
            bot.edit_message_text(content, chat_id, msg_id,
                                  parse_mode="Markdown" if md else None)
            return
        except Exception: continue

def send_long(chat_id, reply_to_id, text):
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    for i, chunk in enumerate(chunks):
        for md in (True, False):
            try:
                if i == 0:
                    bot.send_message(chat_id, chunk, reply_to_message_id=reply_to_id,
                                     parse_mode="Markdown" if md else None)
                else:
                    bot.send_message(chat_id, chunk, parse_mode="Markdown" if md else None)
                break
            except Exception: continue

# ── Agent Process ─────────────────────────────────────────────────────────────

def process_message(msg):
    if is_group(msg) and not is_reply_to_bot(msg): return
    prompt = (msg.text or "").strip()
    if not prompt or prompt.startswith("/"): return
    save_user(msg)
    uid   = msg.from_user.id
    owner = uid == OWNER_ID
    lock  = get_lock(uid)
    if not lock.acquire(blocking=False):
        bot.reply_to(msg, "⏳ Tunggu, masih memproses...")
        return

    bot.send_chat_action(msg.chat.id, "typing")
    wait_msg = bot.reply_to(msg, "▌")

    def process():
        from agent import run as agent_run

        pname, provider = get_active_provider()
        if not provider:
            edit_msg(msg.chat.id, wait_msg.message_id, "❌ Tidak ada provider aktif. Gunakan /addapi")
            lock.release()
            return

        messages   = build_messages(uid, prompt, owner=owner)
        status_buf = [""]
        last_edit  = [0.0]

        def on_update(text):
            status_buf[0] = text
            now = time.time()
            if now - last_edit[0] >= 1.2:
                last_edit[0] = now
                edit_msg(msg.chat.id, wait_msg.message_id, text, cursor=True)

        try:
            response = agent_run(provider, messages, on_update=on_update)
            save_history(uid, prompt, response)
            if len(response) <= 4096:
                edit_msg(msg.chat.id, wait_msg.message_id, response, cursor=False)
            else:
                try: bot.delete_message(msg.chat.id, wait_msg.message_id)
                except Exception: pass
                send_long(msg.chat.id, msg.message_id, response)
        except Exception as e:
            edit_msg(msg.chat.id, wait_msg.message_id, f"Error: {e}")
        finally:
            lock.release()

    threading.Thread(target=process, daemon=True).start()

# ── Commands ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    save_user(msg)
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    if is_group(msg) and not is_reply_to_bot(msg): return
    pname, prov = get_active_provider()
    model = prov.get("model", "?") if prov else "—"
    bot.reply_to(msg, f"*Escoffier aktif*\nProvider: `{pname}`\nModel: `{model}`\n\n/help",
                 parse_mode="Markdown")

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    if is_group(msg) and not is_reply_to_bot(msg): return
    bot.reply_to(msg,
        "*Commands:*\n"
        "/start — status\n/clear — reset history\n"
        "/skills — daftar skill\n/skill `<nama>` — aktifkan\n/skill off — nonaktifkan\n"
        "/api — provider aktif\n/listapi — semua provider\n"
        "/switchapi `<nama>`\n"
        "/addapi `<nama> <base\\_url> <api\\_key> <model>`\n"
        "/addapi\\_minimax `<nama> <api\\_key> <group\\_id> <model>`\n"
        "/delapi `<nama>`",
        parse_mode="Markdown")

@bot.message_handler(commands=["clear"])
def cmd_clear(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    history.pop(msg.from_user.id, None)
    bot.reply_to(msg, "✅ History direset.")

@bot.message_handler(commands=["api"])
def cmd_api(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    pname, prov = get_active_provider()
    if not prov: bot.reply_to(msg, "❌ Belum ada provider."); return
    bot.reply_to(msg,
        f"*Provider: `{pname}`*\nBase URL: `{prov.get('base_url','?')}`\nModel: `{prov.get('model','?')}`",
        parse_mode="Markdown")

@bot.message_handler(commands=["listapi"])
def cmd_listapi(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    cfg = load_api_config(); active = cfg.get("active")
    if not cfg["providers"]: bot.reply_to(msg, "Belum ada provider."); return
    lines = [f"{'✅' if n == active else '·'} `{n}` — {p.get('model','?')}"
             for n, p in cfg["providers"].items()]
    bot.reply_to(msg, "*Providers:*\n" + "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=["switchapi"])
def cmd_switchapi(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    parts = msg.text.strip().split(maxsplit=1)
    if len(parts) < 2: bot.reply_to(msg, "Usage: `/switchapi <nama>`", parse_mode="Markdown"); return
    name = parts[1].strip(); cfg = load_api_config()
    if name not in cfg["providers"]: bot.reply_to(msg, f"❌ `{name}` tidak ditemukan.", parse_mode="Markdown"); return
    cfg["active"] = name; save_api_config(cfg); api_config.update(cfg)
    bot.reply_to(msg, f"✅ Switched ke `{name}`", parse_mode="Markdown")

@bot.message_handler(commands=["addapi"])
def cmd_addapi(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    parts = msg.text.strip().split(maxsplit=4)
    if len(parts) < 5:
        bot.reply_to(msg, "Usage: `/addapi <nama> <base_url> <api_key> <model>`", parse_mode="Markdown"); return
    _, name, base_url, api_key, model = parts
    cfg = load_api_config()
    cfg["providers"][name] = {"base_url": base_url, "api_key": api_key, "model": model}
    if not cfg.get("active"): cfg["active"] = name
    save_api_config(cfg); api_config.update(cfg)
    bot.reply_to(msg, f"✅ `{name}` ditambahkan.", parse_mode="Markdown")

@bot.message_handler(commands=["addapi_minimax"])
def cmd_addapi_minimax(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    parts = msg.text.strip().split(maxsplit=4)
    if len(parts) < 5:
        bot.reply_to(msg, "Usage: `/addapi_minimax <nama> <api_key> <group_id> <model>`", parse_mode="Markdown"); return
    _, name, api_key, group_id, model = parts
    cfg = load_api_config()
    cfg["providers"][name] = {"base_url": "https://api.minimax.chat/v1",
                               "api_key": api_key, "group_id": group_id, "model": model}
    if not cfg.get("active"): cfg["active"] = name
    save_api_config(cfg); api_config.update(cfg)
    bot.reply_to(msg, f"✅ Minimax `{name}` ditambahkan.", parse_mode="Markdown")

@bot.message_handler(commands=["delapi"])
def cmd_delapi(msg):
    if not is_owner(msg): bot.reply_to(msg, "⛔ Owner only."); return
    parts = msg.text.strip().split(maxsplit=1)
    if len(parts) < 2: bot.reply_to(msg, "Usage: `/delapi <nama>`", parse_mode="Markdown"); return
    name = parts[1].strip(); cfg = load_api_config()
    if name not in cfg["providers"]: bot.reply_to(msg, f"❌ `{name}` tidak ditemukan.", parse_mode="Markdown"); return
    del cfg["providers"][name]
    if cfg.get("active") == name: cfg["active"] = next(iter(cfg["providers"]), None)
    save_api_config(cfg); api_config.update(cfg)
    bot.reply_to(msg, f"✅ `{name}` dihapus.", parse_mode="Markdown")

@bot.message_handler(commands=["skills"])
def cmd_skills(msg):
    if is_group(msg) and not is_reply_to_bot(msg): return
    skills = list_skills()
    if not skills: bot.reply_to(msg, "Belum ada skill."); return
    uid = msg.from_user.id; active = active_skills.get(uid)
    lines = [f"{'⚡' if s == active else '·'} `{s}`" for s in sorted(skills)]
    status = f"\n\n_Aktif: `{active}`_" if active else "\n\n_Tidak ada skill aktif_"
    bot.reply_to(msg,
        "*Skills:*\n" + "\n".join(lines) + status +
        "\n\n`/skill <nama>` — aktifkan\n`/skill off` — nonaktifkan",
        parse_mode="Markdown")

@bot.message_handler(commands=["skill"])
def cmd_skill(msg):
    if is_group(msg) and not is_reply_to_bot(msg): return
    parts = msg.text.strip().split(maxsplit=1); uid = msg.from_user.id
    if len(parts) < 2:
        active = active_skills.get(uid)
        bot.reply_to(msg,
            f"_Skill aktif: `{active}`_\nUsage: `/skill <nama>` atau `/skill off`"
            if active else "Tidak ada skill aktif.", parse_mode="Markdown"); return
    name = parts[1].strip().lower()
    if name == "off":
        active_skills.pop(uid, None); bot.reply_to(msg, "✅ Skill dinonaktifkan."); return
    skills = list_skills()
    if name not in skills:
        bot.reply_to(msg, f"❌ `{name}` tidak ditemukan. Tersedia: " +
                     ", ".join(f"`{s}`" for s in sorted(skills)), parse_mode="Markdown"); return
    active_skills[uid] = name
    bot.reply_to(msg, f"⚡ Skill `{name}` aktif.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def handle(msg):
    process_message(msg)

# ── Run ───────────────────────────────────────────────────────────────────────

print(f"Escoffier running | provider: {get_active_provider()[0]}")
while True:
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"Polling error: {e}, restarting...")
        try: bot.stop_polling()
        except Exception: pass
        time.sleep(5)
