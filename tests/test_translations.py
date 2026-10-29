"""HA reads translations/en.json for a custom integration, and hassfest checks strings.json too, so the two must match."""

import json
from pathlib import Path


def test_translations_match_strings():
    folder = Path(__file__).resolve().parents[1] / "custom_components" / "monoprice_8zone"
    strings = json.loads((folder / "strings.json").read_text(encoding="utf-8"))
    assert json.loads((folder / "translations" / "en.json").read_text(encoding="utf-8")) == strings
