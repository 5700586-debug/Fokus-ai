from providers.file_storage import TelegramFileStorageProvider, get_file_storage_provider


def test_register_returns_file_reference():
    provider = TelegramFileStorageProvider()

    ref = provider.register("file123", owner_id=1, category="cash_shift_photo")

    assert ref.file_id == "file123"
    assert ref.owner_id == 1
    assert ref.category == "cash_shift_photo"
    assert ref.created_at


def test_retention_days_for_new_categories():
    provider = TelegramFileStorageProvider()

    assert provider.retention_days("cash_shift_photo") == 180
    assert provider.retention_days("inventory_snapshot_photo") == 180


def test_retention_days_unknown_category_is_none():
    provider = TelegramFileStorageProvider()
    assert provider.retention_days("unknown_category") is None


def test_get_file_storage_provider_returns_telegram_provider():
    assert isinstance(get_file_storage_provider(), TelegramFileStorageProvider)
