"""CLI interface for BookingGuard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bookingguard.application.analyze import analyze_booking_change
from bookingguard.domain.models import ProcessingStatus, Verdict


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
    # Handle file read errors
    try:
        original_text = args.original.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        print(f"Error reading original file: {e}", file=sys.stderr)
        return 3
    try:
        amendment_text = args.amendment.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        print(f"Error reading amendment file: {e}", file=sys.stderr)
        return 3
    try:
        plan_csv = args.plan.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        print(f"Error reading plan file: {e}", file=sys.stderr)
        return 3

    result = analyze_booking_change(
        original_text=original_text,
        amendment_text=amendment_text,
        plan_csv=plan_csv,
        booking_reference=args.booking_ref,
    )

    # Print results
    print(f"Booking: {result.booking_reference}")
    status_label = result.processing_status.value.upper()
    print(f"Status: {status_label}")
    print()

    if result.before.get("cy_cutoff") or result.after.get("cy_cutoff"):
        print("CY Cutoff")
        if result.before.get("cy_cutoff"):
            print(f"  Before: {result.before['cy_cutoff']}")
        if result.after.get("cy_cutoff"):
            print(f"  After : {result.after['cy_cutoff']}")
        print()

    # Always print aggregate verdict first
    agg_label = result.verdict.value.upper().replace("_", " ")
    print(f"VERDICT: {agg_label}")
    print()

    # Then print individual findings if any
    if result.findings:
        for finding in result.findings:
            finding_label = finding.verdict.value.upper().replace("_", " ")
            print(f"  Finding: {finding_label}")
            if finding.delta_hours is not None:
                print(f"    Delta: {finding.delta_hours:+.1f}h")
            if finding.detail:
                print(f"    Detail: {finding.detail}")
            if finding.needs_review_reasons:
                print(f"    Review reasons: {', '.join(finding.needs_review_reasons)}")
            print()

    # Show evidence
    verified_evidence = [e for e in result.evidence if e.verified]
    if verified_evidence:
        print("Evidence:")
        for ev in verified_evidence:
            print(f'  "{ev.quote}"')
        print()

    if result.errors:
        print("Errors:")
        for err in result.errors:
            print(f"  - {err}")

    # Exit codes: 0=clean, 1=conflict, 2=needs_review, 3=processing_failure
    if result.processing_status == ProcessingStatus.FAILED:
        return 3
    if result.verdict == Verdict.CONFLICT:
        return 1
    if result.verdict == Verdict.NEEDS_REVIEW:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
