from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GroceryOrder:
    items_requested: list[str]
    items_added: list[str]
    store: str
    status: str  # "cart_ready" | "ordered" | "failed"
    summary: str


class BrowserOrderingAdapter:
    """Uses browser-use to order groceries from online stores."""

    def __init__(self, model: str = "openai/gpt-4o-mini") -> None:
        self._model = model

    async def add_to_cart(
        self, items: list[str], store: str = "mercadona.com"
    ) -> GroceryOrder:
        """Navigate to a grocery store website and add items to cart."""
        from browser_use import Agent
        from browser_use.llm.litellm.chat import ChatLiteLLM

        llm = ChatLiteLLM(model=self._model)
        items_str = ", ".join(items)
        task = (
            f"Go to {store}. For each of these items, search for it and add it to the cart: "
            f"{items_str}. "
            f"After adding all items, go to the cart and report what was added and the total price."
        )

        logger.info("Browser agent starting: adding %d items to %s", len(items), store)
        try:
            agent = Agent(task=task, llm=llm)
            result = await agent.run()
            summary = str(result) if result else "Browser task completed."
            logger.info("Browser agent finished: %s", summary[:200])
            return GroceryOrder(
                items_requested=items,
                items_added=items,
                store=store,
                status="cart_ready",
                summary=summary,
            )
        except Exception as e:
            logger.exception("Browser agent failed")
            return GroceryOrder(
                items_requested=items,
                items_added=[],
                store=store,
                status="failed",
                summary=f"Failed to add items: {e}",
            )
