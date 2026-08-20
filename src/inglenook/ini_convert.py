from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass

import yaml

FLAG_IF_TRUTHY = frozenset({"jinja", "offline", "cache-prompt"})
PASSTHROUGH = (
    "flash-attn",
    "n-gpu-layers",
    "batch-size",
    "ubatch-size",
    "cache-type-k",
    "cache-type-v",
    "spec-type",
    "spec-draft-n-max",
    "spec-draft-n-min",
    "ctx-size",
    "n-predict",
    "temp",
    "top-k",
    "top-p",
    "min-p",
    "repeat-last-n",
    "repeat-penalty",
    "presence-penalty",
    "frequency-penalty",
    "dry-multiplier",
    "dry-base",
    "dry-allowed-length",
    "dry-penalty-last-n",
    "reasoning",
    "reasoning-budget",
    "reasoning-effort",
)
TRUTHY = frozenset({"1", "true", "on", "yes"})


@dataclass(frozen=True)
class IniModel:
    name: str
    model: str
    mmproj: str
    values: dict[str, str]


def parse_models_ini(text: str) -> list[IniModel]:
    parser = ConfigParser(interpolation=None)

    def keep_case(option: str) -> str:
        return option

    parser.optionxform = keep_case  # type: ignore[method-assign, assignment]
    parser.read_string(text)
    defaults = dict(parser["*"]) if parser.has_section("*") else {}
    models: list[IniModel] = []
    for section in parser.sections():
        if section == "*":
            continue
        merged = {**defaults, **dict(parser[section])}
        models.append(
            IniModel(
                name=section,
                model=merged.get("model", ""),
                mmproj=merged.get("mmproj", ""),
                values=merged,
            )
        )
    return models


def convert_models_ini(text: str) -> str:
    models = parse_models_ini(text)
    rendered: dict[str, object] = {
        "models": {model.name: _model_entry(model) for model in models},
        "routing": {
            "router": {
                "use": "group",
                "settings": {
                    "groups": {
                        "gpu-exclusive": {
                            "swap": True,
                            "exclusive": True,
                            "members": [model.name for model in models],
                        }
                    }
                },
            }
        },
    }
    return yaml.safe_dump(rendered, sort_keys=False)


def _model_entry(model: IniModel) -> dict[str, object]:
    parts = ["${llama_server}", "--port ${PORT}", "--host 127.0.0.1"]
    if model.model:
        parts.append(f"--model {model.model}")
    if model.mmproj:
        parts.append(f"--mmproj {model.mmproj}")
    for key in FLAG_IF_TRUTHY:
        if model.values.get(key, "").lower() in TRUTHY:
            parts.append(f"--{key}")
    for key in PASSTHROUGH:
        value = model.values.get(key)
        if value is None or value == "":
            continue
        parts.append(f"--{key} {value}")
    return {
        "cmd": " ".join(parts),
        "ttl": 600,
        "group": "gpu-exclusive",
    }
