import shlex
from typing import Any


from tiaga.config.config import Config
from tiaga.config.loader import update_config
from tiaga.ui.render import _get_console
console = _get_console()

class ConfigSetter:

    def __init__(self,config:Config):
        self.console = console
        self.config = config
        self.session_usage:dict[str,int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }
        self.usage_by_model:dict[str,dict[str,int]] = {}
    async def _handle_local_command(self,message:str)->bool:
        stripped = message.strip()
        if not stripped.startswith("/"):
            return False

        try:
            parts = shlex.split(stripped)
        except ValueError as e:
            console.print(f"[error]Invalid command:[/error] {e}")
            return True

        if not parts:
            return False

        command = parts[0].lower()
        if command in {"/help"}:
            self._print_config_help()
            return True

        if command in {"/model"}:
            if len(parts) == 1:
                self._show_model_usage()
                return True
            parts = ["/config", "model", " ".join(parts[1:])]
            command = "/config"

        if command not in {"/config", "/congig"}:
            return False

        if len(parts) == 1:
            self._print_config_help()
            return True

        action = parts[1].lower()
        if action in {"help", "-h", "--help"}:
            self._print_config_help()
            return True
        if action == "show":
            self._show_config()
            return True

        if len(parts) < 3:
            console.print("[error]Missing value.[/error] Use /config help")
            return True

        value = " ".join(parts[2:]).strip()
        if not value:
            console.print("[error]Value cannot be empty.[/error]")
            return True

        updates:dict[str,Any]
        if action in {"model", "model_name"}:
            self.config.model_name = value
            updates = {"model": {"name": value}}
            display_value = value
        elif action in {"base_url", "url", "baseurl"}:
            self.config.base_url = value
            updates = {"base_url": value}
            display_value = value
        elif action in {"api_key", "apikey", "key"}:
            self.config.api_key = value
            updates = {"api_key": value}
            display_value = self._mask_secret(value)
        else:
            console.print(f"[error]Unknown config key:[/error] {action}")
            self._print_config_help()
            return True

        try:
            path = update_config(updates,cwd=self.config.cwd)
        except Exception as e:
            console.print(f"[error]Failed to persist config:[/error] {e}")
            return True

        console.print(f"[success]Updated {action}[/success] -> {display_value}")
        console.print(f"[dim]Saved to {path}[/dim]")
        return True
    

    def _mask_secret(self,value:str|None)->str:
        if not value:
            return "(not set)"
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def _print_config_help(self)->None:
        console.print("[info]/config usage:[/info]")
        console.print("[dim]- /config show[/dim]")
        console.print("[dim]- /config model <model_name>[/dim]")
        console.print("[dim]- /config base_url <url>[/dim]")
        console.print("[dim]- /config api_key <key>[/dim]")
        console.print("[dim]- /model[/dim]")
        console.print("[dim]- /model <model_name>[/dim]")

    def _show_config(self)->None:
        console.print("[info]Current config:[/info]")
        console.print(f"[dim]model:[/dim] {self.config.model_name or '(not set)'}")
        console.print(f"[dim]base_url:[/dim] {self.config.base_url or '(not set)'}")
        console.print(f"[dim]api_key:[/dim] {self._mask_secret(self.config.api_key)}")

    def _show_model_usage(self)->None:
        usage = self.session_usage
        console.print("[info]Model usage:[/info]")
        console.print(f"[dim]model:[/dim] {self.config.model_name or '(not set)'}")
        console.print(f"[dim]prompt_tokens:[/dim] {usage.get('prompt_tokens', 0)}")
        console.print(f"[dim]completion_tokens:[/dim] {usage.get('completion_tokens', 0)}")
        console.print(f"[dim]total_tokens:[/dim] {usage.get('total_tokens', 0)}")
        console.print(f"[dim]cached_tokens:[/dim] {usage.get('cached_tokens', 0)}")
        if self.usage_by_model:
            console.print("[info]Per-model usage:[/info]")
            for model_name, model_usage in self.usage_by_model.items():
                console.print(
                    f"[dim]{model_name}[/dim] "
                    f"prompt={model_usage.get('prompt_tokens',0)} "
                    f"completion={model_usage.get('completion_tokens',0)} "
                    f"total={model_usage.get('total_tokens',0)} "
                    f"cached={model_usage.get('cached_tokens',0)}"
                )

    def _update_session_usage(self,usage_data:dict[str,Any]|None)->None:
        if not isinstance(usage_data,dict):
            return
        for key in self.session_usage:
            value = usage_data.get(key)
            if isinstance(value,int):
                self.session_usage[key] += value
        model_name = self.config.model_name or "(not set)"
        model_usage = self.usage_by_model.setdefault(
            model_name,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
            },
        )
        for key in model_usage:
            value = usage_data.get(key)
            if isinstance(value,int):
                model_usage[key] += value