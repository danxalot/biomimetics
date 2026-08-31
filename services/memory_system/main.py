#!/usr/bin/env python3
"""
ARCA Memory System Service

A comprehensive memory management service that integrates:
- Working Memory (SQLite): Short-term conversation context
- Episodic Memory (SQLite + Vector DB): Long-term semantic memory
- Structural Memory (Neo4j): Knowledge graph relationships
- ReasoningBank: Agent learning and strategy development

Features:
- RESTful API for memory operations
- MCP integration for tool access
- Health monitoring and metrics
- Automatic summarization and optimization
"""

import os
import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from contextlib import asynccontextmanager

# Import memory system
try:
    from memory_system import UnifiedMemorySystem
except ImportError:
    # Try relative import
    from .memory_system import UnifiedMemorySystem

# Import ReasoningTrajectory
try:
    from langgraph_agent import ReasoningTrajectory
except ImportError:
    ReasoningTrajectory = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Global variables
memory_system = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global memory_system

    # Startup
    logger.info("Starting ARCA Memory System Service...")

    # Initialize memory system
    try:
        memory_system = UnifiedMemorySystem(
            working_memory_db=os.getenv("WORKING_MEMORY_DB", "/app/data/working_memory.db"),
            postgres_host=os.getenv("POSTGRES_HOST"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            api_key=os.getenv("GOOGLE_API_KEY"),
            embedding_service_url=os.getenv("EMBEDDING_SERVICE_URL", "http://embedding_service:8005"),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password")
        )

        await memory_system.initialize()
        logger.info("Memory system initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize memory system: {e}")
        memory_system = None

    yield

    # Shutdown
    if memory_system:
        await memory_system.close()
    logger.info("ARCA Memory System Service stopped")

# Create FastAPI app
app = FastAPI(
    title="ARCA Memory System",
    description="Comprehensive memory management with working, episodic, structural, and reasoning layers",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Set limiter in app state
app.state.limiter = limiter

# Pydantic models
class ConversationTurn(BaseModel):
    session_id: str = Field(..., description="Conversation session ID")
    user_id: str = Field(..., description="User identifier")
    user_message: str = Field(..., description="User message content")
    assistant_response: str = Field(..., description="Assistant response content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class DocumentInput(BaseModel):
    content: str = Field(..., description="Document content")
    source: str = Field(..., description="Document source identifier")
    document_type: str = Field("document", description="Type of document")

class ContextQuery(BaseModel):
    session_id: str = Field(..., description="Session ID for context")
    query: str = Field(..., description="Query for context retrieval")
    user_id: Optional[str] = Field("default", description="User identifier")

class AgentTrajectory(BaseModel):
    agent_id: str = Field(..., description="Agent identifier")
    task_input: str = Field(..., description="Task description")
    task_type: str = Field(..., description="Type of task")
    actions_taken: List[str] = Field(..., description="Actions performed")
    context_used: Dict[str, Any] = Field(..., description="Context information used")
    outcome: str = Field(..., description="Task outcome (success/failure)")
    execution_time: float = Field(..., description="Execution time in seconds")
    timestamp: datetime = Field(default_factory=datetime.now, description="Trajectory timestamp")

class LearningQuery(BaseModel):
    agent_id: str = Field(..., description="Agent identifier")
    task_context: str = Field(..., description="Current task context")

class CypherQuery(BaseModel):
    query: str = Field(..., description="Cypher query string")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")

async def publish_health_alert(service: str, status: str, error_type: str, component: str, 
                               message: str, suggested_skill: str = None, suggested_action: str = None):
    """
    Publish health alert to Redis for Serena's self-healing system.
    Follows ARCA_SELF_HEALING_SYSTEM.md specification.
    """
    try:
        import redis
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        enable_alerts = os.getenv("ENABLE_HEALTH_ALERTS", "true").lower() == "true"
        
        if not enable_alerts:
            logger.info(f"Health alerts disabled, skipping alert for {error_type}")
            return
        
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        
        alert = {
            "service": service,
            "status": status,
            "details": {
                "error_type": error_type,
                "component": component,
                "message": message,
                "suggested_skill": suggested_skill,
                "suggested_action": suggested_action
            },
            "timestamp": datetime.now().isoformat(),
            "severity": "critical" if status in ["critical", "unhealthy"] else "warning"
        }
        
        # Publish to alert channel
        channel = os.getenv("REDIS_ALERT_CHANNEL", "arca:health:alerts")
        r.publish(channel, json.dumps(alert))
        
        # Also store in history list (keep last 100)
        history_key = f"{channel}:history"
        r.lpush(history_key, json.dumps(alert))
        r.ltrim(history_key, 0, 99)
        
        logger.warning(f"Published health alert: {error_type} for {component}")
        
    except Exception as e:
        logger.error(f"Failed to publish health alert: {e}")


@app.get("/health")
async def health_check():
    """
    Enhanced health check endpoint with authentication and write tests.
    Tests all memory layers and publishes Redis alerts for CRITICAL failures.
    """
    health_status = {
        "status": "healthy" if memory_system else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "memory_system_initialized": memory_system is not None,
        "reasoning_bank_available": memory_system.reasoning_bank is not None if memory_system else False,
        "components": {}
    }

    if not memory_system:
        await publish_health_alert(
            service="memory_system",
            status="critical",
            error_type="memory_system_not_initialized",
            component="memory_system",
            message="Memory system failed to initialize",
            suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
            suggested_action="restart_memory_system"
        )
        return health_status

    all_healthy = True

    # Test 1: Working Memory (SQLite) - Write Test
    try:
        test_session = f"health_check_{datetime.now().isoformat()}"
        await memory_system.working_memory.add_message(
            test_session, "health_check", "system", "Health check", {}
        )
        health_status["components"]["working_memory"] = {"status": "healthy", "details": "Write test passed"}
    except Exception as e:
        health_status["components"]["working_memory"] = {"status": "critical", "details": f"Write failed: {str(e)}"}
        health_status["status"] = "critical"
        all_healthy = False
        await publish_health_alert(
            service="memory_system",
            status="critical",
            error_type="working_memory_write_failed",
            component="working_memory",
            message=f"SQLite write test failed: {str(e)}",
            suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
            suggested_action="restart_memory_system"
        )

    # Test 2: Redis - Connection and Write Test
    try:
        import redis
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r.ping()
        # Write test
        test_key = f"arca:health:test:{datetime.now().timestamp()}"
        r.set(test_key, "ok", ex=10)
        val = r.get(test_key)
        if val == "ok":
            health_status["components"]["redis"] = {"status": "healthy", "details": "Connection and write test passed"}
        else:
            raise Exception("Write test failed - value mismatch")
    except Exception as e:
        health_status["components"]["redis"] = {"status": "critical", "details": f"Failed: {str(e)}"}
        health_status["status"] = "critical"
        all_healthy = False
        await publish_health_alert(
            service="memory_system",
            status="critical",
            error_type="redis_connection_failed",
            component="cache_layer",
            message=f"Redis connection or write failed: {str(e)}",
            suggested_skill="ARCA_SELF_HEALING_SYSTEM.md",
            suggested_action="restart_redis"
        )

    # Test 3: Neo4j - Authentication and Write Test
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            # Authentication test - this will fail if auth is wrong
            result = session.run("RETURN 1 as test")
            record = result.single()
            
            # Write test - create and delete a test node
            session.run("CREATE (n:HealthCheck {timestamp: $ts}) RETURN n", 
                       ts=datetime.now().isoformat())
            session.run("MATCH (n:HealthCheck) DELETE n")
            
        driver.close()
        health_status["components"]["neo4j"] = {"status": "healthy", "details": "Authentication and write test passed"}
    except Exception as e:
        error_msg = str(e).lower()
        if "unauthorized" in error_msg or "authentication" in error_msg:
            health_status["components"]["neo4j"] = {"status": "critical", "details": f"Authentication failed: {str(e)}"}
            health_status["status"] = "critical"
            all_healthy = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="neo4j_auth_failed",
                component="structural_memory",
                message=f"Neo4j authentication failed: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
                suggested_action="reset_neo4j_password"
            )
        else:
            health_status["components"]["neo4j"] = {"status": "critical", "details": f"Connection or write failed: {str(e)}"}
            health_status["status"] = "critical"
            all_healthy = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="neo4j_connection_failed",
                component="structural_memory",
                message=f"Neo4j connection or write failed: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
                suggested_action="restart_neo4j"
            )

    # Test 4: PostgreSQL - Authentication and Write Test
    try:
        import psycopg2
        postgres_host = os.getenv("POSTGRES_HOST", "postgres")
        postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        postgres_db = os.getenv("POSTGRES_DB", "arca_episodic")
        postgres_user = os.getenv("POSTGRES_USER", "arca")
        postgres_password = os.getenv("POSTGRES_PASSWORD", "arca_secure_password")
        
        conn = psycopg2.connect(
            host=postgres_host,
            port=postgres_port,
            database=postgres_db,
            user=postgres_user,
            password=postgres_password
        )
        
        cursor = conn.cursor()
        # Authentication test - connection itself tests auth
        cursor.execute("SELECT 1")
        
        # Write test - create and drop a test table
        test_table = f"health_check_{int(datetime.now().timestamp())}"
        cursor.execute(f"CREATE TEMP TABLE {test_table} (id INT)")
        cursor.execute(f"INSERT INTO {test_table} VALUES (1)")
        cursor.execute(f"DROP TABLE {test_table}")
        conn.commit()
        
        cursor.close()
        conn.close()
        health_status["components"]["postgres"] = {"status": "healthy", "details": "Authentication and write test passed"}
    except Exception as e:
        error_msg = str(e).lower()
        if "authentication" in error_msg or "password" in error_msg:
            health_status["components"]["postgres"] = {"status": "critical", "details": f"Authentication failed: {str(e)}"}
            health_status["status"] = "critical"
            all_healthy = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="postgres_auth_failed",
                component="episodic_memory",
                message=f"PostgreSQL authentication failed: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR_PostgreSQL.md",
                suggested_action="verify_postgres_credentials"
            )
        else:
            health_status["components"]["postgres"] = {"status": "critical", "details": f"Connection or write failed: {str(e)}"}
            health_status["status"] = "critical"
            all_healthy = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="postgres_connection_failed",
                component="episodic_memory",
                message=f"PostgreSQL connection or write failed: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR_PostgreSQL.md",
                suggested_action="restart_postgres"
            )

    # Update overall status
    if all_healthy:
        health_status["status"] = "healthy"
        health_status["message"] = "All memory layers operational"
    else:
        health_status["message"] = "One or more memory layers have critical failures"

    return health_status

@app.post("/conversation")
async def add_conversation_turn(turn: ConversationTurn, request: Request):
    """Add a conversation turn to memory"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        result = await memory_system.add_conversation_turn(
            turn.session_id, turn.user_id, turn.user_message,
            turn.assistant_response, turn.metadata
        )
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error adding conversation turn: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/document")
async def add_document(doc: DocumentInput, request: Request):
    """Add a document to memory"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        result = await memory_system.add_document(
            doc.content, doc.source, doc.document_type
        )
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error adding document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/context")
async def get_context(query: ContextQuery, request: Request):
    """Get comprehensive context from all memory layers"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        context = await memory_system.get_comprehensive_context(
            query.session_id, query.query, query.user_id
        )
        return {"status": "success", "context": context}
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trajectory")
async def record_trajectory(trajectory: AgentTrajectory, request: Request):
    """Record agent trajectory for learning"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        # Convert to ReasoningTrajectory format
        reasoning_trajectory = ReasoningTrajectory(
            agent_id=trajectory.agent_id,
            initial_state={
                "task_input": trajectory.task_input,
                "task_type": trajectory.task_type
            },
            actions_taken=trajectory.actions_taken,
            context_used=trajectory.context_used,
            outcome=trajectory.outcome,
            execution_time=trajectory.execution_time,
            timestamp=trajectory.timestamp
        )

        result = await memory_system.record_agent_trajectory(reasoning_trajectory)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error recording trajectory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/learning")
async def get_learning_context(query: LearningQuery, request: Request):
    """Get learning context for agent decision making"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        context = await memory_system.get_agent_learning_context(
            query.agent_id, query.task_context
        )
        return {"status": "success", "learning_context": context}
    except Exception as e:
        logger.error(f"Error getting learning context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/structural/cypher")
async def run_cypher_query(query: CypherQuery, request: Request):
    """Run a raw Cypher query against the knowledge graph"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        result = await memory_system.structural_memory.run_cypher(
            query.query, query.parameters
        )
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error running Cypher query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/strategies")
async def get_strategies(task_context: str, top_k: int = 5, request: Request = None):
    """Get reasoning strategies for a task context"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        strategies = await memory_system.get_reasoning_strategies(task_context, top_k)
        return {"status": "success", "strategies": strategies}
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_memory_stats():
    """Get memory system statistics"""
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    try:
        # This would be expanded to provide detailed stats
        stats = {
            "reasoning_bank_strategies": len(memory_system.reasoning_bank.strategy_library) if memory_system.reasoning_bank and hasattr(memory_system.reasoning_bank, 'strategy_library') else 0,
            "timestamp": datetime.now().isoformat()
        }
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/preflight")
async def preflight_check():
    """
    Comprehensive preflight check for all database connections.
    Used before consuming Genesis jobs to ensure infrastructure is ready.
    
    Returns:
        - redis: Redis blackboard connectivity
        - neo4j: Neo4j graph database connectivity  
        - postgres: PostgreSQL vector DB connectivity
        - working_memory: SQLite working memory
        - all_systems_go: Boolean indicating all systems are operational
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "redis": {"status": "unknown", "details": None},
        "neo4j": {"status": "unknown", "details": None},
        "postgres": {"status": "unknown", "details": None},
        "working_memory": {"status": "unknown", "details": None},
        "all_systems_go": False
    }
    
    if not memory_system:
        results["error"] = "Memory system not initialized"
        return results
    
    all_ok = True
    
    # Test Redis Blackboard
    try:
        import redis
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r.ping()
        # Test read/write
        test_key = "arca:preflight:test"
        r.set(test_key, "ok", ex=10)
        val = r.get(test_key)
        if val == "ok":
            results["redis"] = {"status": "ok", "details": {"host": redis_host, "port": redis_port}}
        else:
            results["redis"] = {"status": "error", "details": "Read/write test failed"}
            all_ok = False
    except Exception as e:
        results["redis"] = {"status": "error", "details": str(e)}
        all_ok = False
    
    # Test Neo4j
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            # Authentication test
            result = session.run("MATCH (n) RETURN count(n) as count")
            record = result.single()
            node_count = record["count"] if record else 0
            
            # Check for Aether node (Genesis requirement)
            aether_result = session.run("MATCH (a:Metaphysics {name: 'Aether'}) RETURN a.name as name LIMIT 1")
            aether_record = aether_result.single()
            has_aether = aether_record is not None
            
            # Write test
            session.run("CREATE (n:PreflightCheck {timestamp: $ts}) RETURN n", 
                       ts=datetime.now().isoformat())
            session.run("MATCH (n:PreflightCheck) DELETE n")
            
        driver.close()
        results["neo4j"] = {
            "status": "ok", 
            "details": {
                "uri": neo4j_uri, 
                "node_count": node_count,
                "aether_seeded": has_aether,
                "auth_verified": True,
                "write_test": "passed"
            }
        }
    except Exception as e:
        error_msg = str(e).lower()
        if "unauthorized" in error_msg or "authentication" in error_msg:
            results["neo4j"] = {"status": "error", "details": f"Authentication failed: {str(e)}"}
            all_ok = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="neo4j_auth_failed",
                component="structural_memory",
                message=f"Neo4j authentication failed during preflight: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
                suggested_action="reset_neo4j_password"
            )
        else:
            results["neo4j"] = {"status": "error", "details": str(e)}
            all_ok = False
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="neo4j_connection_failed",
                component="structural_memory",
                message=f"Neo4j connection failed during preflight: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR.md",
                suggested_action="restart_neo4j"
            )
    
    # Test PostgreSQL (if configured)
    try:
        postgres_host = os.getenv("POSTGRES_HOST")
        if postgres_host:
            import psycopg2
            postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
            postgres_db = os.getenv("POSTGRES_DB")
            postgres_user = os.getenv("POSTGRES_USER")
            postgres_password = os.getenv("POSTGRES_PASSWORD")
            
            conn = psycopg2.connect(
                host=postgres_host,
                port=postgres_port,
                database=postgres_db,
                user=postgres_user,
                password=postgres_password
            )
            
            cursor = conn.cursor()
            # Authentication test
            cursor.execute("SELECT 1")
            
            # Write test
            test_table = f"preflight_check_{int(datetime.now().timestamp())}"
            cursor.execute(f"CREATE TEMP TABLE {test_table} (id INT)")
            cursor.execute(f"INSERT INTO {test_table} VALUES (1)")
            cursor.execute(f"DROP TABLE {test_table}")
            conn.commit()
            
            cursor.close()
            conn.close()
            results["postgres"] = {
                "status": "ok", 
                "details": {
                    "host": postgres_host, 
                    "database": postgres_db,
                    "auth_verified": True,
                    "write_test": "passed"
                }
            }
        else:
            results["postgres"] = {"status": "skipped", "details": "POSTGRES_HOST not configured"}
    except Exception as e:
        error_msg = str(e).lower()
        if "authentication" in error_msg or "password" in error_msg:
            results["postgres"] = {"status": "error", "details": f"Authentication failed: {str(e)}"}
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="postgres_auth_failed",
                component="episodic_memory",
                message=f"PostgreSQL authentication failed during preflight: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR_PostgreSQL.md",
                suggested_action="verify_postgres_credentials"
            )
        else:
            results["postgres"] = {"status": "error", "details": str(e)}
            await publish_health_alert(
                service="memory_system",
                status="critical",
                error_type="postgres_connection_failed",
                component="episodic_memory",
                message=f"PostgreSQL connection failed during preflight: {str(e)}",
                suggested_skill="ARCA_MEMORY_SYSTEM_REPAIR_PostgreSQL.md",
                suggested_action="restart_postgres"
            )
        # PostgreSQL is optional, don't fail preflight
        all_ok = False
    
    # Test Working Memory (SQLite)
    try:
        test_session = f"preflight_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        await memory_system.working_memory.add_message(
            test_session, "preflight", "system", "Preflight check", {}
        )
        results["working_memory"] = {"status": "ok", "details": "SQLite operational"}
    except Exception as e:
        results["working_memory"] = {"status": "error", "details": str(e)}
        all_ok = False
    
    results["all_systems_go"] = all_ok
    
    return results

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )