from fritz_callhistory.config import Config, load, save


def test_load_without_existing_file_returns_defaults(tmp_path):
    config = load(tmp_path / "does-not-exist.toml")
    assert config == Config()


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    original = Config(
        address="192.168.178.1",
        username="admin",
        sync_interval_minutes=15,
        phonebook_ids=[0, 1],
        minimize_to_tray_on_close=True,
    )

    save(original, path)
    loaded = load(path)

    assert loaded == original


def test_minimize_to_tray_on_close_defaults_to_false():
    assert Config().minimize_to_tray_on_close is False


def test_empty_phonebook_ids_means_all_phonebooks():
    config = Config()
    assert config.resolved_phonebook_ids() is None


def test_explicit_phonebook_ids_are_returned():
    config = Config(phonebook_ids=[0])
    assert config.resolved_phonebook_ids() == [0]


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('address = "192.168.178.1"\nfuture_option = "x"\n')

    config = load(path)

    assert config.address == "192.168.178.1"
