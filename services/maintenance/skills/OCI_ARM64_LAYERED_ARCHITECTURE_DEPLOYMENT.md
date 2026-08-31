---
skill_id: oci_arm64_layered_architecture_deployment
layer: infrastructure
domain: container_management
touchpoints:
  - service: neural_system
    deployment: oci
  - file: docker-compose.oci.yml
  - registry: ghcr.io/danxalot/arca-*
prerequisites:
  - layered_architecture_refactoring_complete
  - oci_instance_access
related_patterns:
  - reasoning_pattern: multi_architecture_builds
geometric_markers:
  - embedding_anchor: "ARM64 layered architecture OCI deployment"
  - embedding_anchor: "multi-architecture container builds"
  - embedding_anchor: "OCI production layered services"
---

# OCI ARM64 Layered Architecture Deployment

**Status**: Pending Implementation
**Priority**: High
**Last Updated**: January 29, 2026

---

## 1. Context & Current State

### OCI Services Defined (15 total in docker-compose.oci.yml):
```yaml
# Core ARCA Services (ARM64 optimization candidates)
- neural_system:layered          # ← Uses layered arch, needs ARM64
- reflexive_amygdala:latest      # Standard service
- dreaming_consolidator:latest   # Standard service  
- td_jepa:latest                # Standard service
- geometry_kernel:arm64         # ✅ Already has ARM64
- host_bridge_oci:latest        # Standard service
- mcp_client_oci:latest         # Standard service

# Infrastructure Services (Third-party)
- dragonfly                     # Redis replacement
- qdrant                       # Vector database
- neo4j                        # Graph database
- oci_builder                  # Docker-in-Docker
```

### Issue Identified:
- **neural_system:layered** is the only layered service in OCI deployment
- Currently **no ARM64 support** for layered architecture components
- Missing: `arca-base-python:arm64`, `arca-middleware:arm64`

---

## 2. ARM64 Build Requirements

### Phase 1: Base Layer ARM64 Support
```bash
# Build base Python layer for ARM64
docker buildx build --platform linux/arm64 \
  -t ghcr.io/danxalot/arca-base-python:arm64 \
  -f layers/base-python/Dockerfile layers/base-python/ \
  --push

# Build middleware layer for ARM64
docker buildx build --platform linux/arm64 \
  -t ghcr.io/danxalot/arca-middleware:arm64 \
  -f layers/middleware/Dockerfile layers/middleware/ \
  --push
```

### Phase 2: Service-Specific ARM64 Builds
```bash
# Build neural_system ARM64 variant
docker buildx build --platform linux/arm64 \
  -t ghcr.io/danxalot/arca-neural_system:arm64 \
  -f services/neural_system/Dockerfile services/neural_system/ \
  --push
```

---

## 3. OCI Deployment Status Verification

### Required Actions:
1. **Verify current OCI status**: Check which services are actually running
2. **Resource assessment**: ARM64 performance vs. AMD64 on OCI Ampere
3. **Deployment strategy**: Rolling update vs. blue-green for layered services

### Verification Commands:
```bash
# SSH to OCI instance (method TBD)
ssh oci-instance "docker ps --format 'table {{.Names}}\t{{.Status}}'"

# Check resource usage
ssh oci-instance "docker system df"
```

---

## 4. Implementation Plan

### Priority 1: Establish ARM64 Layered Foundation
- [ ] Locate or create base-python Dockerfile for ARM64 builds
- [ ] Build and push arca-base-python:arm64
- [ ] Build and push arca-middleware:arm64
- [ ] Test ARM64 layered build process

### Priority 2: OCI-Specific Service Builds  
- [ ] Build neural_system:arm64 using layered architecture
- [ ] Update OCI compose to use ARM64 variants where appropriate
- [ ] Verify OCI instance can pull and run ARM64 images

### Priority 3: Production Deployment
- [ ] Coordinate OCI deployment window
- [ ] Deploy ARM64 layered services to OCI
- [ ] Monitor performance and resource utilization
- [ ] Document ARM64 vs. AMD64 performance characteristics

---

## 5. Decision Points

### Architecture Questions:
1. **Should other OCI services be migrated to layered architecture?**
   - reflexive_amygdala, dreaming_consolidator, td_jepa are ~259MB-1GB
   - May not benefit significantly from layered approach

2. **ARM64 performance on OCI Ampere A1?**
   - Need baseline performance metrics for comparison
   - Evaluate ML workload performance on ARM64 vs. AMD64

3. **Multi-arch registry strategy?**
   - Use ARM64-specific tags or manifest lists?
   - Current: geometry_kernel:arm64 (tag-based)
   - Alternative: Use Docker manifest lists for automatic selection

---

## 6. Success Criteria

- [ ] OCI neural_system service running ARM64 layered image (1.38GB)
- [ ] Performance parity or improvement vs. current deployment  
- [ ] Automated ARM64 build pipeline established
- [ ] Documentation updated with ARM64 deployment procedures

---

## 7. Rollback Strategy

```bash
# Revert OCI services to AMD64 versions
docker-compose -f docker-compose.oci.yml down
# Update compose file to use :latest tags instead of :arm64
docker-compose -f docker-compose.oci.yml up -d
```

**Next Action**: Determine current OCI service status and locate/create base layer Dockerfiles for ARM64 builds.