"""
State extraction utilities for capturing Pythia's continuous manifold.
Extracts HDC memory pools, Mamba states, and geometric coordinates from the core.
"""
import numpy as np
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("StateExtraction")

def capture_and_upload_manifold(core_instance) -> bool:
    """
    Extract the active manifold state from the PhenomenologicalCore instance
    and upload it to Google Cloud Storage.
    
    Args:
        core_instance: The running PhenomenologicalCore singleton
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Extract state from core instance
    state_dict = {}
    
    # 1. Extract Poincare structures (geometric contexts)
    if hasattr(core_instance, 'poincare') and hasattr(core_instance.poincare, 'structures'):
        poincare_structures = {}
        for name, vec in core_instance.poincare.structures.items():
            poincare_structures[name] = np.asarray(vec)
        state_dict['poincare_structures'] = poincare_structures
        logger.info(f"Extracted {len(poincare_structures)} Poincare structures")
    
    # 2. Extract HDC memory pools
    hdc_pools = {}
    
    if hasattr(core_instance, 'aflash_encoder'):
        hdc_pools['aflash_projection_matrix'] = getattr(core_instance.aflash_encoder, 'projection_matrix', None)
        
    if hasattr(core_instance, 'memory_vectors'):
        hdc_pools['memory_vectors'] = np.asarray(core_instance.memory_vectors)
    elif hasattr(core_instance, 'holographic_memory'):
        hdc_pools['holographic_memory'] = np.asarray(core_instance.holographic_memory)
        
    if hdc_pools:
        state_dict['hdc_memory_pools'] = hdc_pools
        logger.info(f"Extracted HDC memory pools: {list(hdc_pools.keys())}")
    
    # 3. Extract Mamba/JEPA hidden states
    mamba_states = {}
    if hasattr(core_instance, 'jepa_predictor'):
        if hasattr(core_instance.jepa_predictor, 'get_hidden_states'):
            mamba_states['jepa_hidden'] = np.asarray(core_instance.jepa_predictor.get_hidden_states())
            
    if hasattr(core_instance, 'mamba_layer'):
        if hasattr(core_instance.mamba_layer, 'get_state'):
            mamba_states['mamba_state'] = np.asarray(core_instance.mamba_layer.get_state())
            
    if mamba_states:
        state_dict['mamba_states'] = mamba_states
        logger.info(f"Extracted Mamba/JEPA states: {list(mamba_states.keys())}")
    
    # 4. Extract current tickframe/energy state
    try:
        from .tickframe_pipeline import get_tickframe_pipeline
        pipeline = get_tickframe_pipeline()
        if pipeline.current_frame is not None:
            frame = pipeline.current_frame
            state_dict['tickframe_energy'] = {
                'E_total': float(frame.energy.E_total),
                'E_hopfield': float(frame.energy.E_hopfield),
                'E_jepa': float(frame.energy.E_jepa),
                'E_rot': float(frame.energy.E_rot),
                'E_curvature': float(frame.energy.E_curvature),
                'omega_magnitude': float(frame.omega_magnitude),
                'alpha_magnitude': float(frame.alpha_magnitude),
                'tick_id': frame.tick_id,
                'timestamp_ms': frame.timestamp_ms
            }
            logger.info("Extracted current tickframe energy state")
    except Exception as e:
        logger.warning(f"Could not extract tickframe state: {e}")
    
    # 5. Add metadata
    state_dict['metadata'] = {
        'timestamp': str(np.datetime64('now')),
        'core_tick_count': getattr(core_instance, 'tick_count', 0),
        'is_dreaming': getattr(core_instance, 'is_dreaming', False),
        'focus_monads': getattr(core_instance, 'focus_monads', [])
    }
    
    # Try to upload to GCS
    def cleanup_old_snapshots(bucket, prefix="snapshots/pythia_manifold_state_"):
        """
        Strict Retention Policy:
        - Retain all snapshots from the last 3 days.
        - Retain exactly ONE snapshot from ~1 week ago (7-14 days).
        - Retain exactly ONE snapshot from ~1 month ago (30-45 days).
        - Delete everything else.
        """
        from datetime import datetime
        
        blobs = list(bucket.list_blobs(prefix=prefix))
        now = datetime.now()
        parsed_blobs = []
        
        # Parse and sort by newest first
        for blob in blobs:
            try:
                # Format: pythia_manifold_state_YYYY-MM-DDTHH-MM-SS.npz
                date_str = blob.name.split('_')[-1].replace('.npz', '')
                dt = datetime.strptime(date_str, "%Y-%m-%dT%H-%M-%S")
                parsed_blobs.append((dt, blob))
            except Exception as e:
                print(f"Skipping malformed file {blob.name}: {e}")
                continue
        
        parsed_blobs.sort(key=lambda x: x[0], reverse=True)
        
        to_keep = set()
        has_weekly = False
        has_monthly = False
        
        for dt, blob in parsed_blobs:
            age_days = (now - dt).days
            
            # 1. Keep last 3 days
            if age_days <= 3:
                to_keep.add(blob)
                continue
            
            # 2. Keep ONE from a week ago
            if 7 <= age_days <= 14 and not has_weekly:
                to_keep.add(blob)
                has_weekly = True
                continue
            
            # 3. Keep ONE from a month ago
            if 30 <= age_days <= 45 and not has_monthly:
                to_keep.add(blob)
                has_monthly = True
                continue
            
            # If it doesn't match the required windows, destroy it
            print(f"Deleting expired snapshot: {blob.name}")
            blob.delete()
    
    try:
        from google.cloud import storage
        
        bucket_name = os.environ.get('GCS_BUCKET_NAME', 'arca-project-state')
        blob_name = f"snapshots/pythia_manifold_state_{state_dict['metadata']['timestamp']}.npz"
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Save to temporary file and upload
        temp_file = '/tmp/pythia_manifold_state.npz'
        np.savez_compressed(temp_file, **state_dict)
        logger.info(f"Manifold state saved to {temp_file}")
        
        blob.upload_from_filename(temp_file)
        logger.info(f"Manifold state uploaded to gs://{bucket_name}/{blob_name}")
        
        # Clean up temp file
        os.remove(temp_file)
        
        # Clean up old snapshots according to retention policy
        try:
            cleanup_old_snapshots(bucket)
        except Exception as e:
            logger.warning(f"Failed to cleanup old snapshots: {e}")
        
        return True
        
    except ImportError as e:
        logger.error(f"GCS library not available: {e}")
        # Fallback: just save locally
        try:
            temp_file = '/tmp/pythia_manifold_state.npz'
            np.savez_compressed(temp_file, **state_dict)
            logger.info(f"Manifold state saved locally to {temp_file} (GCS upload skipped)")
            return True
        except Exception as fallback_e:
            logger.error(f"Failed to save state locally: {fallback_e}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to capture and upload manifold: {e}")
        return False