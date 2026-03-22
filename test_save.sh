#!/bin/bash

# Test the save_to_notion functionality
TITLE="Test Travel Peru"
CATEGORY="travel"
CONTENT="# Peru Travel Itinerary\n\n## Day 1\n- Lima\n- Cusco\n- Machu Picchu"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
FNAME="${CATEGORY}/${TITLE,,}"
FNAME="${FNAME// /-}"
FNAME="${FNAME}-${TIMESTAMP//[ :]/-}"

echo "Title: $TITLE"
echo "Category: $CATEGORY"
echo "Timestamp: $TIMESTAMP"
echo "Filename: $FNAME"
echo "Content length: ${#CONTENT}"

# Test the actual API call that save_to_notion makes
echo -e "\nTesting API call:"
RESPONSE=$(curl -s -X PUT "http://127.0.0.1:8088/api/agent/memory/${FNAME}" \
  -H "Content-Type: text/plain" \
  -d "# ${TITLE}

**Category**: ${CATEGORY}
**Created**: ${TIMESTAMP}

${CONTENT}" -w "\nHTTP Status: %{http_code}\n")

echo "$RESPONSE"

# Also test with JSON
echo -e "\nTesting with JSON wrapper:"
RESPONSE2=$(curl -s -X PUT "http://127.0.0.1:8088/api/agent/memory/${FNAME}-json" \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"# ${TITLE}

**Category**: ${CATEGORY}
**Created**: ${TIMESTAMP}

${CONTENT}\"}" -w "\nHTTP Status: %{http_code}\n")

echo "$RESPONSE2"