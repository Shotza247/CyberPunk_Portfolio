from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from mongodb_vector_test_ui.core.config import Settings


class PortfolioBadgeStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.mongodb_uri:
            raise ValueError("MONGODB_URI is required.")
        self.client = MongoClient(settings.mongodb_uri)
        self.collection: Collection = self.client[settings.mongodb_db][settings.badge_collection]

    def list_badges(self) -> list[dict]:
        documents = self.collection.find({}, projection={"_id": 0}).sort("created_at", -1)
        return [
            {
                **document,
                "created_at": document["created_at"].isoformat()
                if isinstance(document.get("created_at"), datetime)
                else None,
            }
            for document in documents
        ]

    def create_badge(self, badge: dict[str, str]) -> dict:
        self.collection.create_index("url", unique=True)
        document = {
            "id": uuid4().hex,
            **badge,
            "created_at": datetime.now(UTC),
        }
        try:
            self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError("That credential link has already been added.") from exc
        document["created_at"] = document["created_at"].isoformat()
        return document

    def delete_badge(self, badge_id: str) -> bool:
        result = self.collection.delete_one({"id": badge_id})
        return result.deleted_count == 1
