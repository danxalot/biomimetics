import pika
import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RabbitMQClient:
    def __init__(self):
        self.host = os.getenv('RABBITMQ_HOST', 'arca-rabbitmq')
        self.port = int(os.getenv('RABBITMQ_PORT', 5672))
        self.user = os.getenv('RABBITMQ_USER', 'arca')
        self.password = os.getenv('RABBITMQ_PASSWORD', 'arca_password')
        self.exchange = 'arca.nexus'
        self.vhost = os.getenv('RABBITMQ_VHOST', 'arca_vhost')
        self.credentials = pika.PlainCredentials(self.user, self.password)
        self.parameters = pika.ConnectionParameters(self.host, self.port, self.vhost, self.credentials)

    def publish(self, routing_key: str, message: Dict[str, Any]):
        """Publish a message to the exchange"""
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            channel.exchange_declare(exchange=self.exchange, exchange_type='topic', durable=True)
            
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(message)
            )
            connection.close()
            logger.info(f"Published to {routing_key}")
        except Exception as e:
            logger.error(f"Failed to publish to {routing_key}: {e}")
            # Fallback or retry logic could go here
