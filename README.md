# erlandi_agent

Autonomous Telegram AI Agent — personal second brain & operational partner.

Supports any OpenAI-compatible LLM provider (Gemini, Claude, GPT, Llama via Cloudflare, etc.) with streaming responses, per-user skill activation, multi-provider switching, and persistent conversation history.

---

## Features

- **Streaming responses** — live token-by-token output via Telegram message editing
- **Multi-provider LLM** — plug in any OpenAI-compatible API (Gemini, Claude, GPT, Ollama, Cloudflare AI, custom proxies)
- **Skill system** — activate context-specific personas per user via `.md` files (recon, exploit, osint, code, report)
- **Owner-only commands** — all admin operations restricted to `OWNER_ID`
- **Persistent history** — rolling conversation memory (configurable window)
- **Soul + User identity** — custom AI persona loaded from `soul.md` + `user.md`
- **Group support** — responds only when mentioned/replied in group chats

---

## Structure

```
erlandi_agent/
├── bot.py              # Main bot
├── soul.md             # AI persona & operational directives
├── user.md             # User profile (gitignored)
├── config/
│   ├── apis.json       # Active providers (gitignored)
│   └── apis.example.json
├── skills/
│   ├── recon.md
│   ├── osint.md
│   ├── exploit.md
│   ├── code.md
│   └── report.md
├── logs/               # Runtime logs (gitignored)
├── .env.example
└── .gitignore
```

---

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/erlandi-main-api/erlandi_agent
cd erlandi_agent
pip install pyTelegramBotAPI requests
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set BOT_TOKEN and OWNER_ID
```

```env
BOT_TOKEN=your_telegram_bot_token_from_botfather
OWNER_ID=your_telegram_user_id
```

### 3. Configure LLM provider

```bash
cp config/apis.example.json config/apis.json
# Edit config/apis.json — add your provider(s)
```

Example with Gemini:
```json
{
  "active": "gemini",
  "providers": {
    "gemini": {
      "type": "openai_compatible",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
      "api_key": "YOUR_GEMINI_API_KEY",
      "model": "gemini-2.5-flash"
    }
  }
}
```

### 4. Customize persona

Edit `soul.md` to define the AI's identity, behavior, and operational context.

Edit `user.md` to define user profile and special instructions.

### 5. Run

```bash
# Direct
python bot.py

# Background (Termux / Linux)
nohup python bot.py >> logs/bot.log 2>&1 &

# With .env loaded
export $(cat .env | xargs) && python bot.py
```

---

## Commands

| Command | Description |
|---|---|
| `/start` | Show active provider and model |
| `/help` | List all commands |
| `/clear` | Reset conversation history |
| `/skills` | List available skills |
| `/skill <name>` | Activate a skill |
| `/skill off` | Deactivate current skill |
| `/api` | Show active provider |
| `/listapi` | List all configured providers |
| `/switchapi <name>` | Switch active provider |
| `/addapi <name> <base_url> <api_key> <model>` | Add OpenAI-compatible provider |
| `/addapi_minimax <name> <api_key> <group_id> <model>` | Add MiniMax provider |
| `/delapi <name>` | Remove a provider |

---

## Skills

Skills are markdown files in `skills/` that inject additional context/instructions into the system prompt when activated.

| Skill | Focus |
|---|---|
| `recon` | Reconnaissance & attack surface mapping |
| `osint` | Open-source intelligence gathering |
| `exploit` | Vulnerability exploitation & PoC development |
| `code` | Code generation & review |
| `report` | Bug bounty / pentest report writing |

Add custom skills: create `skills/yourskill.md` with instructions, then activate with `/skill yourskill`.

---

## Multi-Provider Example

```bash
# Add multiple providers
/addapi claude https://api.anthropic.com/v1 sk-ant-xxx claude-sonnet-4-6
/addapi gemini https://generativelanguage.googleapis.com/v1beta/openai AIza-xxx gemini-2.5-flash
/addapi llama https://api.cloudflare.com/client/v4/accounts/xxx/ai/v1 cf-token @cf/meta/llama-3.3-70b-instruct-fp8-fast

# Switch between them
/switchapi gemini
/switchapi llama
```

---

## Deployment on Serv00 / VPS

```bash
# Keep running after SSH disconnect
nohup python bot.py >> logs/bot.log 2>&1 &
echo $! > logs/bot.pid

# Stop
kill $(cat logs/bot.pid)
```

---

## License

MIT
