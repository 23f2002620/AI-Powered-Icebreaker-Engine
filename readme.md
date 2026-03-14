# AI-Powered Icebreaker Engine

An internal admin tool that generates **3 personalised conversation starters** for matched dating app users — a question, an observation, and a fun fact — powered by Google Gemini 2.0 Flash and backed by Supabase.

---

## Quick Start

```bash
# 1. Clone and set up environment
git clone <your-repo-url>
cd icebreaker-engine
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env with your keys (see Environment Variables below)

# 3. Run
python app.py
# Open http://localhost:5000
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` | **service_role** key — NOT the anon key. Found in Supabase → Settings → API |
| `GEMINI_API_KEY` | Google Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `FLASK_SECRET_KEY` | Any random string for Flask session signing |
| `FLASK_ENV` | `development` (debug mode) or `production` |
| `PORT` | Optional. Defaults to `5000` |

---

## Project Structure

```
icebreaker-engine/
├── app.py                  ← Flask backend (all routes + Supabase + Gemini)
├── test_icebreakers.py     ← CLI relevance test script
├── requirements.txt
├── .env
├── templates/
│   └── index.html          ← Admin UI (no hardcoded data)
└── static/
    ├── css/style.css
    └── js/app.js
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/profiles` | All active profiles (used to populate dropdowns) |
| `GET` | `/api/profiles/<id>` | Full enriched profile |
| `POST` | `/api/icebreakers/generate` | Generate icebreakers for a profile pair |
| `POST` | `/api/icebreakers/generate-for-match/<match_id>` | Generate from a match row |

### Generate icebreakers

```bash
POST /api/icebreakers/generate
Content-Type: application/json

{
  "profile_a_id": "<sender-uuid>",
  "profile_b_id": "<recipient-uuid>"
}
```

**Response:**
```json
{
  "success": true,
  "profile_a": { "id": "...", "name": "Priya" },
  "profile_b": { "id": "...", "name": "Arjun" },
  "icebreakers": {
    "question":    "Since you hike in Coorg, what's the most unexpected thing you discovered there?",
    "observation": "Your indie music taste combined with UX work suggests you find beauty in the details most overlook.",
    "fun_fact":    "People who love spicy food and astronomy are statistically more likely to be night owls — which one keeps you up?",
    "model_used":  "gemini-2.0-flash",
    "generated_at": "2026-03-14T10:00:00Z"
  }
}
```

---

## Test Script

Scores icebreaker quality (1–10) using Gemini as an evaluator. Pass = avg ≥ 6.0.

```bash
python test_icebreakers.py                        # 5 random pairs (default)
python test_icebreakers.py --pairs 10             # 10 pairs
python test_icebreakers.py --ids <A_ID> <B_ID>    # specific pair
python test_icebreakers.py --match <MATCH_ID>     # from match table
python test_icebreakers.py --quiet                # suppress per-pair output
```

Saves a full JSON report: `test_report_YYYYMMDD_HHMMSS.json`

---

## How Icebreakers Are Generated

1. Both profiles are fetched with full context: interests, lifestyle chips, prompt Q&As, bio, work, education, star sign, dating intention, and more.
2. A plain-text summary is built for each profile.
3. Gemini is called **3 times** — once per icebreaker type — each returning a single focused sentence. This prevents JSON truncation issues that occur with a single large combined call.

---

## Supabase Tables Used (Read-Only)

| Table | Purpose |
|---|---|
| `profiles` | Core identity and attributes |
| `profile_modes` | Active mode bio and intent |
| `profile_mode_interestchips` | Interest tags |
| `interest_chips` | Interest label lookup |
| `profile_mode_lifestylechips` | Lifestyle tags |
| `lifestyle_chips` | Lifestyle label lookup |
| `profile_mode_prompts` | User Q&A answers |
| `prompt_templates` | Prompt question text |
| `matches` | Used by generate-for-match endpoint |

> The app is **read-only** — it never writes to or modifies the database.

---

## Production

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

- Set `FLASK_ENV=production`
- Never expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend
- Gemini free tier: 15 req/min, 1M tokens/day — each generation uses 3 calls
- Consider caching results for high-volume usage

---

## Dependencies

| Package | Version |
|---|---|
| flask | 3.0.3 |
| flask-cors | 4.0.1 |
| supabase | 2.5.3 |
| google-generativeai | 0.8.3 |
| python-dotenv | 1.0.1 |
| requests | 2.32.3 |