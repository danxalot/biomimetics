# Document Upload & Retrieval for User Interaction Terminal

import os
import aiofiles
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class DocumentHandler:
    '''Document upload and retrieval for MiniMax reasoning integration'''
    
    def __init__(self):
        self.upload_dir = Path("/home/ubuntu/mcp_storage/ARCA/user_documents")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        print(f"✅ DocumentHandler initialized: {self.upload_dir}")
    
    async def upload_document(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        '''Upload document and return document_id and local_path'''
        doc_hash = hashlib.sha256(file_content).hexdigest()[:16]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"doc_{timestamp}_{doc_hash}"
        local_path = self.upload_dir / f"{doc_id}_{filename}"
        
        async with aiofiles.open(local_path, 'wb') as f:
            await f.write(file_content)
        
        return {"status": "uploaded", "document_id": doc_id, "local_path": str(local_path)}
    
    async def retrieve_document(self, local_path: str) -> str:
        '''Retrieve document content by path'''
        async with aiofiles.open(local_path, 'r') as f:
            return await f.read()
