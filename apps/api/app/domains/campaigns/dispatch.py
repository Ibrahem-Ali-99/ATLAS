"""Persist recipient claims before handing messages to the scheduled transport."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.campaigns.audience import audience_filters
from app.domains.campaigns.models import Campaign, CampaignDelivery, CustomerSegment
from app.domains.campaigns.preferences import public_origin, token_for
from app.domains.campaigns.resend import live_sender, send_resend
from app.integrations.email import OutboundEmail, send_email
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

MAX_RECIPIENTS = 1_000
ACTIVE = ("scheduled", "dispatching")
CLAIM_WINDOW = timedelta(minutes=15)


def _segment(db: Session, campaign: Campaign) -> CustomerSegment | None:
    return db.scalar(
        select(CustomerSegment).where(
            CustomerSegment.id == campaign.segment_id,
            CustomerSegment.organization_id == campaign.organization_id,
        )
    )


def schedule(
    db: Session, campaign: Campaign, scheduled_at: datetime | None, *, delivery_mode: str
) -> int:
    if campaign.status != "draft":
        raise AppError(409, "campaign_locked", "Only draft campaigns can be scheduled")
    if delivery_mode != get_settings().email_mode:
        raise AppError(409, "campaign_mode_changed", "Review the current campaign delivery mode")
    if delivery_mode == "live":
        live_sender(db, campaign.organization_id)
    public_origin()
    if (
        not campaign.subject
        or not campaign.subject.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in campaign.subject)
        or not campaign.body
        or not campaign.body.strip()
    ):
        raise AppError(422, "invalid_campaign_message", "Enter a valid subject and email body")
    segment = _segment(db, campaign)
    if segment is None:
        raise AppError(422, "segment_required", "Select a segment before scheduling")
    now = datetime.now(UTC)
    if scheduled_at is not None and scheduled_at <= now:
        raise AppError(422, "invalid_campaign_schedule", "Select a future date and time")
    candidates, valid, consented, suppressed = audience_filters(
        campaign.organization_id, segment.definition, operational_only=delivery_mode == "live"
    )
    emails = db.scalars(
        select(candidates.c.email)
        .where(valid, consented, ~suppressed)
        .distinct()
        .order_by(candidates.c.email)
        .limit(MAX_RECIPIENTS + 1)
    ).all()
    if not emails:
        raise AppError(422, "empty_campaign_audience", "No eligible recipients in this segment")
    if len(emails) > MAX_RECIPIENTS:
        raise AppError(
            422, "campaign_audience_limit", "Select a segment with up to 1,000 recipients"
        )
    db.add_all(
        CampaignDelivery(campaign_id=campaign.id, email=email, status="queued") for email in emails
    )
    campaign.status = "scheduled"
    campaign.delivery_mode = delivery_mode
    campaign.scheduled_at = scheduled_at or now
    campaign.updated_at = now
    return len(emails)


def cancel(db: Session, campaign: Campaign) -> None:
    if campaign.status not in ACTIVE:
        raise AppError(409, "campaign_locked", "Only active campaigns can be cancelled")
    db.execute(
        update(CampaignDelivery)
        .where(CampaignDelivery.campaign_id == campaign.id, CampaignDelivery.status == "queued")
        .values(status="cancelled")
    )
    campaign.status = "cancelled"
    campaign.finished_at = campaign.updated_at = datetime.now(UTC)


def counts(db: Session, campaign: Campaign) -> dict[str, int]:
    rows = db.execute(
        select(CampaignDelivery.status, func.count())
        .where(CampaignDelivery.campaign_id == campaign.id)
        .group_by(CampaignDelivery.status)
    )
    return {status: count for status, count in rows}


def _eligible(db: Session, campaign: Campaign, email: str) -> bool:
    segment = _segment(db, campaign)
    if segment is None:
        return False
    candidates, valid, consented, suppressed = audience_filters(
        campaign.organization_id,
        segment.definition,
        operational_only=campaign.delivery_mode == "live",
    )
    return (
        db.scalar(
            select(candidates.c.email)
            .where(candidates.c.email == email, valid, consented, ~suppressed)
            .limit(1)
        )
        is not None
    )


def _deliver(db: Session, campaign: Campaign, row: CampaignDelivery) -> None:
    row.status = "sending"
    row.claimed_at = datetime.now(UTC)
    delivery_id = row.id
    db.commit()
    message_id = None
    try:
        db.refresh(campaign)
        if campaign.status == "cancelled" or not _eligible(db, campaign, row.email):
            result = "skipped"
        else:
            unsubscribe_url = (
                f"{public_origin()}/api/v1/campaign-preferences/{token_for(delivery_id)}"
            )
            message = OutboundEmail(
                row.email,
                campaign.subject or "",
                f"{campaign.body or ''}\n\nUnsubscribe: {unsubscribe_url}",
                row.id.hex,
                unsubscribe_url,
            )
            if campaign.delivery_mode == "live":
                sender, key = live_sender(db, campaign.organization_id)
                receipt = send_resend(message, sender=sender, api_key=key)
            else:
                receipt = send_email(
                    message, db=db, organization_id=campaign.organization_id, sandbox_only=True
                )
            message_id = receipt.message_id
            result = "accepted"
    except (AppError, DeliveryFailed):
        result = "failed"
    except OutcomeUncertain:
        result = "needs_attention"
    # An expired claim may already have been resolved by another worker.
    db.rollback()
    db.execute(
        update(CampaignDelivery)
        .where(CampaignDelivery.id == delivery_id, CampaignDelivery.status == "sending")
        .values(status=result, message_id=message_id)
    )
    db.commit()


def dispatch_due(db: Session, *, limit: int = 10) -> int:
    processed = 0
    db.execute(
        update(CampaignDelivery)
        .where(
            CampaignDelivery.status == "sending",
            CampaignDelivery.claimed_at < datetime.now(UTC) - CLAIM_WINDOW,
        )
        .values(status="needs_attention")
    )
    queued = (
        select(CampaignDelivery.id)
        .where(CampaignDelivery.campaign_id == Campaign.id, CampaignDelivery.status == "queued")
        .exists()
    )
    sending = (
        select(CampaignDelivery.id)
        .where(CampaignDelivery.campaign_id == Campaign.id, CampaignDelivery.status == "sending")
        .exists()
    )
    for _ in range(limit):
        now = datetime.now(UTC)
        campaign = db.scalar(
            select(Campaign)
            .where(Campaign.status.in_(ACTIVE), Campaign.scheduled_at <= now, queued | ~sending)
            .order_by(Campaign.scheduled_at, Campaign.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if campaign is None:
            db.commit()
            break
        row = db.scalar(
            select(CampaignDelivery)
            .where(CampaignDelivery.campaign_id == campaign.id, CampaignDelivery.status == "queued")
            .order_by(CampaignDelivery.id)
            .limit(1)
        )
        if row is None:
            outcomes = counts(db, campaign)
            if not outcomes.get("sending"):
                campaign.status = (
                    "completed_with_errors"
                    if any(
                        outcomes.get(status)
                        for status in (
                            "failed",
                            "needs_attention",
                            "bounced",
                            "complained",
                        )
                    )
                    else "completed"
                )
                campaign.finished_at = campaign.updated_at = now
            db.commit()
            continue
        campaign.status = "dispatching"
        campaign.updated_at = now
        _deliver(db, campaign, row)
        processed += 1
    return processed
