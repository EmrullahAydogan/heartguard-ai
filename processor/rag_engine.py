"""
HeartGuard AI - RAG Engine
Provides Retrieval-Augmented Generation capabilities.
Uses a local vector database to store and retrieve clinical guidelines
(e.g., AHA/ACC Heart Failure guidelines) to ground MedGemma's reasoning.
"""

import logging
import os
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# Medical guidelines to embed in the vector database
GUIDELINES = [
    {
        "id": "aha_hf_001",
        "title": "AHA 2022 Heart Failure Guidelines - Stage C",
        "content": "For patients with HFrEF and Stage C HF, beta blockers (bisoprolol, carvedilol, or sustained-release metoprolol succinate) are recommended to reduce mortality and hospitalizations."
    },
    {
        "id": "aha_hf_002",
        "title": "AHA 2022 Heart Failure Guidelines - Fluid Overload",
        "content": "In patients with HF who have fluid retention, diuretics are recommended to relieve congestion, improve symptoms, and prevent worsening heart failure. Loop diuretics are preferred."
    },
    {
        "id": "aha_hf_003",
        "title": "AHA 2022 Heart Failure Guidelines - Tachycardia",
        "content": "Resting tachycardia (>100 bpm) in heart failure patients may indicate decompensation, increased sympathetic tone, or concurrent arrhythmias like AFib. Evaluate for underlying causes such as infection, ischemia, or worsening pump failure before titrating beta blockers."
    },
    {
        "id": "aha_hf_004",
        "title": "AHA 2022 Heart Failure Guidelines - Hypoxia",
        "content": "Sudden drops in SpO2 (<90%) in HF patients often indicate pulmonary edema. Supplemental oxygen is recommended, followed by rapid assessment for IV diuretics or vasodilators if blood pressure permits."
    }
]

class ClinicalRAGEngine:
    def __init__(self, db_path="/app/data/chroma_db"):
        self.db_path = db_path
        self.collection_name = "clinical_guidelines"
        
        # Ensure directory exists
        os.makedirs(db_path, exist_ok=True)
        
        # Initialize ChromaDB client (persistent storage)
        self.chroma_client = chromadb.PersistentClient(path=self.db_path)
        
        # Use a lightweight sentence-transformer model for embeddings
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Get or create the collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn
        )
        
        # Populate the database if it's empty
        self._initialize_database()

    def _initialize_database(self):
        """Populate ChromaDB with our medical guidelines if empty."""
        count = self.collection.count()
        if count == 0:
            logger.info("Initializing RAG Vector Database with Clinical Guidelines...")
            
            ids = [g["id"] for g in GUIDELINES]
            documents = [g["content"] for g in GUIDELINES]
            metadatas = [{"title": g["title"]} for g in GUIDELINES]
            
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Successfully embedded {len(GUIDELINES)} guidelines.")
        else:
            logger.info(f"RAG Database already initialized with {count} guidelines.")

    def retrieve_guidelines(self, query: str, n_results: int = 2) -> str:
        """
        Query the vector DB for guidelines relevant to the current patient state.
        Returns a formatted string of the retrieved context.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            if not results["documents"] or not results["documents"][0]:
                return ""
                
            context_blocks = []
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                title = meta.get("title", "Clinical Guideline")
                context_blocks.append(f"[{title}]: {doc}")
                
            return "\n".join(context_blocks)
            
        except Exception as e:
            logger.error(f"Error querying RAG engine: {e}")
            return ""

# Singleton instance for the processor
rag_engine = None

def get_rag_engine():
    global rag_engine
    if rag_engine is None:
        try:
            rag_engine = ClinicalRAGEngine()
        except Exception as e:
            logger.error(f"Failed to initialize RAG Engine: {e}")
    return rag_engine
