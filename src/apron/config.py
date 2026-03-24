from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://apron:apron@localhost:5432/apron"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = "whatsapp:+14155238886"

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_text_model: str = "gemini-3.1-flash-lite-preview"
    gemini_vision_model: str = "gemini-2.5-flash"
    minimax_api_key: str = ""
    minimax_api_base: str = "https://api.minimax.io/anthropic/v1/messages"
    minimax_text_model: str = "minimax/MiniMax-M2.5"
    minimax_vision_model: str = "minimax/MiniMax-VL-01"

    openai_api_key: str = ""

    environment: str = "development"
    log_level: str = "INFO"
    llm_provider: str = "inmemory"
    messaging_provider: str = "inmemory"
    adk_model_provider: str = "gemini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
