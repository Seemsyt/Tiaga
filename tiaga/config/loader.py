from pathlib import Path
from typing import Any
from tomli import TOMLDecodeError,load
from .config import Config
from platformdirs import user_config_dir
import logging
from tiaga.utils.erors import ConfigError
logger = logging.getLogger(__name__)
CONFIG_FILE_NAME =  'config.toml'
AGENT_MD_FILE = "AGENT.md"

def get_config_dir()->Path:

    return Path(user_config_dir("seems-tiaga"))



def get_data_dir()->Path:
    return Path(user_config_dir("seems-tiaga"))

def get_system_config_path()->Path:
    return get_config_dir()/CONFIG_FILE_NAME

def _parse_toml(path:Path):
    try:
        with open(path,'rb') as f:
            return load(f)
    except TOMLDecodeError as e:
        raise ConfigError(f"Invalid Toml error in {e} in path {path}") from e
    except (OSError,IOError) as e:
        raise ConfigError(f"Invalid Toml error in {e} in path {path}") from e

def _get_project_config(cwd:Path)->Path|None:
    current = cwd.resolve()
    agent_dir = current/'.seems-tiaga'

    if agent_dir.is_dir():
        config_file = agent_dir/CONFIG_FILE_NAME

        if config_file.is_file():
            return config_file
    return None
    
def _get_agent_md_file(cwd:Path)->str|None:
    current = cwd.resolve()


    if current.is_dir():
        agend_md_file = current/AGENT_MD_FILE

        if agend_md_file.is_file():
            content = agend_md_file.read_text(encoding="utf-8")
            return content
    return None
def _merge_dicts(base:dict[str,Any],overide:dict[str,Any])->dict[str,Any]:
    result = base.copy()
    for key,value in overide.items():
        if key in result and isinstance(result[key],dict) and  isinstance(value,dict):
            result[key] = _merge_dicts(result[key],value)
        else :
            result[key] = value
    return result

def _format_toml_value(value:Any)->str:
    if isinstance(value,bool):
        return "true" if value else "false"
    if isinstance(value,(int,float)):
        return str(value)
    if isinstance(value,str):
        escaped = value.replace("\\","\\\\").replace('"','\\"')
        return f'"{escaped}"'
    if isinstance(value,list):
        inner = ", ".join(_format_toml_value(item) for item in value)
        return f"[{inner}]"
    raise ConfigError(f"Unsupported TOML value type: {type(value).__name__}")

def _dict_to_toml(data:dict[str,Any],prefix:str|None = None)->str:
    lines:list[str] = []
    nested_items:list[tuple[str,dict[str,Any]]] = []

    for key,value in data.items():
        if isinstance(value,dict):
            nested_items.append((key,value))
            continue
        lines.append(f"{key} = {_format_toml_value(value)}")

    for key,child in nested_items:
        table_name = f"{prefix}.{key}" if prefix else key
        child_body = _dict_to_toml(child,prefix=table_name).strip()
        if not child_body:
            continue
        if lines:
            lines.append("")
        lines.append(f"[{table_name}]")
        lines.append(child_body)

    return "\n".join(lines).rstrip() + "\n"

def update_system_config(values:dict[str,Any])->Path:
    return _update_config_at_path(get_system_config_path(),values)

def _update_config_at_path(path:Path,values:dict[str,Any])->Path:
    path.parent.mkdir(parents=True,exist_ok=True)
    current:dict[str,Any] = {}
    if path.is_file():
        current = _parse_toml(path)
    merged = _merge_dicts(current,values)
    path.write_text(_dict_to_toml(merged),encoding="utf-8")
    return path

def update_config(values:dict[str,Any],cwd:Path|None = None)->Path:
    system_path = get_system_config_path()
    try:
        return _update_config_at_path(system_path,values)
    except OSError:
        if cwd is None:
            raise
        project_path = cwd/".seems-tiaga"/CONFIG_FILE_NAME
        return _update_config_at_path(project_path,values)


def load_config(cwd:Path|None)-> Config:
    cwd = cwd or Path.cwd()

    system_path = get_system_config_path()
    
    config_dicts:dict[str,Any] = {}
    if system_path.is_file():
        try:
            config_dicts = _parse_toml(system_path)
        except ConfigError as e:
            raise ConfigError(
                "Invalid system config",
                config_file=str(system_path),
                cause=e,
            ) from e
    project_path = _get_project_config(cwd=cwd)

    if project_path:
        try:
            project_config_dict = _parse_toml(project_path)

            config_dicts = _merge_dicts(config_dicts,project_config_dict)

        except ConfigError as e:
            raise ConfigError(
                "Invalid project config",
                config_file=str(project_path),
                cause=e,
            ) from e

    if  "cwd" not in config_dicts :
        config_dicts["cwd"] = cwd

    if  "developer_instruction" not in config_dicts : 
       agent_md_content =  _get_agent_md_file(cwd)
       if agent_md_content:
           config_dicts["developer_instruction"] = agent_md_content
    try:
        config = Config(**config_dicts)
    except Exception as e:
        raise ConfigError(f"Invalid configuration {e}") from e
    errors = config.validate_config()
    if errors:
        raise ConfigError("Invalid configuration", details={"errors": errors})
    return config
