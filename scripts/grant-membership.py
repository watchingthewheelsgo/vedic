"""Manually approve a verified upgrade. Never called by the public API."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.db.engine import init_db, close_db, get_session_factory
from app.db.models import AppUserRecord, ManualMembershipRecord
from app.settings import get_settings


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-id", required=True, help="Verified Clerk user ID from the request"
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--monthly-limit", type=int, default=100)
    parser.add_argument(
        "--note", required=True, help="Approval reference, without payment secrets"
    )
    args = parser.parse_args()
    if not 1 <= args.days <= 366 or not 10 <= args.monthly_limit <= 10000:
        parser.error("days must be 1–366; monthly-limit must be 10–10000")
    await init_db(get_settings())
    try:
        async with get_session_factory()() as db:
            user = await db.scalar(
                select(AppUserRecord).where(AppUserRecord.clerk_user_id == args.user_id)
            )
            if not user:
                raise SystemExit(
                    "Unknown user. Verify the account before granting access."
                )
            record = await db.get(ManualMembershipRecord, args.user_id)
            if record is None:
                record = ManualMembershipRecord(owner_user_id=args.user_id)
                db.add(record)
            # Explicit replacement, not an accidental extension on repeated execution.
            record.expires_at = datetime.now(timezone.utc) + timedelta(days=args.days)
            record.monthly_limit = args.monthly_limit
            record.note = args.note
            await db.commit()
            print(
                f"Membership approved until {record.expires_at.isoformat()}; monthly allowance {record.monthly_limit}."
            )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
