from celery import shared_task


@shared_task(name="bexio.sync_konten")  # type: ignore[untyped-decorator]
def sync_konten_task() -> int:
    from apps.bexio.sync import sync_konten

    return sync_konten()


@shared_task(name="bexio.sync_lieferantenrechnungen")  # type: ignore[untyped-decorator]
def sync_lieferantenrechnungen_task() -> int:
    from apps.bexio.sync import sync_lieferantenrechnungen

    return sync_lieferantenrechnungen()
