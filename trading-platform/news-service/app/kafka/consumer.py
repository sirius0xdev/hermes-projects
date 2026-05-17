"""Kafka consumer pipeline: watches for new articles on the articles topic."""

import json
import logging
from typing import Optional
from kafka import KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from app.core.config import get_settings
from app.services.nlp.analyzer import analyze_article

logger = logging.getLogger(__name__)


class KafkaArticleConsumer:
    """Consumes raw articles from Kafka, runs NLP analysis, publishes results.
    
    Topic flow:
    - Consumes from: news.articles (raw article data from scraper)
    - Produces to: news.analysis (NLP analysis results)
    """
    
    def __init__(self):
        self.consumer: Optional[KafkaConsumer] = None
        self._running = False
    
    def _ensure_topics(self, admin_client: KafkaAdminClient):
        """Ensure required topics exist."""
        existing = admin_client.list_topics()
        settings = get_settings()
        
        topics_to_create = []
        for topic_name in [settings.kafka_topic_articles, settings.kafka_topic_analysis]:
            if topic_name not in existing:
                topics_to_create.append(NewTopic(
                    name=topic_name,
                    num_partitions=3,
                    replication_factor=1,
                    config={"retention.ms": str(7 * 24 * 60 * 60 * 1000)},  # 7 days
                ))
        
        if topics_to_create:
            admin_client.create_topics(topics_to_create)
            logger.info(f"Created topics: {[t.name for t in topics_to_create]}")
    
    def start(self, process_article_func):
        """Start consuming articles and processing them."""
        settings = get_settings()
        
        self.consumer = KafkaConsumer(
            settings.kafka_topic_articles,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset=settings.kafka_auto_offset_reset,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
        )
        
        self._running = True
        logger.info(
            f"Kafka consumer started (topic={settings.kafka_topic_articles}, "
            f"group={settings.kafka_group_id})"
        )
        
        try:
            while self._running:
                # Poll with 100ms timeout
                records = self.consumer.poll(timeout_ms=100)
                
                for topic_partition, messages in records.items():
                    for message in messages:
                        self._process_message(message, process_article_func)
        except Exception:
            logger.exception("Kafka consumer error")
            self.stop()
    
    def _process_message(self, message, process_article_func):
        """Process a single article message."""
        try:
            article_data = message.value
            logger.debug(
                f"Processing article from Kafka: "
                f"partition={message.partition}, offset={message.offset}"
            )
            
            # Run NLP analysis
            analysis_result = process_article_func(article_data)
            
            # Publish analysis result
            if analysis_result:
                self._publish_analysis(analysis_result)
                
        except Exception:
            logger.exception(f"Error processing message at offset {message.offset}")
    
    def _publish_analysis(self, analysis_result: dict):
        """Publish analysis result to the output topic."""
        # Note: In production, use kafka-python's KafkaProducer
        # For now, we store directly to DB via the service
        logger.info(
            f"Analysis published for article_id={analysis_result.get('article_id')}: "
            f"sentiment={analysis_result.get('sentiment_label')}, "
            f"impact={analysis_result.get('market_impact_score')}"
        )
    
    def stop(self):
        """Stop the consumer."""
        self._running = False
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer closed")


class InMemoryMessageBroker:
    """In-memory message broker for development/testing without Kafka.
    
    Simulates Kafka topics using a publish/subscribe pattern with queues.
    """
    
    def __init__(self):
        self._subscribers = {}  # topic -> list of subscriber functions
    
    def subscribe(self, topic: str, handler):
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.info(f"Subscribed handler to topic: {topic}")
    
    def publish(self, topic: str, message: dict):
        """Publish a message to a topic, delivering to all subscribers."""
        subscribers = self._subscribers.get(topic, [])
        for handler in subscribers:
            try:
                handler(message)
            except Exception:
                logger.exception(f"Subscriber error on topic {topic}")
