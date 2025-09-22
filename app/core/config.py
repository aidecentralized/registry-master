import os
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel


class Settings(BaseModel):
    """Application configuration sourced from environment variables."""

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "registry_master"
    mongodb_collection: str = "registry_master"
    admin_token: str = "admin-secret-token"
    port: int = 8000
    
    # Kafka configuration
    kafka_bootstrap_servers: str = "34.229.1.253:9092"
    kafka_topic: str = "demo-topic"
    kafka_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        """Instantiate settings pulling values from the OS environment."""
        return cls(
            mongodb_uri=os.getenv("MONGODB_URI", cls.model_fields["mongodb_uri"].default),
            mongodb_database=os.getenv("MONGODB_DATABASE", cls.model_fields["mongodb_database"].default),
            mongodb_collection=os.getenv("MONGODB_COLLECTION", cls.model_fields["mongodb_collection"].default),
            admin_token=os.getenv("ADMIN_TOKEN", cls.model_fields["admin_token"].default),
            port=int(os.getenv("PORT", cls.model_fields["port"].default)),
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", cls.model_fields["kafka_bootstrap_servers"].default),
            kafka_topic=os.getenv("KAFKA_TOPIC", cls.model_fields["kafka_topic"].default),
            kafka_enabled=os.getenv("KAFKA_ENABLED", "true").lower() == "true",
        )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings.from_env()
