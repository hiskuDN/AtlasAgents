"""Configuration management for AtlasAgents."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum

from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings


class ProviderType(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VLLM = "vllm"


class ModelProvider(BaseModel):
    type: ProviderType
    model: str
    url: Optional[str] = None
    api_key: Optional[str] = None

    class Config:
        extra = "allow"


class ModelConfig(BaseModel):
    default: str = "local_gemma"
    per_agent: Dict[str, str] = Field(default_factory=lambda: {
        "planner": "local_gemma",
        "spec_writer": "local_gemma",
        "coder": "local_qwen",
        "reviewer": "local_qwen"
    })
    providers: Dict[str, ModelProvider] = Field(default_factory=dict)


class TrustPolicy(BaseModel):
    default: str = "deny"
    allow: Dict[str, List[str]] = Field(default_factory=lambda: {
        "planner": ["fs.read", "git.branch.list"],
        "spec": ["fs.read", "fs.write.preview"],
        "coder": ["fs.write.preview", "git.branch.create", "git.diff"],
        "reviewer": ["git.diff", "fs.write.preview"]
    })
    require_approval: List[str] = Field(default_factory=lambda: [
        "*.write*", "git.*merge*", "git.*push*", "sql.write*"
    ])


class TelegramConfig(BaseModel):
    group_id: Optional[str] = None
    bot_token: Optional[str] = None


class LimitsConfig(BaseModel):
    max_files_per_patch: int = 20
    max_patch_kb: int = 256
    max_context_tokens: int = 100000
    timeout_seconds: int = 300


class Settings(BaseModel):
    models: ModelConfig = Field(default_factory=ModelConfig)
    trust: TrustPolicy = Field(default_factory=TrustPolicy)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    class Config:
        extra = "allow"


class MCPTransport(BaseModel):
    name: str
    type: str  # stdio, http
    cmd: Optional[List[str]] = None
    url: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class MCPConfig(BaseModel):
    transports: List[MCPTransport] = Field(default_factory=list)


class AtlasConfig:
    """Main configuration manager for AtlasAgents."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or self._get_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.settings_path = self.config_dir / "settings.json"
        self.mcp_config_path = Path.cwd() / "atlas.config.yaml"

        self._settings: Optional[Settings] = None
        self._mcp_config: Optional[MCPConfig] = None

    @staticmethod
    def _get_config_dir() -> Path:
        """Get the atlas configuration directory."""
        home = Path.home()
        return home / ".atlas"

    @property
    def settings(self) -> Settings:
        """Load settings lazily."""
        if self._settings is None:
            self._settings = self.load_settings()
        return self._settings

    @property
    def mcp_config(self) -> MCPConfig:
        """Load MCP config lazily."""
        if self._mcp_config is None:
            self._mcp_config = self.load_mcp_config()
        return self._mcp_config

    def load_settings(self) -> Settings:
        """Load settings from JSON file or create default."""
        if self.settings_path.exists():
            with open(self.settings_path) as f:
                data = json.load(f)
                return Settings(**data)
        else:
            # Create default settings
            settings = Settings()
            self.save_settings(settings)
            return settings

    def save_settings(self, settings: Settings) -> None:
        """Save settings to JSON file."""
        with open(self.settings_path, 'w') as f:
            json.dump(settings.dict(), f, indent=2)

    def load_mcp_config(self) -> MCPConfig:
        """Load MCP configuration from YAML file."""
        if self.mcp_config_path.exists():
            import yaml
            with open(self.mcp_config_path) as f:
                data = yaml.safe_load(f)
                return MCPConfig(**data.get('mcp', {}))
        return MCPConfig()

    def save_mcp_config(self, config: MCPConfig) -> None:
        """Save MCP configuration to YAML file."""
        import yaml
        data = {'mcp': config.dict()}
        with open(self.mcp_config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

    def get_model_provider(self, agent: str) -> ModelProvider:
        """Get model provider configuration for an agent."""
        model_id = self.settings.models.per_agent.get(agent, self.settings.models.default)
        provider = self.settings.models.providers.get(model_id)
        if not provider:
            raise ValueError(f"Model provider '{model_id}' not found in settings")
        return provider

    def is_tool_allowed(self, agent: str, tool: str) -> bool:
        """Check if a tool is allowed for an agent."""
        if self.settings.trust.default == "allow":
            return True

        allowed_tools = self.settings.trust.allow.get(agent, [])
        for pattern in allowed_tools:
            if self._match_pattern(tool, pattern):
                return True

        return False

    def requires_approval(self, tool: str) -> bool:
        """Check if a tool requires approval."""
        for pattern in self.settings.trust.require_approval:
            if self._match_pattern(tool, pattern):
                return True
        return False

    @staticmethod
    def _match_pattern(text: str, pattern: str) -> bool:
        """Simple pattern matching with wildcards."""
        import fnmatch
        return fnmatch.fnmatch(text, pattern)


# Singleton instance
_config_instance: Optional[AtlasConfig] = None


def get_config(config_dir: Optional[Path] = None) -> AtlasConfig:
    """Get or create the global config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = AtlasConfig(config_dir)
    return _config_instance