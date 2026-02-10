"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for testing."""
    return '''
class UserService:
    """Service for user operations."""

    def __init__(self, db):
        self.db = db

    def login(self, username: str, password: str) -> bool:
        """Authenticate user."""
        user = self.db.find_user(username)
        return check_password(user, password)

    def logout(self, user_id: int) -> None:
        """Log out user."""
        self.db.clear_session(user_id)


def check_password(user, password: str) -> bool:
    """Verify password hash."""
    import hashlib
    return user.password_hash == hashlib.sha256(password.encode()).hexdigest()
'''


@pytest.fixture
def sample_php_code() -> str:
    """Sample PHP code for testing."""
    return '''<?php
namespace App\\Service;

use App\\Model\\User;
use App\\Repository\\UserRepository;

class UserService {
    private UserRepository $repository;

    public function __construct(UserRepository $repository) {
        $this->repository = $repository;
    }

    public function authenticate(string $username, string $password): ?User {
        $user = $this->repository->findByUsername($username);
        if ($user && password_verify($password, $user->getPasswordHash())) {
            return $user;
        }
        return null;
    }
}
'''
