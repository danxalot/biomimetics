"""
Asynchronous Knowledge Curation Pipeline
Implements the Symbiotic Research Loop for autonomous knowledge augmentation
"""

import asyncio
import json
import uuid
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import re
import hashlib

import logging
logger = logging.getLogger(__name__)


class TopicPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class ResearchTopic:
    """Represents a topic identified for research"""
    id: str
    name: str
    description: str
    priority: TopicPriority
    user_id: str
    session_ids: List[str]
    keywords: List[str]
    created_at: datetime
    research_status: str = "pending"
    augmentation_objects: List[str] = None
    
    def __post_init__(self):
        if self.augmentation_objects is None:
            self.augmentation_objects = []


@dataclass
class AugmentationObject:
    """Knowledge augmentation package"""
    id: str
    topic_id: str
    title: str
    summary: str
    content: Dict[str, Any]
    knowledge_graph_entries: List[str]
    episodic_memory_ids: List[str]
    confidence_score: float
    created_at: datetime
    presented_to_users: Set[str] = None
    
    def __post_init__(self):
        if self.presented_to_users is None:
            self.presented_to_users = set()


class TopicAnalysisEngine:
    """
    Phase 1: Asynchronous Topic Analysis and Prioritization
    Analyzes conversations to identify research-worthy topics
    """
    
    def __init__(self):
        self.topic_patterns = {
            # Physics concepts
            "quantum": ["quantum", "entanglement", "superposition", "wave function", "observer effect"],
            "relativity": ["relativity", "spacetime", "einstein", "time dilation", "gravity"],
            "particle_physics": ["particles", "bosons", "fermions", "standard model", "higgs"],
            
            # Philosophy concepts
            "consciousness": ["consciousness", "awareness", "mind", "qualia", "phenomenology"],
            "metaphysics": ["reality", "existence", "being", "ontology", "essence"],
            "epistemology": ["knowledge", "truth", "belief", "certainty", "skepticism"],
            
            # Esoteric concepts
            "hermetic": ["hermes", "hermetic", "alchemy", "correspondence", "sympathy"],
            "kabbalah": ["kabbalah", "sephirot", "tree of life", "emanation", "divine"],
            "eastern_philosophy": ["tao", "dharma", "karma", "maya", "atman", "brahman"]
        }
        
        self.cross_domain_indicators = [
            "connection", "relationship", "similar", "analogous", "parallel",
            "corresponds", "relates to", "like", "compared to", "reminds me"
        ]
    
    async def analyze_conversation(self, conversation_messages: List[Dict[str, Any]], 
                                 session_id: str, user_id: str) -> List[ResearchTopic]:
        """Analyze conversation to identify potential research topics"""
        try:
            topics = []
            conversation_text = self._extract_conversation_text(conversation_messages)
            
            # Identify topic categories
            identified_categories = self._identify_topic_categories(conversation_text)
            
            # Look for cross-domain connections
            cross_domain_topics = self._identify_cross_domain_topics(conversation_text, identified_categories)
            
            # Check for user research requests
            explicit_requests = self._identify_explicit_research_requests(conversation_text)
            
            # Generate research topics
            for category, keywords in identified_categories.items():
                if len(keywords) >= 2:  # Multiple mentions indicate interest
                    topic = ResearchTopic(
                        id=str(uuid.uuid4()),
                        name=f"{category.replace('_', ' ').title()} Research",
                        description=f"Deep dive into {category} concepts mentioned in conversation",
                        priority=TopicPriority.MEDIUM,
                        user_id=user_id,
                        session_ids=[session_id],
                        keywords=keywords,
                        created_at=datetime.now()
                    )
                    topics.append(topic)
            
            # High priority for cross-domain topics
            for cross_topic in cross_domain_topics:
                cross_topic.priority = TopicPriority.HIGH
                topics.append(cross_topic)
            
            # Urgent priority for explicit requests
            for explicit_topic in explicit_requests:
                explicit_topic.priority = TopicPriority.URGENT
                topics.append(explicit_topic)
            
            logger.info(f"Identified {len(topics)} research topics from conversation {session_id}")
            return topics
            
        except Exception as e:
            logger.error(f"Error analyzing conversation: {e}")
            return []
    
    def _extract_conversation_text(self, messages: List[Dict[str, Any]]) -> str:
        """Extract text content from conversation messages"""
        text_parts = []
        for msg in messages:
            if msg.get("type") in ["user", "assistant"]:
                text_parts.append(msg.get("content", ""))
        return " ".join(text_parts).lower()
    
    def _identify_topic_categories(self, text: str) -> Dict[str, List[str]]:
        """Identify topic categories and their keywords in text"""
        identified = {}
        
        for category, keywords in self.topic_patterns.items():
            found_keywords = []
            for keyword in keywords:
                if keyword in text:
                    found_keywords.append(keyword)
            
            if found_keywords:
                identified[category] = found_keywords
        
        return identified
    
    def _identify_cross_domain_topics(self, text: str, categories: Dict[str, List[str]]) -> List[ResearchTopic]:
        """Identify topics that span multiple domains"""
        cross_domain_topics = []
        
        if len(categories) >= 2:  # Multiple categories present
            # Look for connection indicators
            has_connection_indicators = any(indicator in text for indicator in self.cross_domain_indicators)
            
            if has_connection_indicators:
                category_names = list(categories.keys())
                all_keywords = []
                for keywords in categories.values():
                    all_keywords.extend(keywords)
                
                topic = ResearchTopic(
                    id=str(uuid.uuid4()),
                    name=f"Cross-Domain: {' & '.join(category_names[:2])}",
                    description=f"Explore connections between {', '.join(category_names)}",
                    priority=TopicPriority.HIGH,
                    user_id="",  # Will be set by caller
                    session_ids=[],  # Will be set by caller
                    keywords=all_keywords,
                    created_at=datetime.now()
                )
                cross_domain_topics.append(topic)
        
        return cross_domain_topics
    
    def _identify_explicit_research_requests(self, text: str) -> List[ResearchTopic]:
        """Identify explicit research requests from user"""
        explicit_topics = []
        
        research_patterns = [
            r"research (.*?) for me",
            r"look into (.*?) further",
            r"find more about (.*?)(?:\.|$)",
            r"explore (.*?) deeper",
            r"investigate (.*?)(?:\.|$)"
        ]
        
        for pattern in research_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                topic_name = match.strip()[:100]  # Limit length
                if len(topic_name) > 3:
                    topic = ResearchTopic(
                        id=str(uuid.uuid4()),
                        name=f"User Request: {topic_name.title()}",
                        description=f"User explicitly requested research on: {topic_name}",
                        priority=TopicPriority.URGENT,
                        user_id="",  # Will be set by caller
                        session_ids=[],  # Will be set by caller
                        keywords=[topic_name],
                        created_at=datetime.now()
                    )
                    explicit_topics.append(topic)
        
        return explicit_topics


class ResearchAgent:
    """
    Phase 2: Knowledge Augmentation Agent
    Conducts research and creates augmentation objects
    """
    
    def __init__(self):
        self.research_sources = {
            "physics_concepts": [
                "Stanford Encyclopedia of Philosophy - Physics",
                "Quantum Theory Fundamentals",
                "Modern Physics Concepts"
            ],
            "philosophy_concepts": [
                "Stanford Encyclopedia of Philosophy",
                "Philosophy of Mind Resources",
                "Metaphysics and Ontology"
            ],
            "esoteric_concepts": [
                "Hermetic Texts Collection",
                "Kabbalah Study Materials",
                "Eastern Philosophy Archives"
            ]
        }
    
    async def research_topic(self, topic: ResearchTopic) -> Optional[AugmentationObject]:
        """Conduct research on topic and create augmentation object"""
        try:
            logger.info(f"Starting research on topic: {topic.name}")
            
            # Simulate research process
            research_results = await self._conduct_research(topic)
            
            if not research_results:
                logger.warning(f"No research results for topic: {topic.name}")
                return None
            
            # Create augmentation object
            augmentation = AugmentationObject(
                id=str(uuid.uuid4()),
                topic_id=topic.id,
                title=f"Research Results: {topic.name}",
                summary=research_results.get("summary", ""),
                content=research_results,
                knowledge_graph_entries=research_results.get("entities", []),
                episodic_memory_ids=research_results.get("memory_chunks", []),
                confidence_score=research_results.get("confidence", 0.8),
                created_at=datetime.now()
            )
            
            logger.info(f"Created augmentation object: {augmentation.id}")
            return augmentation
            
        except Exception as e:
            logger.error(f"Error researching topic {topic.name}: {e}")
            return None
    
    async def _conduct_research(self, topic: ResearchTopic) -> Dict[str, Any]:
        """Simulate research process - in production, integrate with actual sources"""
        try:
            # Simulate async research delay
            await asyncio.sleep(1)
            
            # Generate mock research results based on topic
            results = {
                "summary": f"Comprehensive research on {topic.name} covering key concepts and relationships.",
                "key_findings": [
                    f"Primary concept: {topic.keywords[0] if topic.keywords else 'Unknown'}",
                    f"Related areas: {', '.join(topic.keywords[1:3]) if len(topic.keywords) > 1 else 'None'}",
                    "Cross-domain connections identified",
                    "Historical development traced"
                ],
                "entities": [f"entity_{keyword}" for keyword in topic.keywords[:5]],
                "relationships": [
                    {"from": topic.keywords[0] if topic.keywords else "unknown", 
                     "to": topic.keywords[1] if len(topic.keywords) > 1 else "concept",
                     "type": "RELATES_TO"}
                ],
                "memory_chunks": [f"chunk_{i}" for i in range(3)],
                "sources": self._get_relevant_sources(topic),
                "confidence": 0.85,
                "research_timestamp": datetime.now().isoformat()
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error in research simulation: {e}")
            return {}
    
    def _get_relevant_sources(self, topic: ResearchTopic) -> List[str]:
        """Get relevant sources based on topic keywords"""
        relevant_sources = []
        
        for keyword in topic.keywords:
            if any(physics_term in keyword for physics_term in ["quantum", "particle", "relativity"]):
                relevant_sources.extend(self.research_sources["physics_concepts"])
            elif any(phil_term in keyword for phil_term in ["consciousness", "reality", "knowledge"]):
                relevant_sources.extend(self.research_sources["philosophy_concepts"])
            elif any(eso_term in keyword for eso_term in ["hermetic", "kabbalah", "tao"]):
                relevant_sources.extend(self.research_sources["esoteric_concepts"])
        
        # Remove duplicates and limit
        return list(set(relevant_sources))[:3]


class KnowledgeCurationPipeline:
    """
    Main orchestrator for the asynchronous knowledge curation pipeline
    Implements the complete Symbiotic Research Loop
    """
    
    def __init__(self, memory_system=None):
        self.topic_analyzer = TopicAnalysisEngine()
        self.research_agent = ResearchAgent()
        self.memory_system = memory_system
        
        # In-memory storage (in production, use persistent storage)
        self.pending_topics: List[ResearchTopic] = []
        self.completed_augmentations: Dict[str, AugmentationObject] = {}
        self.user_topic_history: Dict[str, List[str]] = {}
        
        # Pipeline control
        self.is_running = False
        self.pipeline_task = None
        
    async def start_pipeline(self):
        """Start the asynchronous curation pipeline"""
        if not self.is_running:
            self.is_running = True
            self.pipeline_task = asyncio.create_task(self._pipeline_worker())
            logger.info("Knowledge curation pipeline started")
    
    async def stop_pipeline(self):
        """Stop the curation pipeline"""
        self.is_running = False
        if self.pipeline_task:
            self.pipeline_task.cancel()
            try:
                await self.pipeline_task
            except asyncio.CancelledError:
                pass
        logger.info("Knowledge curation pipeline stopped")
    
    async def analyze_conversation_for_topics(self, conversation_messages: List[Dict[str, Any]], 
                                            session_id: str, user_id: str) -> List[str]:
        """Analyze conversation and queue topics for research"""
        try:
            # Phase 1: Topic Analysis and Prioritization
            topics = await self.topic_analyzer.analyze_conversation(
                conversation_messages, session_id, user_id
            )
            
            # Update topics with session and user info
            for topic in topics:
                topic.user_id = user_id
                topic.session_ids = [session_id]
            
            # Cross-reference with existing knowledge
            prioritized_topics = await self._prioritize_topics(topics, user_id)
            
            # Queue high-priority topics
            topic_ids = []
            for topic in prioritized_topics:
                if topic.priority in [TopicPriority.HIGH, TopicPriority.URGENT]:
                    self.pending_topics.append(topic)
                    topic_ids.append(topic.id)
                    
                    # Track user topic history
                    if user_id not in self.user_topic_history:
                        self.user_topic_history[user_id] = []
                    self.user_topic_history[user_id].append(topic.id)
            
            logger.info(f"Queued {len(topic_ids)} topics for research from session {session_id}")
            return topic_ids
            
        except Exception as e:
            logger.error(f"Error analyzing conversation for topics: {e}")
            return []
    
    async def get_relevant_augmentations(self, query: str, user_id: str, 
                                       session_id: str) -> List[Dict[str, Any]]:
        """Get relevant augmentation objects for current conversation"""
        try:
            relevant_augmentations = []
            
            # Find augmentations related to current query
            query_lower = query.lower()
            
            for aug_id, augmentation in self.completed_augmentations.items():
                # Check keyword relevance
                relevance_score = self._calculate_relevance(query_lower, augmentation)
                
                if relevance_score > 0.3:  # Relevance threshold
                    # Check if already presented to this user
                    if user_id not in augmentation.presented_to_users:
                        relevant_augmentations.append({
                            "augmentation_id": aug_id,
                            "title": augmentation.title,
                            "summary": augmentation.summary,
                            "relevance_score": relevance_score,
                            "confidence": augmentation.confidence_score,
                            "created_at": augmentation.created_at.isoformat(),
                            "knowledge_graph_connections": len(augmentation.knowledge_graph_entries),
                            "content_preview": self._create_content_preview(augmentation)
                        })
            
            # Sort by relevance
            relevant_augmentations.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Mark as presented to user
            for aug_data in relevant_augmentations[:3]:  # Limit to top 3
                aug_id = aug_data["augmentation_id"]
                if aug_id in self.completed_augmentations:
                    self.completed_augmentations[aug_id].presented_to_users.add(user_id)
            
            return relevant_augmentations[:3]  # Return top 3
            
        except Exception as e:
            logger.error(f"Error getting relevant augmentations: {e}")
            return []
    
    async def _pipeline_worker(self):
        """Main pipeline worker - processes topics in background"""
        while self.is_running:
            try:
                if self.pending_topics:
                    # Process highest priority topic
                    topic = max(self.pending_topics, key=lambda t: t.priority.value)
                    self.pending_topics.remove(topic)
                    
                    logger.info(f"Processing topic: {topic.name} (Priority: {topic.priority.name})")
                    
                    # Phase 2: Research and Augmentation
                    augmentation = await self.research_agent.research_topic(topic)
                    
                    if augmentation:
                        # Phase 3: Integration with memory system
                        await self._integrate_with_memory_system(augmentation)
                        
                        # Store completed augmentation
                        self.completed_augmentations[augmentation.id] = augmentation
                        
                        # Update topic status
                        topic.research_status = "completed"
                        topic.augmentation_objects.append(augmentation.id)
                        
                        logger.info(f"Completed research for topic: {topic.name}")
                    else:
                        topic.research_status = "failed"
                        logger.warning(f"Failed to research topic: {topic.name}")
                
                # Sleep before next iteration
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pipeline worker: {e}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _prioritize_topics(self, topics: List[ResearchTopic], user_id: str) -> List[ResearchTopic]:
        """Prioritize topics based on existing knowledge and user history"""
        try:
            for topic in topics:
                # Check if user has shown repeated interest
                user_history = self.user_topic_history.get(user_id, [])
                related_topics = [t_id for t_id in user_history 
                                if any(keyword in topic.keywords for keyword in topic.keywords)]
                
                if len(related_topics) > 1:
                    # Increase priority for repeated interest
                    if topic.priority == TopicPriority.MEDIUM:
                        topic.priority = TopicPriority.HIGH
                
                # Check novelty - if we already have augmentations on this topic, lower priority
                existing_augmentations = [aug for aug in self.completed_augmentations.values()
                                        if any(keyword in aug.summary.lower() for keyword in topic.keywords)]
                
                if len(existing_augmentations) > 0:
                    # Lower priority if we already have research
                    if topic.priority == TopicPriority.HIGH:
                        topic.priority = TopicPriority.MEDIUM
            
            return topics
            
        except Exception as e:
            logger.error(f"Error prioritizing topics: {e}")
            return topics
    
    async def _integrate_with_memory_system(self, augmentation: AugmentationObject):
        """Integrate augmentation with the memory system"""
        try:
            if not self.memory_system:
                logger.warning("No memory system available for integration")
                return
            
            # Add to episodic memory
            content_text = f"{augmentation.title}\n\n{augmentation.summary}\n\nKey Findings: {json.dumps(augmentation.content.get('key_findings', []))}"
            
            episodic_id = await self.memory_system.episodic_memory.add_memory(
                content=content_text,
                source=f"research_augmentation_{augmentation.id}",
                document_type="research",
                metadata={
                    "augmentation_id": augmentation.id,
                    "topic_id": augmentation.topic_id,
                    "confidence": augmentation.confidence_score,
                    "research_type": "autonomous"
                }
            )
            
            # Add entities to structural memory
            for entity_data in augmentation.content.get("entities", []):
                entity_id = f"research_{entity_data}"
                await self.memory_system.structural_memory.add_entity(
                    entity_id=entity_id,
                    entity_type="RESEARCH_CONCEPT",
                    name=entity_data.replace("entity_", "").title(),
                    properties={
                        "source": "autonomous_research",
                        "augmentation_id": augmentation.id,
                        "confidence": augmentation.confidence_score
                    }
                )
            
            # Add relationships from research
            for rel in augmentation.content.get("relationships", []):
                from_entity = f"research_{rel.get('from', 'unknown')}"
                to_entity = f"research_{rel.get('to', 'unknown')}"
                rel_type = rel.get("type", "RELATES_TO")
                
                await self.memory_system.structural_memory.add_relationship(
                    from_entity, to_entity, rel_type,
                    {
                        "source": "autonomous_research",
                        "augmentation_id": augmentation.id,
                        "confidence": augmentation.confidence_score
                    }
                )
            
            logger.info(f"Integrated augmentation {augmentation.id} with memory system")
            
        except Exception as e:
            logger.error(f"Error integrating with memory system: {e}")
    
    def _calculate_relevance(self, query: str, augmentation: AugmentationObject) -> float:
        """Calculate relevance score between query and augmentation"""
        try:
            query_words = set(query.lower().split())
            
            # Check title relevance
            title_words = set(augmentation.title.lower().split())
            title_overlap = len(query_words & title_words) / max(len(query_words), 1)
            
            # Check summary relevance
            summary_words = set(augmentation.summary.lower().split())
            summary_overlap = len(query_words & summary_words) / max(len(query_words), 1)
            
            # Check keyword relevance if available
            content_keywords = augmentation.content.get("key_findings", [])
            keyword_text = " ".join(str(kw).lower() for kw in content_keywords)
            keyword_words = set(keyword_text.split())
            keyword_overlap = len(query_words & keyword_words) / max(len(query_words), 1)
            
            # Weighted relevance score
            relevance = (title_overlap * 0.4 + summary_overlap * 0.3 + keyword_overlap * 0.3)
            
            return min(relevance, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating relevance: {e}")
            return 0.0
    
    def _create_content_preview(self, augmentation: AugmentationObject) -> str:
        """Create a preview of augmentation content"""
        try:
            key_findings = augmentation.content.get("key_findings", [])
            if key_findings:
                return f"Key insights: {'; '.join(str(finding) for finding in key_findings[:2])}"
            else:
                return augmentation.summary[:150] + "..." if len(augmentation.summary) > 150 else augmentation.summary
                
        except Exception as e:
            logger.error(f"Error creating content preview: {e}")
            return "Content preview unavailable"
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status"""
        return {
            "is_running": self.is_running,
            "pending_topics": len(self.pending_topics),
            "completed_augmentations": len(self.completed_augmentations),
            "users_tracked": len(self.user_topic_history),
            "pipeline_uptime": datetime.now().isoformat() if self.is_running else None
        }