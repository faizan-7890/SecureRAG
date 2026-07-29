"""Test bootstrap for Windows environments that block uuid-utils' native extension."""

import sys
import types
from uuid import uuid4

uuid_utils = types.ModuleType("uuid_utils")
compat = types.ModuleType("uuid_utils.compat")
compat.uuid7 = uuid4
uuid_utils.compat = compat
sys.modules["uuid_utils"] = uuid_utils
sys.modules["uuid_utils.compat"] = compat
