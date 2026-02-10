"""Integration test fixtures.

Requires PostgreSQL with pgvector running on localhost:5433
Start with: docker run -d --name loomgraph-pg -e POSTGRES_USER=loomgraph \
  -e POSTGRES_PASSWORD=loomgraph_dev -e POSTGRES_DB=loomgraph \
  -p 5433:5432 pgvector/pgvector:pg16
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator, Generator

import pytest

if TYPE_CHECKING:
    from lightrag import LightRAG

# Database connection settings
DB_HOST = os.getenv("LOOMGRAPH_DB_HOST", "localhost")
DB_PORT = int(os.getenv("LOOMGRAPH_DB_PORT", "5433"))
DB_USER = os.getenv("LOOMGRAPH_DB_USER", "loomgraph")
DB_PASSWORD = os.getenv("LOOMGRAPH_DB_PASSWORD", "loomgraph_dev")
DB_NAME = os.getenv("LOOMGRAPH_DB_NAME", "loomgraph")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_connection_string() -> str:
    """PostgreSQL connection string."""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


@pytest.fixture
def temp_python_file(tmp_path: Path) -> Path:
    """Create a temporary Python file for testing."""
    code = '''"""User authentication module."""

import hashlib
from typing import Optional

class UserService:
    """Service for user authentication."""

    def __init__(self, db):
        """Initialize with database connection."""
        self.db = db

    def login(self, username: str, password: str) -> bool:
        """Authenticate user with username and password."""
        user = self.db.find_user(username)
        if user is None:
            return False
        return self._verify_password(user, password)

    def _verify_password(self, user, password: str) -> bool:
        """Verify password hash."""
        hashed = hashlib.sha256(password.encode()).hexdigest()
        return user.password_hash == hashed


def create_user(name: str, email: str) -> dict:
    """Create a new user."""
    return {"name": name, "email": email}
'''
    file_path = tmp_path / "auth_service.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def temp_php_file(tmp_path: Path) -> Path:
    """Create a temporary PHP file for testing."""
    code = '''<?php
namespace App\\Service;

use App\\Model\\User;
use App\\Repository\\UserRepository;

/**
 * User authentication service.
 */
class AuthService {
    private UserRepository $repository;

    public function __construct(UserRepository $repository) {
        $this->repository = $repository;
    }

    /**
     * Authenticate user by credentials.
     */
    public function authenticate(string $username, string $password): ?User {
        $user = $this->repository->findByUsername($username);
        if ($user && password_verify($password, $user->getPasswordHash())) {
            return $user;
        }
        return null;
    }
}
'''
    file_path = tmp_path / "AuthService.php"
    file_path.write_text(code)
    return file_path


class MockEmbeddingClient:
    """Mock embedding client for testing without GPU."""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self._call_count = 0

    async def embed(self, texts: list[str]) -> "MockEmbedResult":
        """Return deterministic mock embeddings."""
        import hashlib

        embeddings = []
        for text in texts:
            # Generate deterministic embedding from text hash
            hash_bytes = hashlib.sha256(text.encode()).digest()
            # Expand to dimension size with repeating pattern
            values = []
            for i in range(self.dimension):
                byte_idx = i % len(hash_bytes)
                # Normalize to [-1, 1]
                values.append((hash_bytes[byte_idx] / 255.0) * 2 - 1)
            embeddings.append(values)

        self._call_count += 1
        return MockEmbedResult(embeddings=embeddings)


class MockEmbedResult:
    """Mock embedding result."""

    def __init__(self, embeddings: list[list[float]]):
        self.embeddings = embeddings


@pytest.fixture
def mock_embedding_client() -> MockEmbeddingClient:
    """Provide mock embedding client."""
    return MockEmbeddingClient(dimension=768)
