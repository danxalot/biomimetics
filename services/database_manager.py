"""
ARCA Multi-Database Configuration Service
Manages 50GB Neo4j + 2x20GB Oracle DBs + 1GB Firestore architecture
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio

# Database connection libraries
import oracledb
import neo4j
from google.cloud import firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration for multi-DB architecture"""
    name: str
    type: str  # 'oracle', 'neo4j', 'firestore'
    connection_string: str
    max_storage_gb: int
    current_usage_gb: float = 0.0
    egress_limit_gb: Optional[float] = None
    
class MultiDatabaseManager:
    """Manages the multi-database architecture with intelligent routing"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.join(os.getenv('ARCA_ROOT', '.'), '.secrets', 'database_config.json')
        self.databases = {}
        self.firestore_client = None
        self.neo4j_driver = None
        self.oracle_connections = {}
        
        # Load configuration
        self._load_config()
        
    def _load_config(self):
        """Load database configuration"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)
                    
                for db_config in config_data.get('databases', []):
                    self.databases[db_config['name']] = DatabaseConfig(**db_config)
            else:
                # Create default configuration
                self._create_default_config()
                
        except Exception as e:
            logger.error(f"Error loading database config: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default multi-database configuration"""
        
        # Get connection details from environment/secrets
        oracle_host = os.getenv('ORACLE_DB_HOST', 'arcadb01_high')
        oracle_user = os.getenv('ORACLE_DB_USER', 'ADMIN')
        oracle_password = os.getenv('ORACLE_DB_PASSWORD')
        
        neo4j_uri = os.getenv('NEO4J_URI', 'bolt://10.0.2.217:7687')
        neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        neo4j_password = os.getenv('NEO4J_PASSWORD')
        
        gcp_project = os.getenv('GCP_PROJECT_ID', 'arca-471022')
        
        default_config = {
            'databases': [
                {
                    'name': 'oracle_primary',
                    'type': 'oracle',
                    'connection_string': f'oracle://{oracle_user}:{oracle_password}@{oracle_host}',
                    'max_storage_gb': 20,
                    'current_usage_gb': 0.0
                },
                {
                    'name': 'oracle_secondary', 
                    'type': 'oracle',
                    'connection_string': f'oracle://{oracle_user}:{oracle_password}@arcadb02_high',
                    'max_storage_gb': 20,
                    'current_usage_gb': 0.0
                },
                {
                    'name': 'neo4j_main',
                    'type': 'neo4j', 
                    'connection_string': f'neo4j://{neo4j_user}:{neo4j_password}@10.0.2.217:7687',
                    'max_storage_gb': 50,
                    'current_usage_gb': 0.0
                },
                {
                    'name': 'firestore_metadata',
                    'type': 'firestore',
                    'connection_string': f'firestore://{gcp_project}',
                    'max_storage_gb': 1,
                    'current_usage_gb': 0.0,
                    'egress_limit_gb': 1.0  # 1GB/month egress limit
                }
            ],
            'routing_rules': {
                'vector_embeddings': ['oracle_primary', 'oracle_secondary'],
                'document_metadata': ['firestore_metadata'],
                'knowledge_graph': ['neo4j_main'],
                'full_text_search': ['oracle_primary'],
                'user_preferences': ['firestore_metadata'],
                'system_config': ['firestore_metadata']
            },
            'sync_settings': {
                'oracle_replication': True,
                'firestore_egress_optimization': True,
                'neo4j_backup_to_oracle': False
            }
        }
        
        # Save configuration
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
            
        # Load the saved config
        self.databases = {
            db['name']: DatabaseConfig(**db) for db in default_config['databases']
        }
        
        logger.info("Created default multi-database configuration")
    
    async def initialize_connections(self):
        """Initialize connections to all databases"""
        try:
            # Initialize Firestore with knowledge_corpus database
            self.firestore_client = firestore.Client(database='knowledge_corpus')
            logger.info("✅ Firestore connection initialized (knowledge_corpus database)")
            
            # Initialize Neo4j
            neo4j_config = self.databases.get('neo4j_main')
            if neo4j_config:
                # Parse connection string
                uri = neo4j_config.connection_string.replace('neo4j://', 'bolt://')
                # Extract credentials (simplified - use proper URI parsing in production)
                user = os.getenv('NEO4J_USER', 'neo4j')
                password = os.getenv('NEO4J_PASSWORD')
                
                self.neo4j_driver = neo4j.GraphDatabase.driver(
                    uri, auth=(user, password)
                )
                
                # Test connection
                with self.neo4j_driver.session() as session:
                    result = session.run("RETURN 1 as test")
                    if result.single():
                        logger.info("✅ Neo4j connection initialized")
            
            # Initialize Oracle connections
            oracle_configs = [db for db in self.databases.values() if db.type == 'oracle']
            
            for oracle_config in oracle_configs:
                try:
                    # Parse Oracle connection (simplified)
                    host = oracle_config.connection_string.split('@')[1]
                    user = os.getenv('ORACLE_DB_USER', 'ADMIN')
                    password = os.getenv('ORACLE_DB_PASSWORD')
                    
                    # Create connection pool
                    pool = oracledb.create_pool(
                        user=user,
                        password=password,
                        dsn=host,
                        min=1,
                        max=5,
                        increment=1
                    )
                    
                    self.oracle_connections[oracle_config.name] = pool
                    logger.info(f"✅ Oracle connection initialized: {oracle_config.name}")
                    
                except Exception as e:
                    logger.error(f"Failed to connect to Oracle {oracle_config.name}: {e}")
            
        except Exception as e:
            logger.error(f"Error initializing database connections: {e}")
            raise
    
    def route_data(self, data_type: str, operation: str = 'read') -> List[str]:
        """Route data to appropriate databases based on type and operation"""
        
        routing_rules = {
            'vector_embeddings': {
                'read': ['oracle_primary'],  # Primary for reads
                'write': ['oracle_primary', 'oracle_secondary']  # Both for writes (replication)
            },
            'document_metadata': {
                'read': ['firestore_metadata'],
                'write': ['firestore_metadata']
            },
            'knowledge_graph': {
                'read': ['neo4j_main'],
                'write': ['neo4j_main']
            },
            'full_text_chunks': {
                'read': ['oracle_primary'],
                'write': ['oracle_primary']
            },
            'user_sessions': {
                'read': ['firestore_metadata'],
                'write': ['firestore_metadata']
            }
        }
        
        return routing_rules.get(data_type, {}).get(operation, ['firestore_metadata'])
    
    def check_storage_usage(self) -> Dict[str, Dict[str, float]]:
        """Check current storage usage across all databases"""
        usage_report = {}
        
        for db_name, db_config in self.databases.items():
            usage_report[db_name] = {
                'current_gb': db_config.current_usage_gb,
                'max_gb': db_config.max_storage_gb,
                'utilization_percent': (db_config.current_usage_gb / db_config.max_storage_gb) * 100,
                'egress_limit_gb': db_config.egress_limit_gb
            }
        
        return usage_report
    
    def optimize_firestore_egress(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize Firestore queries to minimize egress"""
        
        # Only fetch essential metadata from Firestore
        essential_fields = [
            'document_id', 'title', 'created_at', 'updated_at', 
            'status', 'tags', 'summary'
        ]
        
        # Remove large fields that should be in Oracle/Neo4j
        optimized_query = {
            k: v for k, v in query_data.items() 
            if k in essential_fields
        }
        
        logger.info(f"Optimized Firestore query: reduced from {len(query_data)} to {len(optimized_query)} fields")
        
        return optimized_query
    
    async def sync_databases(self):
        """Synchronize data between databases where needed"""
        try:
            # Sync Oracle primary -> secondary (vector embeddings)
            await self._sync_oracle_replication()
            
            # Update metadata in Firestore (minimal data)
            await self._sync_firestore_metadata()
            
            # Backup critical Neo4j data to Oracle (optional)
            # await self._backup_neo4j_to_oracle()
            
            logger.info("✅ Database synchronization completed")
            
        except Exception as e:
            logger.error(f"Error during database sync: {e}")
    
    async def _sync_oracle_replication(self):
        """Replicate vector data from primary to secondary Oracle DB"""
        # Implementation would depend on your vector storage schema
        logger.info("Oracle replication sync - placeholder")
    
    async def _sync_firestore_metadata(self):
        """Sync minimal metadata to Firestore (respecting egress limits)"""
        # Only sync essential document metadata, not full content
        logger.info("Firestore metadata sync - placeholder")
    
    def get_database_health(self) -> Dict[str, str]:
        """Check health status of all databases"""
        health_status = {}
        
        for db_name, db_config in self.databases.items():
            try:
                if db_config.type == 'firestore' and self.firestore_client:
                    # Test Firestore connection
                    test_doc = self.firestore_client.collection('_health').document('test')
                    test_doc.set({'timestamp': datetime.now(timezone.utc).isoformat()})
                    health_status[db_name] = 'healthy'
                    
                elif db_config.type == 'neo4j' and self.neo4j_driver:
                    # Test Neo4j connection
                    with self.neo4j_driver.session() as session:
                        session.run("RETURN 1")
                    health_status[db_name] = 'healthy'
                    
                elif db_config.type == 'oracle' and db_name in self.oracle_connections:
                    # Test Oracle connection
                    pool = self.oracle_connections[db_name]
                    with pool.acquire() as connection:
                        cursor = connection.cursor()
                        cursor.execute("SELECT 1 FROM DUAL")
                        cursor.fetchone()
                    health_status[db_name] = 'healthy'
                    
                else:
                    health_status[db_name] = 'not_connected'
                    
            except Exception as e:
                health_status[db_name] = f'error: {str(e)}'
        
        return health_status
    
    async def close_connections(self):
        """Close all database connections"""
        try:
            # Close Neo4j
            if self.neo4j_driver:
                await self.neo4j_driver.close()
                
            # Close Oracle pools
            for pool in self.oracle_connections.values():
                pool.close()
                
            logger.info("✅ All database connections closed")
            
        except Exception as e:
            logger.error(f"Error closing connections: {e}")


async def main():
    """Test the multi-database manager"""
    
    # Initialize manager
    db_manager = MultiDatabaseManager()
    
    try:
        # Initialize connections
        await db_manager.initialize_connections()
        
        # Check storage usage
        usage = db_manager.check_storage_usage()
        print("\n=== Storage Usage Report ===")
        for db_name, stats in usage.items():
            print(f"{db_name}: {stats['current_gb']:.1f}GB / {stats['max_gb']}GB ({stats['utilization_percent']:.1f}%)")
        
        # Check database health
        health = db_manager.get_database_health()
        print("\n=== Database Health ===")
        for db_name, status in health.items():
            print(f"{db_name}: {status}")
        
        # Test routing
        vector_dbs = db_manager.route_data('vector_embeddings', 'write')
        metadata_dbs = db_manager.route_data('document_metadata', 'read')
        
        print(f"\n=== Routing Test ===")
        print(f"Vector embeddings (write) -> {vector_dbs}")
        print(f"Document metadata (read) -> {metadata_dbs}")
        
    finally:
        await db_manager.close_connections()

if __name__ == '__main__':
    asyncio.run(main())