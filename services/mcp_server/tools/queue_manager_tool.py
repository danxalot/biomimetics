#!/usr/bin/env python3
"""
Queue Manager Tool for ARCA MCP Server
Handles RabbitMQ connections and job queue management
"""

import logging
import pika
import json
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)

class QueueManager:
    """Manages RabbitMQ connections and job queuing operations"""

    def __init__(self):
        self.connection_params = {
            'host': os.getenv('RABBITMQ_HOST', 'arca-rabbitmq'),
            'port': int(os.getenv('RABBITMQ_PORT', '5672')),
            'virtual_host': os.getenv('RABBITMQ_VHOST', 'arca_vhost'),
            'credentials': pika.PlainCredentials(
                os.getenv('RABBITMQ_USER', 'arca'),
                os.getenv('RABBITMQ_PASSWORD', 'arca_password')
            )
        }
        self.connection = None
        self.channel = None

    def _get_connection(self) -> Optional[pika.BlockingConnection]:
        """Get or create RabbitMQ connection"""
        try:
            if self.connection is None or self.connection.is_closed:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(**self.connection_params)
                )
                self.channel = self.connection.channel()
            return self.connection
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return None

    def submit_job(self, queue_name: str, job_data: Dict[str, Any]) -> bool:
        """Submit a job to the specified queue"""
        try:
            connection = self._get_connection()
            if connection is None:
                return False

            # Declare queue (idempotent)
            self.channel.queue_declare(queue=queue_name, durable=True)

            # Publish message
            message = json.dumps(job_data)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )

            logger.info(f"Job {job_data.get('id', 'unknown')} submitted to queue {queue_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to submit job to queue {queue_name}: {e}")
            return False

    def close(self):
        """Close the connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()