"""
Day-1 calibration test for Reply Triage. Pulls 50 most recent inbound
emails, runs the agent's classifier, then asks the user to confirm/correct
each label + urgency. Computes match rate. Pass = ≥80% joint match.

If pass: keep Qwen as default model.
If fail: set AGENT_MODEL_REPLY_TRIAGE=claude-sonnet-4-6 and re-run this
script. If Claude also fails, escalate per spec §8.1 fix-window.

Usage:
  python scripts/calibrate_reply_triage.py
  python scripts/calibrate_reply_triage.py --limit 30  # for a quick smoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from agents.reply_triage.gmail_client import fetch_message, list_recent_inbound
from agents.reply_triage.reply_triage_agent import _classify_email


VALID_LABELS = ["needs_reply", "fyi", "spam", "promo"]
VALID_URGENCIES = ["now", "today", "this_week", "later"]


async def main(limit: int) -> int:
    print(f"Fetching last {limit} inbound emails…")
    msg_ids = await list_recent_inbound(limit)
    n = len(msg_ids)
    print(f"Got {n} message IDs.\n")

    matches_label = 0
    matches_urgency = 0
    matches_joint = 0
    evaluated = 0
    skipped_invalid = 0
    skipped_error = 0
    interrupted = False

    try:
        for i, mid in enumerate(msg_ids, 1):
            try:
                msg = await fetch_message(mid)
                agent_pred = await _classify_email(msg)
            except Exception as exc:
                print(f"\n--- {i}/{n} ---")
                print(f"[skipped: {type(exc).__name__}: {exc}]")
                skipped_error += 1
                continue

            print(f"\n--- {i}/{n} ---")
            print(f"From:    {msg['from']}")
            print(f"Subject: {msg['subject'][:80]}")
            print(f"Agent:   label={agent_pred['label']:12s} urgency={agent_pred['urgency']}")
            print("Your label?    [needs_reply / fyi / spam / promo] ", end="", flush=True)
            user_label = input().strip() or agent_pred["label"]
            print("Your urgency?  [now / today / this_week / later] ", end="", flush=True)
            user_urgency = input().strip() or agent_pred["urgency"]

            if user_label not in VALID_LABELS or user_urgency not in VALID_URGENCIES:
                print("invalid input; skipping this email")
                skipped_invalid += 1
                continue

            l_match = (agent_pred["label"] == user_label)
            u_match = (agent_pred["urgency"] == user_urgency)
            matches_label   += int(l_match)
            matches_urgency += int(u_match)
            matches_joint   += int(l_match and u_match)
            evaluated       += 1
    except (KeyboardInterrupt, EOFError):
        interrupted = True
        print("\n\nInterrupted. Partial results below.")

    if n == 0:
        print("\nNo emails to evaluate. Check Gmail credentials.")
        return 1
    if evaluated == 0:
        print("\nNo emails were successfully evaluated.")
        if skipped_invalid:
            print(f"  ({skipped_invalid} skipped due to invalid input)")
        if skipped_error:
            print(f"  ({skipped_error} skipped due to fetch/classify errors)")
        return 1

    print("\n=== Results ===")
    print(f"Evaluated:  {evaluated}/{n}"
          + (f" (skipped {skipped_invalid} invalid)" if skipped_invalid else "")
          + (f" ({skipped_error} errored)" if skipped_error else ""))
    print(f"Label-only match:    {matches_label}/{evaluated} = {100*matches_label/evaluated:.1f}%")
    print(f"Urgency-only match:  {matches_urgency}/{evaluated} = {100*matches_urgency/evaluated:.1f}%")
    print(f"Joint match:         {matches_joint}/{evaluated} = {100*matches_joint/evaluated:.1f}%")
    joint_rate = matches_joint / evaluated

    if interrupted:
        return 130
    if joint_rate >= 0.80:
        print("\n✅ PASSES exit gate (≥80% joint match). Keep current model.")
        return 0
    else:
        print("\n❌ FAILS exit gate. Either (a) flip model to claude-sonnet-4-6:")
        print("     export AGENT_MODEL_REPLY_TRIAGE=claude-sonnet-4-6")
        print("   then re-run this script; or (b) iterate on prompt/schema.")
        return 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.limit)))
