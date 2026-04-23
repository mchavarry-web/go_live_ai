"""Abstract base repository for database operations.

Provides common CRUD operations that concrete repositories inherit.
All database queries go through repositories — services never access
SQLAlchemy sessions directly.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(ABC, Generic[ModelType]):
    """Abstract base repository with common CRUD operations.

    Subclasses must define the ``model`` class attribute pointing to
    the SQLAlchemy model they manage.

    Attributes:
        _session: The async database session for executing queries.

    Args:
        session: An async SQLAlchemy session.
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with a database session.

        Args:
            session: An async SQLAlchemy session.
        """
        self._session = session

    async def get_by_id(self, entity_id: str) -> ModelType | None:
        """Retrieve an entity by its primary key.

        Args:
            entity_id: The primary key value.

        Returns:
            The entity if found, None otherwise.
        """
        return await self._session.get(self.model, entity_id)

    async def create(self, entity: ModelType) -> ModelType:
        """Persist a new entity to the database.

        Args:
            entity: The SQLAlchemy model instance to persist.

        Returns:
            The persisted entity with generated fields populated.
        """
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        """Delete an entity from the database.

        Args:
            entity: The SQLAlchemy model instance to delete.
        """
        await self._session.delete(entity)
        await self._session.commit()

    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> list[ModelType]:
        """Find all entities belonging to a user.

        Args:
            user_id: The user's unique identifier.

        Returns:
            List of entities for the specified user.
        """
        ...
