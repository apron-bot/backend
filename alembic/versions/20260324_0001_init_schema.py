"""initial apron schema

Revision ID: 20260324_0001
Revises:
Create Date: 2026-03-24
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260324_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            household_size INT DEFAULT 2,
            allergies JSONB DEFAULT '[]',
            dietary_preferences JSONB DEFAULT '[]',
            taste_profiles JSONB DEFAULT '[]',
            weekly_budget DECIMAL(10,2) DEFAULT 100.00,
            preferred_cuisines JSONB DEFAULT '[]',
            cooking_skill VARCHAR(20) DEFAULT 'intermediate',
            time_available VARCHAR(20) DEFAULT 'normal',
            disliked_ingredients JSONB DEFAULT '[]',
            conversation_state VARCHAR(30) DEFAULT 'onboarding',
            onboarding_step INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE inventory (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            quantity DECIMAL(10,2) NOT NULL,
            unit VARCHAR(20) NOT NULL,
            expiry_date DATE,
            date_added TIMESTAMPTZ DEFAULT NOW(),
            source VARCHAR(20) NOT NULL,
            UNIQUE(user_id, name)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE recipes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            cuisine VARCHAR(50),
            cook_time_minutes INT,
            difficulty VARCHAR(20),
            servings INT,
            ingredients JSONB NOT NULL,
            steps JSONB NOT NULL,
            image_url TEXT,
            tags JSONB DEFAULT '[]'
        );
        """
    )
    op.execute(
        """
        CREATE TABLE user_favorite_recipes (
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            recipe_id UUID REFERENCES recipes(id) ON DELETE CASCADE,
            rating INT,
            PRIMARY KEY (user_id, recipe_id)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE meal_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            week_start DATE NOT NULL,
            meals JSONB NOT NULL,
            total_estimated_cost DECIMAL(10,2),
            missing_ingredients JSONB DEFAULT '[]',
            confirmed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            items JSONB NOT NULL,
            source VARCHAR(50) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            total_price DECIMAL(10,2),
            estimated_delivery_minutes INT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE shopping_list (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            quantity DECIMAL(10,2) NOT NULL,
            unit VARCHAR(20) NOT NULL,
            added_by VARCHAR(20) NOT NULL,
            purchased BOOLEAN DEFAULT FALSE
        );
        """
    )
    op.execute("CREATE INDEX idx_inventory_user ON inventory(user_id);")
    op.execute("CREATE INDEX idx_inventory_expiry ON inventory(user_id, expiry_date);")
    op.execute("CREATE INDEX idx_meal_plans_user_week ON meal_plans(user_id, week_start);")
    op.execute("CREATE INDEX idx_orders_user ON orders(user_id);")
    op.execute("CREATE INDEX idx_shopping_user ON shopping_list(user_id, purchased);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shopping_list;")
    op.execute("DROP TABLE IF EXISTS orders;")
    op.execute("DROP TABLE IF EXISTS meal_plans;")
    op.execute("DROP TABLE IF EXISTS user_favorite_recipes;")
    op.execute("DROP TABLE IF EXISTS recipes;")
    op.execute("DROP TABLE IF EXISTS inventory;")
    op.execute("DROP TABLE IF EXISTS users;")
