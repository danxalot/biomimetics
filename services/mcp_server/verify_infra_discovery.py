from tools.mcp_infra_discovery import infra_discovery
import json

print("=== Testing Infrastructure Discovery ===")
try:
    summary = infra_discovery.discover_from_compose(
        "/app/../docker-compose.local.yml",
        "/app/../.env"
    )
    print("Discovery Summary:")
    print(json.dumps(summary, indent=2))
    
    print("\n=== Testing Query: List All Services ===")
    results = infra_discovery.query_infrastructure("MATCH (s:Service) RETURN s.name as name, s.image as image LIMIT 10")
    print(json.dumps(results, indent=2))
    
    print("\n=== Testing Query: Service with Ports ===")  
    results = infra_discovery.query_infrastructure("""
        MATCH (s:Service)-[:EXPOSES]->(p:Port)
        RETURN s.name as service, p.number as port
        ORDER BY s.name
        LIMIT 10
    """)
    print(json.dumps(results, indent=2))
    
    print("\nSUCCESS: Infrastructure Discovery is functional!")
    
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
