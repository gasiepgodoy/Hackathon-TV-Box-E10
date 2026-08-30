"""
Configuração central do backend.
Lê variáveis de ambiente (ou um arquivo .env na pasta backend/) e expõe
um objeto único `settings` usado pelo resto da aplicação.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # InfluxDB
    influx_url: str = os.getenv("INFLUX_URL", "http://localhost:8086")
    influx_token: str = os.getenv("INFLUX_TOKEN", "")
    influx_org: str = os.getenv("INFLUX_ORG", "")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "sensores")

    # Banco local de cadastro de sensores
    sqlite_path: str = os.getenv("SQLITE_PATH", "./gateway.db")

    # Servidor
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # CORS
    cors_origins: list[str] = (
        ["*"] if os.getenv("CORS_ORIGINS", "*") == "*"
        else [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    )


settings = Settings()
