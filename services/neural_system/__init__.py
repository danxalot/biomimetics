# Neural System Package
try:
    from .phenomenological_core import PhenomenologicalCore
except ImportError as e:
    print(f"WARNING: Could not import PhenomenologicalCore: {e}")
    PhenomenologicalCore = None
from .system_hash import SystemHash

# Export TickFrame Pipeline
try:
    from .tickframe_pipeline import (
        EnergyTerms,
        TickFrame,
        TickFramePipeline,
        get_pipeline,
    )
except ImportError:
    pass

# Export Koopman Operator
try:
    from .koopman_operator import (
        ConformalPredictor,
        KoopmanMode,
        KoopmanOperator,
        get_conformal_predictor,
        get_koopman,
        get_koopman_operator,
    )
except ImportError:
    pass

# Export Bicameral Reflex
try:
    from .bicameral_reflex import (
        BicameralReflexEngine,
        GenesisHyperSpatial,
        LanguageOfThought,
        Neo4jHDCBridge,
        get_bicameral_engine,
        get_genesis_hyper,
        get_lot,
    )
except ImportError:
    pass

# Export SDM Memory (Kanerva's Sparse Distributed Memory)
try:
    from .sdm_memory import SDMConfig, SDMMemory, SDMMemoryCompact
except ImportError:
    pass

# Export HDC Infinite Memory Systems
try:
    from .hdc_infini_memory import (
        HDCInfiniMemory,
        HDCLongMemory,
        HolographicAccumulator,
        create_memory_system,
    )
except ImportError:
    pass

# Export Hopfield Memory
try:
    from .hopfield_memory import HDCHopfieldMemory
except ImportError:
    pass

# Export Memory Maintainer (Agent Integration Module)
try:
    from .memory_maintainer import (
        AccumulatorChannel,
        MemoryEvent,
        MemoryMaintainer,
        RetrievalResult,
        RetrievalStrategy,
        create_memory_maintainer,
        get_memory_maintainer,
        set_memory_maintainer,
    )
except ImportError:
    pass

__all__ = [
    "SystemHash",
    "PhenomenologicalCore",
    # TickFrame Pipeline
    "TickFrame",
    "EnergyTerms",
    "TickFramePipeline",
    "get_pipeline",
    # Koopman Operator
    "KoopmanOperator",
    "KoopmanMode",
    "ConformalPredictor",
    "get_koopman",
    "get_koopman_operator",
    "get_conformal_predictor",
    # Bicameral Reflex
    "BicameralReflexEngine",
    "LanguageOfThought",
    "GenesisHyperSpatial",
    "Neo4jHDCBridge",
    "get_bicameral_engine",
    "get_lot",
    "get_genesis_hyper",
    # Memory Systems
    "SDMMemory",
    "SDMConfig",
    "SDMMemoryCompact",
    "HDCInfiniMemory",
    "HDCLongMemory",
    "HolographicAccumulator",
    "create_memory_system",
    "HDCHopfieldMemory",
    # Memory Maintainer (Agent Integration)
    "MemoryMaintainer",
    "MemoryEvent",
    "RetrievalResult",
    "RetrievalStrategy",
    "AccumulatorChannel",
    "create_memory_maintainer",
    "get_memory_maintainer",
    "set_memory_maintainer",
]
