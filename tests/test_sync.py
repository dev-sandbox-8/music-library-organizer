import importlib.util
import os
from pathlib import Path
import json

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / 'update-mp3-metadata.py'

spec = importlib.util.spec_from_file_location('update_mp3_module', str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeAudio:
    def __init__(self, path, initial=None):
        self._path = path
        self._meta = {} if initial is None else dict(initial)

    def get(self, key, default=None):
        # mimic mutagen returning lists
        if key in self._meta:
            return [self._meta.get(key)]
        if default is not None:
            return default
        return [None]

    def __getitem__(self, key):
        # support audio['artist'] style access returning a list
        return [self._meta.get(key)]

    def __setitem__(self, key, value):
        # allow setting a value (string)
        self._meta[key] = value

    def __contains__(self, key):
        return key in self._meta

    def save(self):
        # no-op for fake
        return


@pytest.fixture(autouse=True)
def patch_mp3(monkeypatch, tmp_path):
    # Patch module.MP3 to return our FakeAudio
    def _fake_mp3(path, ID3=None):
        return FakeAudio(path)

    monkeypatch.setattr(module, 'MP3', _fake_mp3)
    # Patch acoustid.match to return empty generator
    monkeypatch.setattr(module.acoustid, 'match', lambda *a, **k: [])
    yield


def test_sync_metadata_and_rename_preserves_content_and_logs(tmp_path, monkeypatch):
    # Create a fake mp3 file (content is arbitrary bytes) with a generic name
    src = tmp_path / 'track01.mp3'
    src.write_bytes(b'FAKE_MP3_DATA')

    # Compute checksum before
    before = module.compute_checksum(str(src))

    # Prepare logger
    log_file = tmp_path / 'changes.json'
    logger = module.ChangeLogger(str(log_file))

    # Ensure filename parsing will return usable metadata for this test
    monkeypatch.setattr(module, 'parse_filename', lambda path: {'albumartist': 'Artist', 'album': 'Album', 'title': 'Song'})

    # Run sync (not dry-run)
    success = module.sync_metadata_and_rename(str(src), dry_run=False, logger=logger)
    assert success is True

    # Find renamed file (albumartist used - from filename it should be 'Artist')
    expected_name = 'Artist - Album - Song.mp3'
    expected_path = tmp_path / expected_name
    assert expected_path.exists()

    # Check checksum unchanged
    after = module.compute_checksum(str(expected_path))
    assert before == after

    # Logger should have one change
    assert len(logger.changes) == 1
    change = logger.changes[0]
    assert change['original_path'].endswith('track01.mp3')
    assert change['new_path'].endswith(expected_name)

    # Save and load log to confirm valid JSON
    logger.save()
    data = json.loads(log_file.read_text())
    assert isinstance(data, list)
    assert data[0]['original_path']
