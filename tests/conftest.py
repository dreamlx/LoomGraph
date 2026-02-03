"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for testing."""
    return '''
"""Sample module for testing."""

from typing import Optional
from hashlib import sha256


class UserService:
    """User authentication service."""

    def __init__(self, db_connection):
        self.db = db_connection

    def login(self, username: str, password: str) -> Optional[dict]:
        """Authenticate a user.

        Args:
            username: User's username
            password: User's password

        Returns:
            User dict if authenticated, None otherwise
        """
        hashed = sha256(password.encode()).hexdigest()
        return self.db.query("SELECT * FROM users WHERE username = ? AND password = ?", username, hashed)

    def logout(self, user_id: int) -> bool:
        """Log out a user."""
        return self.db.execute("DELETE FROM sessions WHERE user_id = ?", user_id)


def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email and "." in email
'''


@pytest.fixture
def sample_php_code() -> str:
    """Sample PHP code for testing."""
    return '''<?php
namespace App\\Service;

use App\\Model\\User;
use App\\Repository\\UserRepository;

/**
 * User authentication service.
 */
class UserService
{
    private UserRepository $userRepository;

    public function __construct(UserRepository $userRepository)
    {
        $this->userRepository = $userRepository;
    }

    /**
     * Authenticate a user.
     *
     * @param string $username
     * @param string $password
     * @return User|null
     */
    public function login(string $username, string $password): ?User
    {
        $user = $this->userRepository->findByUsername($username);
        if ($user && password_verify($password, $user->getPassword())) {
            return $user;
        }
        return null;
    }
}
'''
