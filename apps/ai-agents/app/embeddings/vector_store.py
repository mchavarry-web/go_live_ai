"""Low-level pgvector operations via SQLAlchemy.

Provides direct SQLAlchemy-based vector operations for cases where
the LangChain PGVector wrapper is insufficient. Supports cosine
similarity search, category filtering, and bulk operations.

Status: NOT_IMPLEMENTED
Planned for: Batch imports, category filtering, or direct SQL
when the LangChain wrapper does not meet requirements.
"""
