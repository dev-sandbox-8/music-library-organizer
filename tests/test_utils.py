import importlib.util
import os
from pathlib import Path
import hashlib

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / 'update-mp3-metadata.py'

spec = importlib.util.spec_from_file_location('update_mp3_module', str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_sanitize_and_parse_filename():
    s = 'Artist/Name: The? *Title*'
    sanitized = module.sanitize_filename(s)
    assert '/' not in sanitized
    assert ':' not in sanitized

    filename = 'Coldplay - Parachutes - Yellow.mp3'
    parsed = module.parse_filename(filename)
    assert parsed['albumartist'] == 'Coldplay'
    assert parsed['album'] == 'Parachutes'
    assert parsed['title'] == 'Yellow'


def test_compute_checksum(tmp_path):
    p = tmp_path / 'file.bin'
    data = b'hello world\n'
    p.write_bytes(data)
    # compute hash independently
    expected = hashlib.sha256(data).hexdigest()
    got = module.compute_checksum(str(p))
    assert got == expected
