"""Checks on the UI text. They run without Home Assistant."""

import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "custom_components" / "monoprice_8zone"


def test_translations_match_strings():
    # HA reads translations/en.json for a custom integration, and hassfest checks strings.json too.
    strings = json.loads((FOLDER / "strings.json").read_text(encoding="utf-8"))
    assert json.loads((FOLDER / "translations" / "en.json").read_text(encoding="utf-8")) == strings


def test_port_in_use_says_to_restart():
    # The built-in Monoprice integration lets go of the port only when HA restarts (PROTOCOL.md).
    strings = json.loads((FOLDER / "strings.json").read_text(encoding="utf-8"))
    assert "restart Home Assistant" in strings["config"]["error"]["port_in_use"]
    assert "restart Home Assistant" in strings["exceptions"]["port_in_use"]["message"]
