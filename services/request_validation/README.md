# Request Validation Module

**Purpose**: Prevent quota waste during development while ensuring production calls are legitimate.

**Key Feature**: `ValidatedModelCall` - The ONLY way to call models in ARCA.

---

## Quick Start

```python
from request_validation import ValidatedModelCall

# Test without consuming quota:
response = ValidatedModelCall.generate_content(
    origin_agent="Architect",
    model="gemini-2.5-pro",
    prompt="Your prompt",
    estimated_tokens=1000,
    dry_run=True  # ← No quota consumed
)

# Production with validation:
response = ValidatedModelCall.generate_content(
    origin_agent="Architect",
    model="gemini-2.5-pro",
    prompt="Your prompt",
    estimated_tokens=1000,
    dry_run=False  # ← Quota consumed after validation
)
```

---

## Why This Matters

**Problem**: Development and testing could waste expensive API quota
**Solution**: ValidatedModelCall wrapper with dry-run capability
**Benefit**: Test entire system with zero quota cost

---

## Architecture

### Multi-Stage Validation Pipeline

Every request passes through 5 validation stages:

```
Request
  ↓
1. Basic Validation (format, fields)
  ↓
2. Origin Verification (agent recognized?)
  ↓
3. Signature Check (cryptographic proof)
  ↓
4. Quota Check (agent has budget?)
  ↓
5. Model Check (model available?)
  ↓
Result: PASS or FAIL
  ↓
If PASS:
  ├─ DRY_RUN → Return cached response (zero quota)
  └─ VALIDATED → Make real API call (quota consumed)
```

### ProvenanceLevel Enum

- **UNVALIDATED**: Request not yet checked
- **DRY_RUN**: Test mode, no quota consumed
- **VALIDATED**: Passed validation, quota will be consumed
- **SYSTEM**: Internal system calls, bypass validation
- **EMERGENCY**: Fallback mode, minimal validation

### Request Context

Every request tracked with:
- Origin agent (who called this?)
- Model name
- Prompt/content
- Estimated tokens
- Dry-run status
- Timestamp
- Validation chain (all steps and results)

---

## Files

### provenance_validator.py
Implements the validation pipeline:
- `ProvenanceLevel` enum
- `RequestContext` dataclass
- `ProvenanceValidator` class with multi-stage validation
- Signature verification (HMAC-SHA256)
- Quota tracking
- Known agent registry
- `get_validator()` factory function

### validated_model_call.py
Implements the mandatory wrapper:
- `ValidatedModelCall` class
- `generate_content()` method (Google Gemini)
- `embed_content()` method (Google Gemini)
- Provider support (Google, Ollama)
- Dry-run response generation
- `ValidationTracker` for global tracking
- Audit trail recording

### __init__.py
Module public API:
- Exports: ProvenanceValidator, ValidatedModelCall, ValidationTracker
- Usage documentation
- Examples

---

## Usage Patterns

### Pattern 1: Generate Content (Gemini LLM)

```python
from request_validation import ValidatedModelCall

response = ValidatedModelCall.generate_content(
    origin_agent="Architect",        # Required: Which agent?
    model="gemini-2.5-pro",          # Required: Which model?
    prompt="Analyze this data",      # Required: The request
    estimated_tokens=1500,           # Required: Quota estimate
    dry_run=False                    # Required: Real or test?
)

# Access response
text = response.text
tokens = response.usage_metadata.output_tokens if hasattr(response, 'usage_metadata') else 0
```

### Pattern 2: Generate Embeddings

```python
from request_validation import ValidatedModelCall

embedding = ValidatedModelCall.embed_content(
    origin_agent="EmbeddingService",
    model="embedding-001",
    content="Text to embed",
    estimated_tokens=100,
    dry_run=False
)

# Access embedding
vector = embedding.embedding  # List of floats
```

### Pattern 3: Development/Testing (Zero Quota)

```python
# During development, use dry_run=True
response = ValidatedModelCall.generate_content(
    origin_agent="Architect",
    model="gemini-2.5-pro",
    prompt="Test prompt",
    estimated_tokens=1000,
    dry_run=True  # ← Zero quota consumed!
)

# Same interface, but cached response
assert response is not None
assert len(response.text) > 0
```

### Pattern 4: Check Quota Usage

```python
from request_validation import ValidationTracker

tracker = ValidationTracker()

# After making requests...
stats = tracker.get_stats()

print(f"Dry-run requests: {stats['dry_run_count']}")
print(f"Real requests: {stats['real_request_count']}")
print(f"Quota consumed: {stats['total_tokens_consumed']}")
print(f"Estimated quota: {stats['total_tokens_estimated']}")
print(f"Money saved by dry-run: ${(stats['total_tokens_estimated'] - stats['total_tokens_consumed']) * 0.000002:.4f}")
```

---

## Response Format

All model calls return a response object with **actual token tracking**:

```python
response = ValidatedModelCall.generate_content(
    origin_agent="Architect",
    model="gemini-2.5-pro",
    prompt="Your prompt",
    estimated_tokens=1000,  # For quota pre-checks
    dry_run=False
)

# Response includes ACTUAL token usage (takes precedence):
print(response["tokens_estimated"])  # What we thought: 1000
print(response["tokens_actual"])     # What API actually used: 892
print(response["tokens_variance"])   # Difference: -108 tokens
```

**Why This Matters**:
- ✅ Estimated tokens used only for pre-checks (don't affect output)
- ✅ Actual tokens from API response take precedence for billing
- ✅ Variance tracked to improve estimation accuracy
- ✅ No arbitrary values affecting request or output

### Known Agents

Edit `provenance_validator.py` to add/modify agents:

```python
KNOWN_AGENTS = {
    "Architect": {
        "tier": "premium",
        "quota_tokens_per_minute": 20000,
        "description": "System architect for complex analysis"
    },
    "MyCustomAgent": {
        "tier": "standard",
        "quota_tokens_per_minute": 10000,
        "description": "Custom agent description"
    }
}
```

### Environment Variables

```bash
# Required
GOOGLE_API_KEY=your-key-here

# Optional but recommended
ARCA_PROVENANCE_SECRET=min-32-chars-secret-key
OLLAMA_BASE_URL=http://localhost:11435  # For local models
```

---

## Testing

### Test Dry-Run (Zero Quota)

```python
def test_dry_run():
    tracker = ValidationTracker()
    initial = tracker.get_stats()['total_tokens_consumed']
    
    response = ValidatedModelCall.generate_content(
        origin_agent="Architect",
        model="gemini-2.5-pro",
        prompt="test",
        estimated_tokens=100,
        dry_run=True
    )
    
    final = tracker.get_stats()['total_tokens_consumed']
    assert final == initial, "Dry-run consumed quota!"
    print("✅ Dry-run test passed")
```

---

## Integration

See [REQUEST_VALIDATION_INTEGRATION_GUIDE.md](../../REQUEST_VALIDATION_INTEGRATION_GUIDE.md) for detailed integration instructions.

**Module Version**: 1.0
**Status**: Production Ready ✅
