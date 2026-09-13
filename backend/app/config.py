from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Vault
    vault_jwt_secret: str
    vault_jwt_expire_minutes: int = 1440
    vault_database_url: str = "sqlite:///./vault.db"
    vault_cors_origins: str = "http://localhost:3000"

    # TMDB
    tmdb_api_read_token: str
    tmdb_image_base: str = "https://image.tmdb.org/t/p"

    # qBittorrent
    qbittorrent_url: str
    qbittorrent_username: str
    qbittorrent_password: str
    qbittorrent_category_movies: str = "vault-movies"
    qbittorrent_category_tv: str = "vault-tv"

    # Jellyfin
    jellyfin_url: str
    jellyfin_api_key: str
    jellyfin_client_name: str = "Vault"
    jellyfin_device_name: str = "vault-backend"
    jellyfin_device_id: str = "vault-backend-001"
    jellyfin_version: str = "1.0.0"
    # Jellyfin reports PinFile paths relative to its own filesystem view
    # (jellyfin_container_config_path); we need to translate that to where
    # the same volume is mounted read-only inside this container.
    jellyfin_container_config_path: str = "/config"
    jellyfin_config_mount_path: str = "/jellyfin-config"

    # Media paths — must be the same absolute path across the qbittorrent
    # and vault-backend containers (via the shared media-downloads volume),
    # since qBittorrent reports file locations that vault-backend's
    # organizer then has to read directly off disk.
    downloads_save_path: str = "/data/downloads"
    media_movies_path: str = "/data/media/movies"
    media_tv_path: str = "/data/media/tv"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.vault_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
