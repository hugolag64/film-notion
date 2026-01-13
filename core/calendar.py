from datetime import datetime, timedelta
from config import calendar_service, CALENDAR_ID


def _event_uid(page_id: str) -> str:
    return f"notion-film-{page_id}"


def _event_exists_by_uid(uid: str) -> bool:
    events = calendar_service.events().list(
        calendarId=CALENDAR_ID,
        privateExtendedProperty=f"notion_uid={uid}"
    ).execute().get("items", [])
    return bool(events)


def _event_exists_by_title_and_day(title: str, day: datetime) -> bool:
    start = day.strftime("%Y-%m-%dT00:00:00Z")
    end = day.strftime("%Y-%m-%dT23:59:59Z")

    events = calendar_service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start,
        timeMax=end,
        q=title
    ).execute().get("items", [])
    return bool(events)


def create_release_reminder(
    *,
    title: str,
    release_date: datetime,
    page_id: str,
    log=None
):
    uid = _event_uid(page_id)
    reminder_day = release_date - timedelta(days=1)

    if _event_exists_by_uid(uid):
        if log:
            log(f"📅 Rappel déjà existant (UID) : {title}", "info")
        return

    if _event_exists_by_title_and_day(title, reminder_day):
        if log:
            log(f"📅 Rappel déjà existant (ancien event) : {title}", "info")
        return

    event = {
        "summary": f"🎬 Sortie demain : {title}",
        "start": {"date": reminder_day.strftime("%Y-%m-%d")},
        "end": {"date": reminder_day.strftime("%Y-%m-%d")},
        "extendedProperties": {
            "private": {"notion_uid": uid}
        }
    }

    calendar_service.events().insert(
        calendarId=CALENDAR_ID,
        body=event
    ).execute()

    if log:
        log(f"📅 Rappel créé : {title}", "success")


def sync_future_releases(pages, get_title, get_release_date, log=None):
    now = datetime.now()

    for page in pages:
        title = get_title(page)
        release = get_release_date(page)

        if not title or not release or release <= now:
            continue

        if log:
            log(f"📅 Sync calendrier : {title}", "info")

        create_release_reminder(
            title=title,
            release_date=release,
            page_id=page["id"],
            log=log
        )
