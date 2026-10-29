"""Leave out the HA tests when Home Assistant isn't installed, so a bare pytest works on Windows."""

import importlib.util

collect_ignore = ["ha"] if importlib.util.find_spec("homeassistant") is None else []
