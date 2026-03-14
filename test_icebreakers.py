"""
test_icebreakers.py
───────────────────
Test script to verify icebreaker generation for real profile pairs from Supabase.

Usage:
    python test_icebreakers.py                    # auto-pick 5 random profile pairs
    python test_icebreakers.py --pairs 10         # test 10 pairs
    python test_icebreakers.py --ids A_ID B_ID    # test a specific pair
    python test_icebreakers.py --match MATCH_ID   # test via match ID
"""

import argparse
import json
import os
import sys
import time
import random
import logging
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
)
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
gemini_scorer = genai.GenerativeModel(
    model_name="gemini-3-flash-preview",
    generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=200),
)


# ── Import core helpers from app ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from app import fetch_profile_full, generate_icebreakers, build_profile_context


# ── Relevance scorer ──────────────────────────────────────────────────────────

def score_icebreaker_relevance(icebreaker: str, profile_b: dict) -> dict:
    """
    Ask Gemini to score the icebreaker's relevance to Profile B.
    Returns {"score": int (1-10), "reason": str}
    """
    import re
    context_b = build_profile_context(profile_b)

    prompt = (
        "You are a strict evaluator of dating app icebreakers. "
        "Score how relevant and personalised the given icebreaker is to the recipient profile.\n"
        "Score 1-3: generic, could be sent to anyone.\n"
        "Score 4-6: references some detail but could be better.\n"
        "Score 7-9: clearly tailored, warm, and specific.\n"
        "Score 10: perfect — witty, specific, and irresistible.\n\n"
        f"Icebreaker:\n{icebreaker}\n\n"
        f"Recipient profile:\n{context_b}\n\n"
        'Return ONLY valid JSON: {"score": <1-10>, "reason": "<one sentence>"}. '
        "No markdown, no code fences."
    )

    response = gemini_scorer.generate_content(prompt)
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"score": 0, "reason": f"Parse error: {raw}"}


def evaluate_pair(profile_a: dict, profile_b: dict, verbose: bool = True) -> dict:
    name_a = profile_a.get("display_name", profile_a["id"][:8])
    name_b = profile_b.get("display_name", profile_b["id"][:8])

    if verbose:
        print(f"\n{'═'*60}")
        print(f"  Pair: {name_a}  →  {name_b}")
        print(f"{'═'*60}")

    result = {
        "profile_a_id": profile_a["id"],
        "profile_b_id": profile_b["id"],
        "profile_a_name": name_a,
        "profile_b_name": name_b,
        "icebreakers": {},
        "scores": {},
        "avg_score": 0,
        "passed": False,
        "error": None,
    }

    try:
        icebreakers = generate_icebreakers(profile_a, profile_b)
        result["icebreakers"] = icebreakers

        total_score = 0
        ib_types = ["question", "observation", "fun_fact"]
        labels = {
            "question": "🤔 Question",
            "observation": "👁  Observation",
            "fun_fact": "✨ Fun Fact",
        }

        for ib_type in ib_types:
            text = icebreakers.get(ib_type, "")
            if verbose:
                print(f"\n{labels[ib_type]}:\n  {text}")

            score_data = score_icebreaker_relevance(text, profile_b)
            result["scores"][ib_type] = score_data
            total_score += score_data.get("score", 0)

            if verbose:
                print(f"  → Score: {score_data['score']}/10 | {score_data['reason']}")

        avg = round(total_score / len(ib_types), 2)
        result["avg_score"] = avg
        result["passed"] = avg >= 6.0  # pass threshold

        if verbose:
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"\n  Average relevance score: {avg}/10  {status}")

    except Exception as e:
        result["error"] = str(e)
        if verbose:
            print(f"  ❌ Error: {e}")

    return result


def run_tests(num_pairs: int = 5, specific_ids: list = None, match_id: str = None, verbose: bool = True):
    print(f"\n{'█'*60}")
    print(f"  ICEBREAKER ENGINE — RELEVANCE TEST")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'█'*60}")

    pairs = []

    if match_id:
        match_res = supabase.table("matches").select("user_a_id, user_b_id, status").eq(
            "id", match_id
        ).single().execute()
        if not match_res.data:
            print(f"Match {match_id} not found.")
            return
        m = match_res.data
        pairs = [(m["user_a_id"], m["user_b_id"])]
        print(f"\n  Mode: Single match test  |  Match ID: {match_id}")

    elif specific_ids:
        pairs = [(specific_ids[0], specific_ids[1])]
        print(f"\n  Mode: Specific pair test")

    else:
        print(f"\n  Mode: Random pairs  |  Pairs to test: {num_pairs}")
        profiles_res = supabase.table("profiles").select("id").eq("is_deleted", False).eq(
            "is_active", True
        ).eq("onboarding_status", "completed").limit(100).execute()

        all_ids = [p["id"] for p in (profiles_res.data or [])]
        if len(all_ids) < 2:
            print("  ❌ Not enough profiles in the database to test.")
            return

        random.shuffle(all_ids)
        used = set()
        for i in range(min(num_pairs, len(all_ids) // 2)):
            a = all_ids[i * 2]
            b = all_ids[i * 2 + 1]
            if a != b and a not in used and b not in used:
                pairs.append((a, b))
                used.add(a)
                used.add(b)

    results = []
    for idx, (a_id, b_id) in enumerate(pairs):
        if verbose:
            print(f"\n[Test {idx+1}/{len(pairs)}]")

        profile_a = fetch_profile_full(a_id)
        profile_b = fetch_profile_full(b_id)

        if not profile_a:
            print(f"  ⚠️  Profile A ({a_id}) not found, skipping.")
            continue
        if not profile_b:
            print(f"  ⚠️  Profile B ({b_id}) not found, skipping.")
            continue

        result = evaluate_pair(profile_a, profile_b, verbose=verbose)
        results.append(result)

        # Rate-limit courtesy pause between pairs
        if idx < len(pairs) - 1:
            time.sleep(1)

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  TEST SUMMARY")
    print(f"{'═'*60}")

    if not results:
        print("  No results to summarise.")
        return

    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"] and not r["error"]]
    errored = [r for r in results if r["error"]]
    all_avgs = [r["avg_score"] for r in results if not r["error"]]
    overall_avg = round(sum(all_avgs) / len(all_avgs), 2) if all_avgs else 0

    print(f"  Total pairs tested : {len(results)}")
    print(f"  Passed (avg ≥ 6)   : {len(passed)}")
    print(f"  Failed             : {len(failed)}")
    print(f"  Errors             : {len(errored)}")
    print(f"  Overall avg score  : {overall_avg}/10")

    if errored:
        print(f"\n  Errors:")
        for r in errored:
            print(f"    {r['profile_a_name']} → {r['profile_b_name']}: {r['error']}")

    # Save JSON report
    report_path = f"test_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(
            {
                "run_at": datetime.utcnow().isoformat() + "Z",
                "pairs_tested": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "errored": len(errored),
                "overall_avg_score": overall_avg,
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\n  📄 Full report saved to: {report_path}")
    print(f"{'█'*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Icebreaker Engine — Relevance Test Script")
    parser.add_argument("--pairs", type=int, default=5, help="Number of random profile pairs to test (default: 5)")
    parser.add_argument("--ids", nargs=2, metavar=("PROFILE_A_ID", "PROFILE_B_ID"), help="Test a specific pair")
    parser.add_argument("--match", metavar="MATCH_ID", help="Test via a specific match ID")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-pair verbose output")
    args = parser.parse_args()

    run_tests(
        num_pairs=args.pairs,
        specific_ids=args.ids,
        match_id=args.match,
        verbose=not args.quiet,
    )