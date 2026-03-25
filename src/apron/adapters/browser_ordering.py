from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class GroceryOrder:
    items_requested: list[str]
    items_added: list[str]
    store: str
    status: str  # "cart_ready" | "ordered" | "failed"
    summary: str
    cart_url: str | None = None


class BrowserOrderingAdapter:
    """Uses browser-use to order groceries from online stores."""

    def __init__(
        self,
        model: str = "openai/gpt-4o",
        store: str = "https://tienda.mercadona.es",
        email: str = "",
        password: str = "",
        on_step: Callable[[str, str, int], Any] | None = None,
    ) -> None:
        self._model = model
        self._store = store
        self._email = email
        self._password = password
        self._on_step = on_step  # callback(screenshot_b64, description, step_number)

    async def add_to_cart(
        self, items: list[str], store: str | None = None
    ) -> GroceryOrder:
        """Navigate to a grocery store website, log in, and add items to cart."""
        from browser_use import Agent
        from browser_use.browser.profile import BrowserProfile
        from browser_use.llm.litellm.chat import ChatLiteLLM

        target_store = store or self._store
        llm = ChatLiteLLM(model=self._model)
        items_str = ", ".join(items)

        # Build login instructions
        login_block = ""
        sensitive_data = {}
        if self._email and self._password:
            sensitive_data = {
                "x_email": self._email,
                "x_password": self._password,
            }
            login_block = (
                "FIRST, log in to the store:\n"
                "1. Look for a login/account button (e.g. 'Iniciar sesión', 'Mi cuenta', user icon)\n"
                "2. Click it\n"
                "3. Enter the email: x_email\n"
                "4. Enter the password: x_password\n"
                "5. Submit the login form and wait for it to complete\n\n"
            )

        task = (
            f"Go to {target_store} and wait for the page to fully load.\n\n"
            f"IMPORTANT: This is a Spanish grocery store. The entire website is in Spanish. "
            f"You MUST translate all search terms to Spanish before searching. "
            f"For example: eggs → huevos, milk → leche, bread → pan, chicken → pollo, "
            f"butter → mantequilla, cheese → queso, rice → arroz.\n\n"
            f"If a cookie consent banner appears, accept it.\n"
            f"If a postal code or location prompt appears, enter \"28001\" (Madrid) and confirm.\n\n"
            f"{login_block}"
            f"Then, for each of the following items, do these steps:\n"
            f"1. Find and click the search bar/icon\n"
            f"2. Translate the item name to Spanish\n"
            f"3. Type the SPANISH name and press Enter or click search\n"
            f"4. Wait for results to load\n"
            f"5. Click \"Añadir\" (Add) on the first relevant product to add it to the cart\n"
            f"6. Go back to search for the next item\n\n"
            f"Items to add (translate each to Spanish before searching): {items_str}\n\n"
            f"After adding ALL items, click on the cart icon to go to the cart page.\n\n"
            f"Once on the cart page, report:\n"
            f"- The current page URL\n"
            f"- Which items were successfully added\n"
            f"- Which items could not be found\n"
            f"- The total price shown in the cart"
        )

        # Step callback for live screenshot streaming
        async def on_step(state, output, step_num):
            if self._on_step and state:
                screenshot_b64 = state.get_screenshot() if hasattr(state, 'get_screenshot') else None
                description = ""
                if output and hasattr(output, 'next_goal'):
                    description = output.next_goal or ""
                if screenshot_b64:
                    try:
                        result = self._on_step(screenshot_b64, description, step_num)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.debug("Step callback error", exc_info=True)

        import os
        is_production = os.environ.get("ENVIRONMENT", "").lower() == "production"

        logger.info("Browser agent starting: adding %d items to %s (headless=%s)", len(items), target_store, is_production)
        try:
            browser_profile = BrowserProfile(
                headless=is_production,
                keep_alive=False,
            )
            agent = Agent(
                task=task,
                llm=llm,
                sensitive_data=sensitive_data if sensitive_data else None,
                browser_profile=browser_profile,
                register_new_step_callback=on_step,
                generate_gif=True,
            )
            result = await agent.run(max_steps=50)

            cart_url = self._extract_cart_url(result, target_store)

            summary = ""
            if result.final_result():
                summary = result.final_result()
            elif result.extracted_content():
                summary = "\n".join(result.extracted_content())
            else:
                summary = "Browser task completed."

            is_successful = result.is_successful()
            status = "cart_ready" if is_successful is not False else "failed"

            # Send final screenshot
            if self._on_step and result.history:
                last_state = result.history[-1] if result.history else None
                if last_state and hasattr(last_state, 'get_screenshot'):
                    final_ss = last_state.get_screenshot()
                    if final_ss:
                        try:
                            r = self._on_step(final_ss, "Cart ready — waiting for confirmation", -1)
                            if asyncio.iscoroutine(r):
                                await r
                        except Exception:
                            pass

            logger.info("Browser agent finished (status=%s, cart_url=%s): %s", status, cart_url, summary[:200])
            return GroceryOrder(
                items_requested=items,
                items_added=items if status == "cart_ready" else [],
                store=target_store,
                status=status,
                summary=summary,
                cart_url=cart_url,
            )
        except Exception as e:
            logger.exception("Browser agent failed")
            return GroceryOrder(
                items_requested=items,
                items_added=[],
                store=target_store,
                status="failed",
                summary=f"Failed to add items: {e}",
            )

    def _extract_cart_url(self, result, store: str) -> str | None:
        """Extract the cart page URL from browser history."""
        urls = result.urls()
        for url in reversed(urls):
            if url and any(kw in url.lower() for kw in ("cart", "cesta", "carrito")):
                return url
        for url in reversed(urls):
            if url:
                return url
        return None
