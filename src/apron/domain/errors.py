class DomainError(Exception):
    """Base exception for domain rule violations."""


class InvalidConversationStateError(DomainError):
    """Raised when a transition is not allowed."""


class BudgetExceededError(DomainError):
    """Raised when generated meal plan exceeds budget."""
