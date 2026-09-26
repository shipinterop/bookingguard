"""CLI interface for BookingGuard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bookingguard.application.analyze import analyze_booking_change
from bookingguard.domain.models import Verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bookingguard",
        description="AI-powered booking change assurance for maritime logistics.",
    )
    sub = parser.add_subparsers(dest="command")

    analyze_p = sub.add_parser("analyze", help="Analyze a booking amendment against a plan.")
    analyze_p.add_argument("--original", required=True, type=Path, help="Path to original booking text.")
    analyze_p.add_argument("--amendment", required=True, type=Path, help="Path to amendment text.")
    analyze_p.add_argument("--plan", required=True, type=Path, help="Path to plan CSV.")
    analyze_p.add_argument("--booking-ref", default=None, help="Override booking reference.")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "analyze":
        return _run_analyze(args)

    return 0


def _run_analyze(args: argparse.Namespace) -> int:
    original_text = args.original.read_text(encoding="utf-8")
    amendment_text = args.amendment.read_text(encoding="utf-8")
    plan_csv = args.plan.read_text(encoding="utf-8")

    result = analyze_booking_change(
        original_text=original_text,
        amendment_text=amendment_text,
        plan_csv=plan_csv,
        booking_reference=args.booking_ref,
    )

    # Print results
    print(f"Booking: {result.booking_reference}")
    print()

    if result.before.get("cy_cutoff") or result.after.get("cy_cutoff"):
        print("CY Cutoff")
        if result.before.get("cy_cutoff"):
            print(f"  Before: {result.before['cy_cutoff']}")
        if result.after.get("cy_cutoff"):
            print(f"  After : {result.after['cy_cutoff']}")
        print()

    if result.findings:
        for finding in result.findings:
            verdict_label = finding.verdict.value.upper().replace("_", " ")
            print(f"RESULT: {verdict_label}")
            if finding.delta_hours is not None:
                print(f"  Delta: {finding.delta_hours:+.1f}h")
            if finding.detail:
                print(f"  Detail: {finding.detail}")
            if finding.needs_review_reasons:
                print(f"  Review reasons: {', '.join(finding.needs_review_reasons)}")
            print()
    else:
        # P1: Always print the overall verdict even when no findings
        verdict_label = result.verdict.value.upper().replace("_", " ")
        print(f"RESULT: {verdict_label}")
        print()

    if result.errors:
        print("Errors:")
        for err in result.errors:
            print(f"  - {err}")

    # Nonzero exit for conflict or needs_review (analysis incomplete)
    if result.verdict == Verdict.CONFLICT:
        return 1
    if result.verdict == Verdict.NEEDS_REVIEW:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
