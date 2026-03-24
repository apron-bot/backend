from enum import Enum


class ConversationState(str, Enum):
    ONBOARDING = "onboarding"
    IDLE = "idle"
    COOKING_MODE = "cooking_mode"
    ORDERING_MODE = "ordering_mode"
    ADJUSTING_PLAN = "adjusting_plan"


class CookingSkill(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TimeAvailability(str, Enum):
    QUICK = "quick"
    NORMAL = "normal"
    LEISURELY = "leisurely"


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class IngredientSource(str, Enum):
    PHOTO_PARSE = "photo_parse"
    MANUAL = "manual"
    VOICE = "voice"
    ORDER = "order"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    FAILED = "failed"
