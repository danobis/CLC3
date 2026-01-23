import logging
import random
import time
import uuid
from typing import Any, Dict

import requests
from faker import Faker

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
INGESTION_URL = "https://ingestion-api-57rnnqsynq-ey.a.run.app/events"
NUM_EVENTS = 100
DELAY_SECONDS = 0.5
LOCALES = ['de_DE', 'en_US']

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("LoadGenerator")


# -----------------------------------------------------------------------------
# Business Logic
# -----------------------------------------------------------------------------
class OrderDataGenerator:
    """Responsible for generating synthetic e-commerce domain data."""

    def __init__(self):
        self._fake = Faker(LOCALES)

    def create_order_payload(self) -> Dict[str, Any]:
        num_items = random.randint(1, 5)
        items = []
        total_amount = 0.0

        for _ in range(num_items):
            qty = random.randint(1, 3)
            price = round(random.uniform(10.0, 2000.0), 2)

            items.append({
                "sku": self._fake.bothify(text='prod-????-##'),
                "name": self._fake.catch_phrase(),
                "qty": qty,
                "price": price
            })
            total_amount += qty * price

        return {
            "orderId": self._fake.unique.bothify(text='ORD-2024-####'),
            "createdAt": time.time(),
            "customer": {
                "id": self._fake.bothify(text='c_#####'),
                "tier": random.choice(["bronze", "silver", "gold", "platinum"]),
                "email": self._fake.email()
            },
            "items": items,
            "totalAmount": round(total_amount, 2),
            "currency": "EUR",
            "shippingAddress": {
                "city": self._fake.city(),
                "zip": self._fake.postcode(),
                "country": self._fake.current_country_code()
            }
        }


class EventPublisher:
    """Handles HTTP communication with the ingestion service."""

    def __init__(self, url: str):
        self._url = url
        self._session = requests.Session()
        # Optimize connection pooling
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount('https://', adapter)

    def publish(self, payload: Dict[str, Any]) -> bool:
        """
        Sends an event to the API. Returns True on success, False otherwise.
        """
        event_envelope = {
            "eventId": str(uuid.uuid4()),
            "eventType": "order.placed",
            "source": "load-generator-service",
            "payload": payload
        }

        try:
            response = self._session.post(self._url, json=event_envelope, timeout=10)
            response.raise_for_status()
            logger.info(f"Successfully published order: {payload.get('orderId')}")
            return True
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err} - Body: {response.text}")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout error occurred: {timeout_err}")
        except Exception as err:
            logger.error(f"An unexpected error occurred: {err}")

        return False


# -----------------------------------------------------------------------------
# Application Entry Point
# -----------------------------------------------------------------------------
def run_load_test():
    logger.info("Starting load generation...")
    logger.info(f"Target: {INGESTION_URL}")
    logger.info(f"Goal: {NUM_EVENTS} events")

    generator = OrderDataGenerator()
    publisher = EventPublisher(INGESTION_URL)

    success_count = 0

    try:
        for i in range(NUM_EVENTS):
            payload = generator.create_order_payload()
            if publisher.publish(payload):
                success_count += 1

            time.sleep(DELAY_SECONDS)

    except KeyboardInterrupt:
        logger.warning("Load test interrupted by user.")
    finally:
        logger.info("Load test completed.")
        logger.info(f"Summary: Sent {success_count}/{NUM_EVENTS} events successfully.")


if __name__ == "__main__":
    run_load_test()
