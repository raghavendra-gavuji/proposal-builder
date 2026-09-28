"""
Hindsight Memory Manager for Proposal Builder
Manages persistent memory of proposals, refinements, and user preferences via HTTP API

NOTE: This module uses the Hindsight HTTP API (REST-based).
If Hindsight is not available, the app continues to work normally.
"""

import json
import httpx
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

# Hindsight API client using HTTP
class HindsightClient:
    """Client for Hindsight HTTP API"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)
    
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def health_check(self) -> bool:
        """Check if Hindsight API is available"""
        try:
            response = self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def create_bank(self, bank_id: str, mission: str, directives: List[str]) -> bool:
        """Create or get a memory bank"""
        try:
            payload = {
                "name": bank_id,
                "mission": mission,
                "directives": [{"text": d, "severity": "high"} for d in directives],
                "description": "Proposal Builder Memory Bank"
            }
            response = self.client.post(
                f"{self.base_url}/v1/default/banks",
                json=payload,
                headers=self._headers()
            )
            return response.status_code in [200, 201, 409]  # 409 = already exists
        except Exception as e:
            print(f"Error creating bank: {e}")
            return False
    
    def retain(self, bank_id: str, content: str, source: str = "proposal", metadata: Optional[Dict] = None) -> bool:
        """Store a fact in memory"""
        try:
            payload = {
                "content": content,
                "source_document_id": source,
                "tagged": metadata or {}
            }
            response = self.client.post(
                f"{self.base_url}/v1/default/banks/{bank_id}/memories",
                json=payload,
                headers=self._headers()
            )
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error retaining memory: {e}")
            return False
    
    def recall(self, bank_id: str, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search memory for relevant facts"""
        try:
            payload = {
                "query": query,
                "limit": limit
            }
            response = self.client.post(
                f"{self.base_url}/v1/default/banks/{bank_id}/memories/recall",
                json=payload,
                headers=self._headers()
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            return []
        except Exception as e:
            print(f"Error recalling memory: {e}")
            return []
    
    def reflect(self, bank_id: str, query: str) -> str:
        """Get consolidated answer based on memory"""
        try:
            payload = {"query": query}
            response = self.client.post(
                f"{self.base_url}/v1/default/banks/{bank_id}/reflect",
                json=payload,
                headers=self._headers()
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("content", "")
            return ""
        except Exception as e:
            print(f"Error in reflect: {e}")
            return ""

# Global client
hindsight_client: Optional[HindsightClient] = None
HINDSIGHT_AVAILABLE = False


def initialize_hindsight(
    base_url: Optional[str] = None, 
    api_key: Optional[str] = None
) -> Optional[HindsightClient]:
    """
    Initialize Hindsight HTTP API client
    
    Args:
        base_url: Hindsight API URL (default: localhost:8090 or env var HINDSIGHT_URL)
        api_key: API key for cloud deployment (default: env var HINDSIGHT_API_KEY)
    
    Returns:
        HindsightClient instance or None if unavailable
    """
    global hindsight_client, HINDSIGHT_AVAILABLE
    
    # Get config from environment or parameters
    base_url = base_url or os.getenv("HINDSIGHT_URL", "http://localhost:8090")
    api_key = api_key or os.getenv("HINDSIGHT_API_KEY")
    
    try:
        client = HindsightClient(base_url, api_key)
        
        # Test connection
        if client.health_check():
            hindsight_client = client
            HINDSIGHT_AVAILABLE = True
            print("✅ Hindsight HTTP API connected successfully")
            print(f"   Base URL: {base_url}")
            return client
        else:
            print("⚠️  Hindsight API not responding")
            print(f"   Tried: {base_url}")
            print("   App will continue without memory features")
            return None
    except Exception as e:
        print(f"⚠️  Hindsight connection failed: {e}")
        print("💡 Ensure Hindsight server is running at:", base_url)
        print("   Or set HINDSIGHT_URL and HINDSIGHT_API_KEY environment variables")
        print("   App will continue without memory features")
        return None


class HindsightManager:
    """Manage Hindsight memory operations for proposal builder via HTTP API"""
    
    MEMORY_BANK_NAME = "sah"
    MISSION = """
    I am a Proposal Builder AI Assistant. My purpose is to generate professional, 
    compelling business proposals that are customized to each client's needs. 
    I retain knowledge about proposal structures, content patterns, user preferences,
    and past successful proposals to improve future generations.
    I prefer clarity, professionalism, and client-specific customization.
    """
    
    DIRECTIVES = [
        "Always cite or reference relevant past proposal patterns when available",
        "Never generate generic content; personalize based on preferences",
        "Maintain consistency across proposal sections",
        "Preserve user refinement choices as strong signals"
    ]
    
    def __init__(self, client: Optional[HindsightClient] = None):
        """Initialize with Hindsight HTTP client"""
        self.client = client or hindsight_client
        self.bank_id = None
        
        if self.client:
            self._setup_memory_bank()
    
    def _setup_memory_bank(self):
        """Create or get the memory bank for proposal builder"""
        try:
            # Create bank if not exists
            if self.client.create_bank(self.MEMORY_BANK_NAME, self.MISSION, self.DIRECTIVES):
                self.bank_id = self.MEMORY_BANK_NAME
                print(f"✅ Memory bank '{self.MEMORY_BANK_NAME}' ready")
            else:
                print(f"⚠️  Could not set up memory bank")
        except Exception as e:
            print(f"⚠️  Error setting up memory bank: {e}")
    
    def retain_proposal(self, proposal_data: Dict[str, Any]) -> bool:
        """Retain a generated proposal in memory"""
        if not self.client or not self.bank_id:
            return False
        
        try:
            proposal_id = proposal_data.get("proposal_id", "unknown")
            discovery_data = proposal_data.get("discovery_data", {})
            generated_content = proposal_data.get("generated_content", {})
            
            summary = self._create_proposal_summary(discovery_data, generated_content)
            
            return self.client.retain(
                self.bank_id,
                summary,
                source=f"proposal_{proposal_id}",
                metadata={
                    "type": "proposal",
                    "proposal_id": proposal_id,
                    "industry": discovery_data.get("industry", "unknown"),
                    "client": discovery_data.get("client_name", "unknown"),
                    "created_at": proposal_data.get("created_at", datetime.now().isoformat())
                }
            )
        except Exception as e:
            print(f"⚠️  Error retaining proposal: {e}")
            return False
    
    def retain_refinements(self, proposal_id: str, refinements: str, original_content: Dict[str, Any]) -> bool:
        """Retain user refinements as feedback"""
        if not self.client or not self.bank_id:
            return False
        
        try:
            feedback_summary = f"User Refinement: {refinements}"
            
            return self.client.retain(
                self.bank_id,
                feedback_summary,
                source=f"refinement_{proposal_id}",
                metadata={"type": "user_feedback", "proposal_id": proposal_id}
            )
        except Exception as e:
            print(f"⚠️  Error retaining refinements: {e}")
            return False
    
    def recall_similar_proposals(self, discovery_data: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
        """Recall similar past proposals"""
        if not self.client or not self.bank_id:
            return []
        
        try:
            query = self._build_recall_query(discovery_data)
            memories = self.client.recall(self.bank_id, query, limit)
            
            if memories:
                print(f"✅ Recalled {len(memories)} similar proposals")
                return memories
            return []
        except Exception as e:
            print(f"⚠️  Error recalling proposals: {e}")
            return []
    
    def recall_user_preferences(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recall user preferences from past refinements"""
        if not self.client or not self.bank_id:
            return []
        
        try:
            query = "user preferences refinement style feedback"
            memories = self.client.recall(self.bank_id, query, limit)
            
            if memories:
                print(f"✅ Recalled {len(memories)} user preference patterns")
                return memories
            return []
        except Exception as e:
            print(f"⚠️  Error recalling preferences: {e}")
            return []
    
    def reflect_for_generation(self, discovery_data: Dict[str, Any]) -> str:
        """Get consolidated context for proposal generation"""
        if not self.client or not self.bank_id:
            return ""
        
        try:
            query = f"""
            Based on past proposals:
            - Industry: {discovery_data.get('industry', 'unknown')}
            - Client: {discovery_data.get('client_name', 'unknown')}
            
            What patterns worked well? What did users prefer to change?
            """
            
            reflection = self.client.reflect(self.bank_id, query)
            
            if reflection:
                print(f"✅ Generated reflections")
                return reflection
            return ""
        except Exception as e:
            print(f"⚠️  Error in reflect: {e}")
            return ""
    
    def _create_proposal_summary(self, discovery_data: Dict[str, Any], generated_content: Dict[str, Any]) -> str:
        """Create a text summary of a proposal"""
        summary = f"""
Proposal Summary:
- Client: {discovery_data.get('client_name', 'Unknown')}
- Industry: {discovery_data.get('industry', 'Unknown')}
- Scope: {discovery_data.get('project_scope', 'Unspecified')}
        """
        return summary
    
    def _build_recall_query(self, discovery_data: Dict[str, Any]) -> str:
        """Build a search query from discovery data"""
        industry = discovery_data.get("industry", "")
        client_type = discovery_data.get("client_type", "")
        scope = discovery_data.get("project_scope", "")
        
        return f"{industry} {client_type} {scope} proposal".strip()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        return {
            "connected": self.client is not None and HINDSIGHT_AVAILABLE,
            "memory_bank_ready": self.bank_id is not None,
            "bank_name": self.bank_id
        }


# Singleton instance
_manager = None


def get_hindsight_manager() -> HindsightManager:
    """Get or initialize the global Hindsight manager"""
    global _manager
    if _manager is None:
        client = initialize_hindsight()
        _manager = HindsightManager(client)
    return _manager
    
    def __init__(self, client: Optional[Hindsight] = None):
        """Initialize with Hindsight client"""
        self.client = client or hindsight_client
        self.memory_bank = None
        
        if self.client:
            self._setup_memory_bank()
    
    def _setup_memory_bank(self):
        """Create or get the memory bank for proposal builder"""
        try:
            # Get or create memory bank
            self.memory_bank = self.client.memory_bank(
                name=self.MEMORY_BANK_NAME,
                mission=self.MISSION,
                directives=self.DIRECTIVES,
                disposition={
                    "professionalism": 5,
                    "creativity": 4,
                    "thoroughness": 5,
                    "empathy": 3
                }
            )
            print(f"✅ Memory bank '{self.MEMORY_BANK_NAME}' ready")
        except Exception as e:
            print(f"⚠️  Error setting up memory bank: {e}")
    
    def retain_proposal(self, proposal_data: Dict[str, Any]) -> bool:
        """
        Retain a generated proposal in memory
        
        Args:
            proposal_data: Dict containing:
                - discovery_data: extracted from discovery document
                - generated_content: content generated by Gemini
                - proposal_id: unique proposal identifier
                - created_at: timestamp
        """
        if not self.client or not self.memory_bank:
            return False
        
        try:
            proposal_id = proposal_data.get("proposal_id", "unknown")
            discovery_data = proposal_data.get("discovery_data", {})
            generated_content = proposal_data.get("generated_content", {})
            
            # Create a summary of the proposal
            summary = self._create_proposal_summary(discovery_data, generated_content)
            
            # Retain the proposal in Hindsight
            self.memory_bank.retain(
                content=summary,
                source=f"proposal_{proposal_id}",
                metadata={
                    "type": "proposal",
                    "proposal_id": proposal_id,
                    "industry": discovery_data.get("industry", "unknown"),
                    "client": discovery_data.get("client_name", "unknown"),
                    "created_at": proposal_data.get("created_at", datetime.now().isoformat())
                }
            )
            print(f"✅ Retained proposal {proposal_id} in Hindsight")
            return True
        except Exception as e:
            print(f"⚠️  Error retaining proposal: {e}")
            return False
    
    def retain_refinements(self, proposal_id: str, refinements: str, original_content: Dict[str, Any]) -> bool:
        """
        Retain user refinements as feedback for future proposals
        
        Args:
            proposal_id: ID of the proposal being refined
            refinements: User's requested changes
            original_content: Original generated content
        """
        if not self.client or not self.memory_bank:
            return False
        
        try:
            feedback_summary = f"""
User Refinement Feedback for Proposal {proposal_id}:
Requested Changes: {refinements}

This indicates user preferences and areas for improvement in future proposals.
User preferred modifications suggest their style preferences and requirements.
            """
            
            self.memory_bank.retain(
                content=feedback_summary,
                source=f"refinement_{proposal_id}",
                metadata={
                    "type": "user_feedback",
                    "proposal_id": proposal_id,
                    "refinement_count": 1,
                    "feedback_timestamp": datetime.now().isoformat()
                }
            )
            print(f"✅ Retained refinement feedback for proposal {proposal_id}")
            return True
        except Exception as e:
            print(f"⚠️  Error retaining refinements: {e}")
            return False
    
    def recall_similar_proposals(self, discovery_data: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Recall similar past proposals to inform current generation
        
        Args:
            discovery_data: Current discovery document data
            limit: Max number of similar proposals to return
        
        Returns:
            List of similar proposal memories with context
        """
        if not self.client or not self.memory_bank:
            return []
        
        try:
            # Build a query from discovery data
            query = self._build_recall_query(discovery_data)
            
            # Recall from memory bank using multi-strategy search
            memories = self.memory_bank.recall(
                query=query,
                limit=limit,
                strategies=["semantic", "keyword", "temporal"]  # Use multiple search strategies
            )
            
            if memories:
                print(f"✅ Recalled {len(memories)} similar proposals from memory")
                return [mem for mem in memories]
            return []
        except Exception as e:
            print(f"⚠️  Error recalling proposals: {e}")
            return []
    
    def recall_user_preferences(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recall user preferences from past refinements
        
        Returns:
            List of user preference patterns
        """
        if not self.client or not self.memory_bank:
            return []
        
        try:
            query = "user preferences refinement style feedback changes"
            
            memories = self.memory_bank.recall(
                query=query,
                limit=limit,
                strategies=["semantic", "keyword"]
            )
            
            if memories:
                print(f"✅ Recalled {len(memories)} user preference patterns")
                return [mem for mem in memories]
            return []
        except Exception as e:
            print(f"⚠️  Error recalling preferences: {e}")
            return []
    
    def reflect_for_generation(self, discovery_data: Dict[str, Any]) -> str:
        """
        Use Hindsight's reflect() to consolidate knowledge and get contextual guidance
        for proposal generation
        
        Args:
            discovery_data: Current proposal's discovery data
        
        Returns:
            Consolidated context/guidance for Gemini prompt
        """
        if not self.client or not self.memory_bank:
            return ""
        
        try:
            query = f"""
            Based on my memory of past proposals:
            - For industry: {discovery_data.get('industry', 'unknown')}
            - For clients similar to: {discovery_data.get('client_name', 'unknown')}
            - What patterns, structures, and content approaches worked well?
            - What did users prefer to change or refine?
            - How should I approach this proposal given the user's history?
            """
            
            # Reflect consolidates observations and applies reasoning
            reflections = self.memory_bank.reflect(query=query)
            
            if reflections:
                print(f"✅ Generated reflections for proposal generation")
                return reflections
            return ""
        except Exception as e:
            print(f"⚠️  Error in reflect: {e}")
            return ""
    
    def _create_proposal_summary(self, discovery_data: Dict[str, Any], generated_content: Dict[str, Any]) -> str:
        """Create a text summary of a proposal for memory storage"""
        summary = f"""
Proposal Summary:
- Client: {discovery_data.get('client_name', 'Unknown')}
- Industry: {discovery_data.get('industry', 'Unknown')}
- Scope: {discovery_data.get('project_scope', 'Unspecified')}

Content Generated:
"""
        # Include high-level content structure
        if isinstance(generated_content, dict):
            for slide_num, content in generated_content.items():
                if isinstance(content, dict):
                    summary += f"\n- Slide {slide_num}: {list(content.keys())}"
        
        return summary
    
    def _build_recall_query(self, discovery_data: Dict[str, Any]) -> str:
        """Build a search query from discovery data"""
        industry = discovery_data.get("industry", "")
        client_type = discovery_data.get("client_type", "")
        scope = discovery_data.get("project_scope", "")
        
        query = f"{industry} {client_type} {scope} proposal template content"
        return query.strip()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of Hindsight integration"""
        return {
            "connected": self.client is not None,
            "memory_bank_ready": self.memory_bank is not None,
            "bank_name": self.MEMORY_BANK_NAME if self.memory_bank else None
        }


# Singleton instance
_manager = None


def get_hindsight_manager() -> HindsightManager:
    """Get or initialize the global Hindsight manager"""
    global _manager
    if _manager is None:
        client = initialize_hindsight()
        _manager = HindsightManager(client)
    return _manager
