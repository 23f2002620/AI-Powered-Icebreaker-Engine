import os
import json
import re
import logging
from datetime import datetime
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Env validation ────────────────────────────────────────────────────────────
_REQUIRED_ENV = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY"]
_missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
if _missing:
    logger.error(f"Missing required environment variables: {', '.join(_missing)}")
    logger.error("Copy .env.example to .env and fill in your credentials.")
    raise SystemExit(1)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
CORS(app)

# ── Supabase client ──────────────────────────────────────────────────────────
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)

# ── Gemini client ─────────────────────────────────────────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel(
    model_name="gemini-3-flash-preview",
    generation_config=genai.GenerationConfig(
        temperature=0.9,
        max_output_tokens=2048,
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_profile_full(profile_id: str) -> dict | None:
    """Fetch a profile along with its mode data, interest chips, lifestyle chips, and prompts."""
    try:
        # Core profile
        profile_res = supabase.table("profiles").select(
            "id, display_name, birth_date, gender, city, state, country, "
            "work_title, work_company, education_level, educated_at, "
            "dating_intention, relationship_type, sexual_orientation, "
            "drinking, smoking, exercise, star_sign, religion, politics, "
            "kids_preference, have_kids, causes_communities, qualities, languages"
        ).eq("id", profile_id).eq("is_deleted", False).single().execute()

        if not profile_res.data:
            return None

        profile = profile_res.data

        # Active profile mode
        current_mode_res = supabase.table("profile_modes").select("id, mode, bio, looking_for").eq(
            "profile_id", profile_id
        ).eq("is_active", True).limit(1).execute()

        mode_data = current_mode_res.data[0] if current_mode_res.data else {}
        profile["mode_bio"] = mode_data.get("bio", "")
        profile["mode"] = mode_data.get("mode", "date")
        profile["looking_for"] = mode_data.get("looking_for", [])
        profile_mode_id = mode_data.get("id")

        if profile_mode_id:
            # Interest chips
            interests_res = supabase.table("profile_mode_interestchips").select(
                "interest_chips(section, label)"
            ).eq("profile_mode_id", profile_mode_id).execute()
            profile["interests"] = [
                row["interest_chips"]["label"]
                for row in (interests_res.data or [])
                if row.get("interest_chips")
            ]

            # Lifestyle chips
            lifestyle_res = supabase.table("profile_mode_lifestylechips").select(
                "lifestyle_chips(label)"
            ).eq("profile_mode_id", profile_mode_id).execute()
            profile["lifestyle"] = [
                row["lifestyle_chips"]["label"]
                for row in (lifestyle_res.data or [])
                if row.get("lifestyle_chips")
            ]

            # Prompts
            prompts_res = supabase.table("profile_mode_prompts").select(
                "user_response, prompt_templates(prompt_text)"
            ).eq("profile_mode_id", profile_mode_id).order("display_order").execute()
            profile["prompts"] = [
                {
                    "question": row["prompt_templates"]["prompt_text"],
                    "answer": row["user_response"],
                }
                for row in (prompts_res.data or [])
                if row.get("prompt_templates")
            ]
        else:
            profile["interests"] = []
            profile["lifestyle"] = []
            profile["prompts"] = []

        return profile

    except Exception as e:
        logger.error(f"Error fetching profile {profile_id}: {e}")
        return None


def build_profile_context(profile: dict) -> str:
    """Convert a profile dict into a readable text block for the AI prompt."""
    lines = []

    name = profile.get("display_name") or "Unknown"
    lines.append(f"Name: {name}")

    if profile.get("birth_date"):
        try:
            dob = datetime.strptime(profile["birth_date"], "%Y-%m-%d")
            age = (datetime.today() - dob).days // 365
            lines.append(f"Age: {age}")
        except Exception:
            pass

    if profile.get("gender"):
        lines.append(f"Gender: {profile['gender']}")

    location_parts = [p for p in [profile.get("city"), profile.get("state"), profile.get("country")] if p]
    if location_parts:
        lines.append(f"Location: {', '.join(location_parts)}")

    if profile.get("work_title") or profile.get("work_company"):
        work = " at ".join(filter(None, [profile.get("work_title"), profile.get("work_company")]))
        lines.append(f"Work: {work}")

    if profile.get("education_level") or profile.get("educated_at"):
        edu = " from ".join(filter(None, [profile.get("education_level"), profile.get("educated_at")]))
        lines.append(f"Education: {edu}")

    if profile.get("mode_bio"):
        lines.append(f"Bio: {profile['mode_bio']}")
    elif profile.get("bio"):
        lines.append(f"Bio: {profile['bio']}")

    if profile.get("interests"):
        lines.append(f"Interests: {', '.join(profile['interests'])}")

    if profile.get("lifestyle"):
        lines.append(f"Lifestyle: {', '.join(profile['lifestyle'])}")

    if profile.get("looking_for"):
        lf = profile["looking_for"]
        lines.append(f"Looking for: {', '.join(lf) if isinstance(lf, list) else lf}")

    if profile.get("dating_intention"):
        lines.append(f"Dating intention: {profile['dating_intention']}")

    if profile.get("relationship_type"):
        lines.append(f"Relationship type: {profile['relationship_type']}")

    if profile.get("causes_communities"):
        lines.append(f"Causes/communities: {', '.join(profile['causes_communities'])}")

    if profile.get("qualities"):
        lines.append(f"Qualities they value: {', '.join(profile['qualities'])}")

    if profile.get("star_sign"):
        lines.append(f"Star sign: {profile['star_sign']}")

    if profile.get("religion"):
        lines.append(f"Religion: {profile['religion']}")

    if profile.get("politics"):
        lines.append(f"Politics: {profile['politics']}")

    for key, label in [("drinking", "Drinking"), ("smoking", "Smoking"), ("exercise", "Exercise")]:
        if profile.get(key):
            lines.append(f"{label}: {profile[key]}")

    if profile.get("prompts"):
        lines.append("Profile prompts:")
        for p in profile["prompts"]:
            lines.append(f'  Q: {p["question"]}')
            lines.append(f'  A: {p["answer"]}')

    return "\n".join(lines)


def _profile_bullets(profile: dict) -> str:
    """Ultra-compact profile summary — only the juiciest details, under 300 chars."""
    bits = []
    if profile.get("display_name"): bits.append(profile["display_name"])
    if profile.get("birth_date"):
        try:
            age = (datetime.today() - datetime.strptime(profile["birth_date"], "%Y-%m-%d")).days // 365
            bits.append(f"{age}y")
        except Exception:
            pass
    if profile.get("city"):         bits.append(profile["city"])
    if profile.get("work_title"):   bits.append(profile["work_title"])
    lines = [", ".join(bits)] if bits else []
    if profile.get("mode_bio"):     lines.append(profile["mode_bio"][:150])
    if profile.get("interests"):    lines.append("Likes: " + ", ".join(profile["interests"][:5]))
    if profile.get("prompts"):
        p = profile["prompts"][0]
        lines.append(f'Q: {p["question"][:60]} A: {p["answer"][:80]}')
    return "\n".join(lines)


def _call_gemini(prompt: str) -> str:
    """Call Gemini and return the full response text, handling truncation gracefully."""
    response = gemini_model.generate_content(prompt)

    if not response.candidates:
        raise ValueError("Gemini returned no candidates")

    candidate = response.candidates[0]
    finish_reason = str(candidate.finish_reason)
    logger.info(f"Gemini finish_reason={finish_reason}")

    raw = response.text.strip()

    # finish_reason=2 means MAX_TOKENS — response was cut off
    # Patch the sentence to end cleanly rather than erroring out
    if finish_reason == "2":
        logger.warning(f"MAX_TOKENS hit — patching truncated response: {raw!r}")
        raw = raw.rstrip(" ,;:-")
        if raw and raw[-1] not in ".!?":
            raw += "."

    # Strip markdown fences and surrounding quotes
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        raw = raw[1:-1].strip()
    return raw


def generate_icebreakers(profile_a: dict, profile_b: dict) -> dict:
    """
    Generate 3 icebreakers using 3 separate minimal Gemini calls.
    Sends only the recipient profile to keep prompts short and output tokens free.
    """
    # Only send recipient profile — that's what the icebreaker is about
    ctx_b = _profile_bullets(profile_b)
    name_b = profile_b.get("display_name", "them")

    def call(kind: str, instruction: str) -> str:
        prompt = (
            f"Dating app icebreaker — {kind}.\n"
            f"Write one complete sentence to send to {name_b}.\n"
            f"Profile: {ctx_b}\n"
            f"Task: {instruction}\n"
            "Rules: Complete sentence only. No ellipsis. No truncation. "
            "Reference a specific profile detail. No quotes. No labels. Just the sentence."
        )
        return _call_gemini(prompt)

    question    = call("question",    "Ask a curious, open-ended question based on their profile.")
    observation = call("observation", "Make a warm, genuine observation about something in their profile.")
    fun_fact    = call("fun_fact",    "Write a playful, witty line tied to their interests that makes them smile.")

    return {
        "question":    question,
        "observation": observation,
        "fun_fact":    fun_fact,
        "model_used":  "gemini-2.0-flash",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    """Return a paginated list of active profiles (id + display_name + city)."""
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        offset = (page - 1) * per_page

        res = supabase.table("profiles").select(
            "id, display_name, city, state, gender, birth_date, current_mode, is_verified"
        ).eq("is_deleted", False).eq("is_active", True
        ).order("created_at", desc=True).range(offset, offset + per_page - 1).execute()

        return jsonify({"success": True, "profiles": res.data or [], "page": page, "per_page": per_page})
    except Exception as e:
        logger.error(f"list_profiles error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/profiles/<profile_id>", methods=["GET"])
def get_profile(profile_id: str):
    """Return full enriched profile data."""
    profile = fetch_profile_full(profile_id)
    if not profile:
        return jsonify({"success": False, "error": "Profile not found"}), 404
    return jsonify({"success": True, "profile": profile})


@app.route("/api/icebreakers/generate", methods=["POST"])
def generate():
    """
    Generate 3 icebreakers for a match pair.
    Body: { "profile_a_id": "...", "profile_b_id": "..." }
    """
    body = request.get_json(force=True) or {}
    profile_a_id = body.get("profile_a_id", "").strip()
    profile_b_id = body.get("profile_b_id", "").strip()

    if not profile_a_id or not profile_b_id:
        return jsonify({"success": False, "error": "profile_a_id and profile_b_id are required"}), 400

    if profile_a_id == profile_b_id:
        return jsonify({"success": False, "error": "profile_a_id and profile_b_id must be different"}), 400

    profile_a = fetch_profile_full(profile_a_id)
    if not profile_a:
        return jsonify({"success": False, "error": f"Profile A ({profile_a_id}) not found"}), 404

    profile_b = fetch_profile_full(profile_b_id)
    if not profile_b:
        return jsonify({"success": False, "error": f"Profile B ({profile_b_id}) not found"}), 404

    try:
        icebreakers = generate_icebreakers(profile_a, profile_b)
        return jsonify({
            "success": True,
            "profile_a": {"id": profile_a_id, "name": profile_a.get("display_name", "")},
            "profile_b": {"id": profile_b_id, "name": profile_b.get("display_name", "")},
            "icebreakers": icebreakers,
        })
    except Exception as e:
        logger.error(f"Icebreaker generation error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/icebreakers/generate-for-match/<match_id>", methods=["POST"])
def generate_for_match(match_id: str):
    """
    Convenience endpoint: resolve user_a and user_b from the matches table,
    then generate icebreakers.
    Body: { "sender_id": "<profile_id_of_the_sender>" }  (optional — defaults to user_a)
    """
    try:
        match_res = supabase.table("matches").select(
            "id, user_a_id, user_b_id, status"
        ).eq("id", match_id).single().execute()

        if not match_res.data:
            return jsonify({"success": False, "error": "Match not found"}), 404

        match = match_res.data
        if match["status"] != "active":
            return jsonify({"success": False, "error": "Match is not active"}), 400

        body = request.get_json(force=True) or {}
        sender_id = body.get("sender_id", match["user_a_id"])

        if sender_id == match["user_a_id"]:
            profile_a_id, profile_b_id = match["user_a_id"], match["user_b_id"]
        else:
            profile_a_id, profile_b_id = match["user_b_id"], match["user_a_id"]

        profile_a = fetch_profile_full(profile_a_id)
        profile_b = fetch_profile_full(profile_b_id)

        if not profile_a or not profile_b:
            return jsonify({"success": False, "error": "Could not load one or both profiles"}), 404

        icebreakers = generate_icebreakers(profile_a, profile_b)
        return jsonify({
            "success": True,
            "match_id": match_id,
            "profile_a": {"id": profile_a_id, "name": profile_a.get("display_name", "")},
            "profile_b": {"id": profile_b_id, "name": profile_b.get("display_name", "")},
            "icebreakers": icebreakers,
        })
    except Exception as e:
        logger.error(f"generate_for_match error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)