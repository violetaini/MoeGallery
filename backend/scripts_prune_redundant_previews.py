import argparse

from app.database import SessionLocal
from app.services.preview_cleanup_service import prune_redundant_previews


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove legacy preview files for verified SDR static and animated images."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update database rows and permanently remove redundant preview files.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        summary = prune_redundant_previews(db, apply=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode}: checked={summary.checked} candidates={summary.candidates} "
        f"retained_hdr={summary.retained_hdr} retained_unverified={summary.retained_unverified} "
        f"removed={summary.removed} missing={summary.missing} unsafe={summary.unsafe} failed={summary.failed}"
    )


if __name__ == "__main__":
    main()
