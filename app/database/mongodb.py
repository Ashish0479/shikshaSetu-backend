import logging
from typing import Dict, Any, List, Optional
import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import settings

logger = logging.getLogger(__name__)

class MongoDBClient:
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db = None
        self.is_connected = False
        self._in_memory_store: Dict[str, Dict[str, Any]] = {
            "datasets": {},
            "teacher_records": {},
            "quality_reports": {},
            "validation_errors": {},
            "standardization_logs": {},
        }
        self.connect()

    def connect(self):
        """Attempts to connect to MongoDB with a short timeout.
        Falls back seamlessly to in-memory storage if MongoDB is not running locally."""
        try:
            self.client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
                connectTimeoutMS=settings.MONGODB_TIMEOUT_MS,
            )
            # Check server availability
            self.client.admin.command('ping')
            self.db = self.client[settings.DATABASE_NAME]
            self.is_connected = True
            logger.info(f"Connected to MongoDB at {settings.MONGODB_URI}, Database: {settings.DATABASE_NAME}")
            self._create_indexes()
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            self.is_connected = False
            self.db = None
            logger.warning(
                f"MongoDB connection failed ({e}). Operating in resilient In-Memory Cache mode. "
                f"All functionalities remain fully operational."
            )

    def _create_indexes(self):
        """Creates required indexes on collections for fast queries."""
        if not self.is_connected or self.db is None:
            return
        try:
            self.db.datasets.create_index([("dataset_id", pymongo.ASCENDING)], unique=True)
            self.db.datasets.create_index([("created_at", pymongo.DESCENDING)])
            
            self.db.teacher_records.create_index([("dataset_id", pymongo.ASCENDING), ("row_number", pymongo.ASCENDING)])
            self.db.teacher_records.create_index([("dataset_id", pymongo.ASCENDING), ("Teacher_ID", pymongo.ASCENDING)])
            
            self.db.quality_reports.create_index([("dataset_id", pymongo.ASCENDING)], unique=True)
            self.db.validation_errors.create_index([("dataset_id", pymongo.ASCENDING), ("severity", pymongo.ASCENDING)])
            self.db.standardization_logs.create_index([("dataset_id", pymongo.ASCENDING), ("column", pymongo.ASCENDING)])
            logger.info("MongoDB indexes verified.")
        except Exception as e:
            logger.error(f"Failed to create MongoDB indexes: {e}")

    # ---------------- Datasets ----------------
    def insert_dataset(self, metadata: Dict[str, Any]):
        dataset_id = metadata["dataset_id"]
        if self.is_connected and self.db is not None:
            self.db.datasets.update_one({"dataset_id": dataset_id}, {"$set": metadata}, upsert=True)
        else:
            self._in_memory_store["datasets"][dataset_id] = metadata

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            doc = self.db.datasets.find_one({"dataset_id": dataset_id}, {"_id": 0})
            return doc
        return self._in_memory_store["datasets"].get(dataset_id)

    def list_datasets(self) -> List[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            cursor = self.db.datasets.find({}, {"_id": 0}).sort("created_at", -1)
            return list(cursor)
        items = list(self._in_memory_store["datasets"].values())
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items

    # ---------------- Teacher Records ----------------
    def insert_teacher_records(self, dataset_id: str, raw_records: List[Dict[str, Any]], clean_records: List[Dict[str, Any]]):
        doc = {
            "dataset_id": dataset_id,
            "raw_records": raw_records,
            "clean_records": clean_records
        }
        if self.is_connected and self.db is not None:
            self.db.teacher_records.update_one({"dataset_id": dataset_id}, {"$set": doc}, upsert=True)
        else:
            self._in_memory_store["teacher_records"][dataset_id] = doc

    def get_teacher_records(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            return self.db.teacher_records.find_one({"dataset_id": dataset_id}, {"_id": 0})
        return self._in_memory_store["teacher_records"].get(dataset_id)

    # ---------------- Quality Reports ----------------
    def insert_quality_report(self, dataset_id: str, report: Dict[str, Any]):
        if self.is_connected and self.db is not None:
            self.db.quality_reports.update_one({"dataset_id": dataset_id}, {"$set": report}, upsert=True)
        else:
            self._in_memory_store["quality_reports"][dataset_id] = report

    def get_quality_report(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            return self.db.quality_reports.find_one({"dataset_id": dataset_id}, {"_id": 0})
        return self._in_memory_store["quality_reports"].get(dataset_id)

    # ---------------- Validation Errors ----------------
    def insert_validation_errors(self, dataset_id: str, errors: List[Dict[str, Any]]):
        doc = {"dataset_id": dataset_id, "errors": errors}
        if self.is_connected and self.db is not None:
            self.db.validation_errors.update_one({"dataset_id": dataset_id}, {"$set": doc}, upsert=True)
        else:
            self._in_memory_store["validation_errors"][dataset_id] = doc

    def get_validation_errors(self, dataset_id: str) -> List[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            doc = self.db.validation_errors.find_one({"dataset_id": dataset_id}, {"_id": 0})
            return doc.get("errors", []) if doc else []
        doc = self._in_memory_store["validation_errors"].get(dataset_id)
        return doc.get("errors", []) if doc else []

    # ---------------- Standardization Logs ----------------
    def insert_standardization_logs(self, dataset_id: str, logs: List[Dict[str, Any]], summary: List[Dict[str, Any]]):
        doc = {"dataset_id": dataset_id, "logs": logs, "summary": summary}
        if self.is_connected and self.db is not None:
            self.db.standardization_logs.update_one({"dataset_id": dataset_id}, {"$set": doc}, upsert=True)
        else:
            self._in_memory_store["standardization_logs"][dataset_id] = doc

    def get_standardization_logs(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            return self.db.standardization_logs.find_one({"dataset_id": dataset_id}, {"_id": 0})
        return self._in_memory_store["standardization_logs"].get(dataset_id)

db_client = MongoDBClient()
