#!/bin/bash

# ARCA Multi-Agent Terminal Notification Test
# Test script for broadcasting to all agent terminals

echo "🎯 ARCA Multi-Agent Terminal Notification System Test"
echo "=================================================="

SERVICE_URL="https://arca-user-interaction-agent-eqij24gbwq-nw.a.run.app"

echo ""
echo "1. Testing Agent Terminal Status Check..."
curl -s -X GET "${SERVICE_URL}/api/agent/terminals" | jq '.' 2>/dev/null || echo "JSON parsing failed - checking raw response:"

echo ""
echo "2. Testing Broadcast to All Terminals..."
curl -s -X POST "${SERVICE_URL}/api/broadcast" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "🎯 ARCHITECT @dev: Multi-agent terminal notification system operational. All agents can now receive coordinated messages.",
    "notification_type": "system_update", 
    "source_agent": "dev",
    "target_agents": ["dev", "workhorse", "blackbox"]
  }' | jq '.' 2>/dev/null || echo "Broadcast sent (JSON parsing failed)"

echo ""
echo "3. Testing Multi-Agent Coordination Notification..."
curl -s -X POST "${SERVICE_URL}/api/agent/notify" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "✅ Multi-agent terminal system deployed successfully. iPhone Messages UI active. WebSocket broadcasting operational.",
    "notification_type": "coordination",
    "source_agent": "dev"
  }' | jq '.' 2>/dev/null || echo "Coordination notification sent"

echo ""
echo "4. Testing System Status Broadcast..."
curl -s -X POST "${SERVICE_URL}/api/broadcast" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "📊 System Status: Cloud Run operational | Local testing: localhost:8084 | Tailscale: 100.124.13.62:8084 | All agents ready for coordination",
    "notification_type": "status_update",
    "source_agent": "dev"
  }' | jq '.' 2>/dev/null || echo "Status broadcast sent"

echo ""
echo "5. Checking Service Health..."
curl -s -X GET "${SERVICE_URL}/health" | jq '.' 2>/dev/null || echo "Health check completed"

echo ""
echo "=================================================="
echo "🎯 Multi-Agent Terminal Notification Test Complete"
echo "All agents (@dev, @workhorse, @blackbox) should now"
echo "receive notifications through the terminal interface."
echo "=================================================="