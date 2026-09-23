"""Load a root .env file and resolve exact YAML environment placeholders."""
import os
import re
from pathlib import Path

import yaml

from runtime.errors import ValidationError


ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def visual_execution_config(explicit=None):
    """Optional machine configuration; no installation paths enter shared defaults."""
    config={'mode':os.environ.get('VISUAL_EXECUTION_MODE','auto')}
    for key,variable in [('home','VISUAL_EXECUTOR_HOME'),('python','VISUAL_EXECUTOR_PYTHON'),('knowledge_home','VISUAL_KNOWLEDGE_HOME')]:
        if os.environ.get(variable):config[key]=os.environ[variable]
    if 'home' not in config and os.environ.get('RENDER_DIRECTOR_HOME'):config['home']=os.environ['RENDER_DIRECTOR_HOME']
    config.update(explicit or {})
    return config


def _dotenv_value(raw, line_number):
    value = raw.strip()
    if not value:
        return ""
    if value[0] in "\"'":
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError as exc:
            raise ValidationError(f"Invalid quoted value in .env line {line_number}") from exc
        if not isinstance(parsed, str):
            raise ValidationError(f"Expected a string value in .env line {line_number}")
        return parsed
    value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
    return value


def load_dotenv(path):
    """Load missing process variables from path without overriding caller settings."""
    path = Path(path)
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValidationError(f"Cannot read environment file: {path}") from exc
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not ENV_NAME.fullmatch(key):
            raise ValidationError(f"Invalid assignment in .env line {number}")
        os.environ.setdefault(key, _dotenv_value(value, number))


def _scalar(value, name):
    if value == "":
        return None
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ValidationError(f"Environment variable {name} is not a valid scalar") from exc
    if isinstance(parsed, (dict, list)):
        raise ValidationError(f"Environment variable {name} must be a scalar")
    return parsed


def resolve_environment(value):
    """Resolve ${NAME} values recursively; partial or missing references are rejected."""
    if isinstance(value, dict):
        return {key: resolve_environment(child) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_environment(child) for child in value]
    if not isinstance(value, str) or "${" not in value:
        return value
    match = ENV_REFERENCE.fullmatch(value)
    if not match:
        raise ValidationError("Environment placeholders must occupy the complete YAML value")
    name = match.group(1)
    if name not in os.environ:
        raise ValidationError(f"Environment is not configured: missing variable {name}")
    return _scalar(os.environ[name], name)
