"""Shopify order operations used by the support workflow."""

import re
from datetime import datetime
from decimal import Decimal

from storekeeper.domain import OrderFacts, ShopifyOrder
from storekeeper.shopify.client import ShopifyClient

ORDER_REFERENCE_PATTERN = re.compile(r"^#?\d{1,10}$")

LOOKUP_ORDER_QUERY = """
query LookupOrder($searchQuery: String!) {
  orders(first: 1, query: $searchQuery) {
    nodes {
      id
      name
      processedAt
      displayFulfillmentStatus
      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
    }
  }
}
"""


class OrderNotFoundError(LookupError):
    """Raised when Shopify has no order matching the supplied reference."""


class InvalidOrderReferenceError(ValueError):
    """Raised when a customer-supplied order reference is not '#' plus digits."""


def normalize_order_reference(raw_order_reference: str | None) -> str:
    """Accept '#1036' or '1036'; refuse everything else, including None.

    The reference ends up inside a Shopify search query, so this is an
    allowlist, not an escape function — ticket text that isn't a plain order
    number never reaches the query.
    """
    cleaned_reference = raw_order_reference.strip() if raw_order_reference else ""
    if not ORDER_REFERENCE_PATTERN.fullmatch(cleaned_reference):
        raise InvalidOrderReferenceError(
            f"Not a valid order reference: {raw_order_reference!r}. "
            "Expected '#' followed by digits, like #1036."
        )
    if cleaned_reference.startswith("#"):
        return cleaned_reference
    return f"#{cleaned_reference}"


def lookup_order(
    order_reference: str | None,
    client: ShopifyClient | None = None,
) -> ShopifyOrder:
    """Find an order by its Shopify name, such as #1001.

    Binds strictly: the reference must normalize to '#'+digits, and the
    returned order's name must equal it exactly — an action can never attach
    to an order the customer did not name.
    """
    normalized_reference = normalize_order_reference(order_reference)

    shopify_client = client if client is not None else ShopifyClient()
    data = shopify_client.graphql(
        LOOKUP_ORDER_QUERY,
        {"searchQuery": f"name:{normalized_reference}"},
    )
    orders = data["orders"]["nodes"]
    if not orders:
        raise OrderNotFoundError(f"No Shopify order found for {normalized_reference}")

    order = orders[0]
    if order["name"] != normalized_reference:
        raise OrderNotFoundError(
            f"Shopify returned order {order['name']} for reference "
            f"{normalized_reference}; treating it as not found."
        )
    return {
        "id": order["id"],
        "name": order["name"],
        "facts": normalize_order_facts(order),
    }


def normalize_order_facts(order: dict) -> OrderFacts:
    """Convert Shopify's GraphQL shape into policy-ready values."""
    shop_money = order["totalPriceSet"]["shopMoney"]
    return {
        "processed_at": datetime.fromisoformat(order["processedAt"]),
        # Any fulfillment activity blocks cancellation and address changes.
        "fulfilled": order["displayFulfillmentStatus"] != "UNFULFILLED",
        "total_amount": Decimal(shop_money["amount"]),
        "currency_code": shop_money["currencyCode"],
    }
