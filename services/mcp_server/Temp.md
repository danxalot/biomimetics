Compose Services Audit
This audit provides a complete list of services defined in the 
local
 and OCI environment configurations.

Local Environment (
docker-compose.local.yml
)
The local stack focuses on core infrastructure and cognitive agents for development and testing.

Category	Services
Infrastructure	postgres, redis, neo4j, rabbitmq, host_bridge
Inference (Vulkan)	llama_0, llama_1
Intelligence Layer	memory_system, embedding_service, llm_gateway, mcp_server
Cognitive Agents	agent_service, user_interaction_agent, maintainer_agents, secondary_maintainer, geometry_kernel
Observer & Ops	observer_agent, resource_monitor, mcp_client, docker_helper
Observability	loki, grafana
OCI Environment (
docker-compose.oci.yml
)
The OCI production configuration is optimized for the Neural System stack.

Category	Services
Neural System Core	neural_system, reflexive_amygdala, dreaming_consolidator, td_jepa, geometry_kernel, host_bridge_oci
Persistence	dragonfly, qdrant, neo4j
Ops & Connectivity	mcp_client_oci, oci_builder
OCI Build Environment (
docker-compose.oci_build.yml
)
Additional services used in the OCI build and specialized inference context.

llama_cpp (The Mind)
pythia_oracle (The Noumenal Engine)
geometry_kernel (The Mount)
conversational_hdc (The Manifold)
td_jepa (The Predictor)
oracle_db (Persistent Storage)
mcp_server (The Coordinator)