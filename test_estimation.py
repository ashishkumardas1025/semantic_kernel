import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, Union, List
import warnings
import os
import pandas as pd
import chromadb
from chromadb.config import Settings
import uuid
from pathlib import Path
import numpy as np
from datetime import datetime

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration
CLAUDE_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
SAMPLE_ESTIMATIONS_DIR = "Sample Estimations"  # Directory containing .xlsx files
CHROMA_DB_PATH = "./chroma_db"  # Local ChromaDB path

class CapabilityLookupSystem:
    def __init__(self):
        """Initialize the capability lookup system"""
        self.bedrock_client = self._initialize_bedrock_client()
        self.chroma_client = self._initialize_chroma_client()
        self.collection = self._get_or_create_collection()
        
    def _initialize_bedrock_client(self):
        """Initialize and return AWS Bedrock client with credentials from environment variables"""
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        bedrock = session.client(
            service_name='bedrock-runtime', 
            region_name='us-east-1', 
            verify=False
        )
        return bedrock

    def _initialize_chroma_client(self):
        """Initialize ChromaDB client"""
        return chromadb.PersistentClient(path=CHROMA_DB_PATH)

    def _get_or_create_collection(self):
        """Get or create ChromaDB collection for capability data"""
        try:
            collection = self.chroma_client.get_collection(name="capability_chunks")
        except:
            collection = self.chroma_client.create_collection(name="capability_chunks")
        return collection

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using Amazon Titan Embed model"""
        try:
            request_payload = {
                "inputText": text,
                "dimensions": 1024,
                "normalize": True
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=TITAN_EMBED_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_payload).encode("utf-8")
            )
            
            response_body = json.loads(response["body"].read().decode("utf-8"))
            return response_body["embedding"]
            
        except ClientError as e:
            print(f"AWS Error generating embedding: {e}")
            raise
        except Exception as e:
            print(f"General Error generating embedding: {e}")
            raise

    def invoke_claude(self, prompt: str, system: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.1) -> str:
        """Invoke Claude model through AWS Bedrock"""
        request_payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ]
        }
        
        if system:
            request_payload["system"] = system
            
        try:
            response = self.bedrock_client.invoke_model(
                modelId=CLAUDE_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_payload).encode("utf-8")
            )
            response_body = json.loads(response["body"].read().decode("utf-8"))
            return response_body["content"][0]["text"]
        except ClientError as e:
            print(f"AWS Error invoking Claude: {e}")
            raise
        except Exception as e:
            print(f"General Error invoking Claude: {e}")
            raise

    def scan_and_index_excel_files(self):
        """Scan Sample Estimations directory and index all Excel files"""
        print(f"Scanning directory: {SAMPLE_ESTIMATIONS_DIR}")
        
        if not os.path.exists(SAMPLE_ESTIMATIONS_DIR):
            print(f"Directory {SAMPLE_ESTIMATIONS_DIR} does not exist!")
            return
        
        excel_files = list(Path(SAMPLE_ESTIMATIONS_DIR).glob("*.xlsx"))
        print(f"Found {len(excel_files)} Excel files to process")
        
        for excel_file in excel_files:
            try:
                print(f"Processing file: {excel_file.name}")
                self._process_excel_file(excel_file)
            except Exception as e:
                print(f"Error processing {excel_file.name}: {e}")
                continue
        
        print("Indexing completed!")

    def _process_excel_file(self, excel_file_path: Path):
        """Process a single Excel file and extract capability data"""
        try:
            # Read the Capability List sheet
            df = pd.read_excel(excel_file_path, sheet_name="Capability List")
            
            # Ensure required columns exist
            required_columns = ["Capability", "Scope / Business Description", "System Changes"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                print(f"Missing columns in {excel_file_path.name}: {missing_columns}")
                return
            
            # Clean the data
            df = df.dropna(subset=["Capability"])  # Remove rows without capability
            
            # Process each row as a chunk
            for index, row in df.iterrows():
                self._create_and_store_chunk(row, excel_file_path, index)
                
        except Exception as e:
            print(f"Error reading Excel file {excel_file_path.name}: {e}")
            raise

    def _create_and_store_chunk(self, row: pd.Series, file_path: Path, row_index: int):
        """Create a text chunk from a row and store it in ChromaDB"""
        try:
            # Create chunk text
            capability = str(row.get("Capability", "")).strip()
            scope_description = str(row.get("Scope / Business Description", "")).strip()
            system_changes = str(row.get("System Changes", "")).strip()
            
            # Skip empty rows
            if not capability or capability.lower() == 'nan':
                return
            
            # Create comprehensive text for embedding
            chunk_text = f"Capability: {capability}\n"
            if scope_description and scope_description.lower() != 'nan':
                chunk_text += f"Scope/Business Description: {scope_description}\n"
            if system_changes and system_changes.lower() != 'nan':
                chunk_text += f"System Changes: {system_changes}"
            
            # Generate embedding
            embedding = self.generate_embedding(chunk_text)
            
            # Create unique ID
            chunk_id = str(uuid.uuid4())
            
            # Prepare metadata
            metadata = {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "sheet_name": "Capability List",
                "row_index": row_index,
                "capability": capability,
                "scope_description": scope_description,
                "system_changes": system_changes,
                "indexed_at": datetime.now().isoformat()
            }
            
            # Store in ChromaDB
            self.collection.add(
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[metadata],
                ids=[chunk_id]
            )
            
        except Exception as e:
            print(f"Error creating chunk for row {row_index}: {e}")
            raise

    def query_similar_capabilities(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query ChromaDB for similar capabilities"""
        try:
            # Generate embedding for query
            query_embedding = self.generate_embedding(query)
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            for i in range(len(results["documents"][0])):
                formatted_results.append({
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i]
                })
            
            return formatted_results
            
        except Exception as e:
            print(f"Error querying capabilities: {e}")
            raise

    def generate_capability_summary(self, capability_data: Dict[str, Any]) -> str:
        """Generate a concise summary using Claude"""
        metadata = capability_data["metadata"]
        
        prompt = f"""
        Based on the following capability information, provide a concise summary:
        
        Capability: {metadata.get('capability', 'N/A')}
        Scope/Business Description: {metadata.get('scope_description', 'N/A')}
        System Changes: {metadata.get('system_changes', 'N/A')}
        
        Please provide a brief, informative summary that captures the key aspects of this capability and its business impact.
        """
        
        system_prompt = "You are a business analyst summarizing capability information. Provide clear, concise summaries that highlight business value and technical changes."
        
        try:
            summary = self.invoke_claude(prompt, system=system_prompt, max_tokens=200)
            return summary.strip()
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Summary generation failed for capability: {metadata.get('capability', 'Unknown')}"

    def search_capabilities(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """Main search function that returns formatted results"""
        try:
            # Query similar capabilities
            similar_capabilities = self.query_similar_capabilities(query, top_k=5)
            
            # Limit to max_results
            similar_capabilities = similar_capabilities[:max_results]
            
            # Generate summaries and format results
            results = []
            for capability_data in similar_capabilities:
                metadata = capability_data["metadata"]
                
                # Generate summary
                summary = self.generate_capability_summary(capability_data)
                
                # Create source link
                source_link = f"file://{metadata['file_path']}#sheet={metadata['sheet_name']}&row={metadata['row_index']}"
                
                results.append({
                    "summary": summary,
                    "sourceLink": source_link,
                    "capability": metadata.get('capability', 'N/A'),
                    "fileName": metadata['file_name'],
                    "distance": capability_data["distance"]
                })
            
            return {
                "query": query,
                "results": results,
                "total_found": len(similar_capabilities),
                "search_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error searching capabilities: {e}")
            return {
                "query": query,
                "results": [],
                "error": str(e),
                "search_timestamp": datetime.now().isoformat()
            }

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the indexed data"""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": "capability_chunks",
                "database_path": CHROMA_DB_PATH
            }
        except Exception as e:
            return {"error": str(e)}


# Usage example and main functions
def main():
    """Main function to demonstrate the capability lookup system"""
    print("Initializing Capability Lookup System...")
    
    # Initialize the system
    lookup_system = CapabilityLookupSystem()
    
    # Check if we need to index files
    stats = lookup_system.get_collection_stats()
    print(f"Current database stats: {stats}")
    
    # Index files if the collection is empty
    if stats.get("total_chunks", 0) == 0:
        print("No indexed data found. Starting indexing process...")
        lookup_system.scan_and_index_excel_files()
    else:
        print(f"Found {stats['total_chunks']} existing chunks in database")
    
    # Example queries
    sample_queries = [
        "review current consent",
        "mutual funds product selection",
        "onboarding process enhancement",
        "customer entitlement management"
    ]
    
    print("\nTesting sample queries:")
    for query in sample_queries:
        print(f"\n--- Query: '{query}' ---")
        results = lookup_system.search_capabilities(query)
        print(json.dumps(results, indent=2))


def search_capability_command(query: str):
    """Command-line interface for searching capabilities"""
    lookup_system = CapabilityLookupSystem()
    results = lookup_system.search_capabilities(query)
    
    print(f"\nSearch Results for: '{query}'")
    print("=" * 50)
    
    if results.get("error"):
        print(f"Error: {results['error']}")
        return
    
    if not results["results"]:
        print("No similar capabilities found.")
        return
    
    for i, result in enumerate(results["results"], 1):
        print(f"\n{i}. {result['capability']}")
        print(f"   File: {result['fileName']}")
        print(f"   Summary: {result['summary']}")
        print(f"   Source: {result['sourceLink']}")
        print(f"   Similarity: {1 - result['distance']:.3f}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Command-line query
        query = " ".join(sys.argv[1:])
        search_capability_command(query)
    else:
        # Run main demo
        main()
