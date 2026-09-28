# Hindsight Integration for Proposal Builder

## Overview

This project integrates **Hindsight**, an AI memory system designed for intelligent agents, into the Proposal Builder. Hindsight enables the system to:

- **Remember** past proposals and user preferences across sessions
- **Learn** from user refinements and improve future generations
- **Consolidate** knowledge about successful proposal patterns
- **Recall** relevant context when generating new proposals

## How It Works

### Memory Lifecycle

```
New Proposal Upload
    ↓
1. RECALL: Query memory for similar proposals & user preferences
    ↓
2. ENHANCE: Pass recalled context to Gemini for smarter generation
    ↓
3. GENERATE: Create proposal with informed content
    ↓
4. RETAIN: Store proposal & metadata in memory
    ↓
User Makes Refinements
    ↓
5. RETAIN FEEDBACK: Store refinements as learning signals
    ↓
6. CONSOLIDATE: Hindsight automatically consolidates observations
```

### Key Features

#### 1. **Recall Similar Proposals** 
Before generating a new proposal, the system queries Hindsight for:
- Similar past proposals (by industry, client type, scope)
- User's historical refinement patterns
- Successful content strategies

#### 2. **Enhanced Gemini Prompts**
Recalled memories are injected into the Gemini prompt as context:
```
**RELEVANT PAST PROPOSALS & PATTERNS (from memory):**
[Recalled proposals and patterns]
Consider these patterns and user preferences when generating content.
```

#### 3. **Automatic Learning**
Every refinement is retained as feedback:
- User's requested changes signal preferences
- Patterns are automatically consolidated into "observations"
- Future proposals benefit from this learning

#### 4. **Multi-Strategy Retrieval**
Hindsight uses TEMPR (4-way search):
- **Semantic**: By meaning (conceptual similarity)
- **Keyword**: Exact matches (industry names, techniques)
- **Graph**: Via entities (related concepts)
- **Temporal**: By time (recent vs. historical patterns)

## Setup & Deployment

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The requirements now include `hindsight-sdk`.

### 2. Deploy Hindsight Server

For a hackathon environment, you can run Hindsight locally:

#### Option A: Docker (Recommended)
```bash
docker run -p 8090:8090 hindsight:latest
```

#### Option B: Local Python Server
```bash
# Install Hindsight server
pip install hindsight-server

# Start the server
hindsight-server --port 8090
```

#### Option C: Cloud Deployment
- Use Hindsight Cloud (hindsight.dev)
- Update `base_url` and `api_key` in `hindsight_manager.py`

### 3. Start Proposal Builder

```bash
cd proposal-builder
python main.py
```

The application will automatically:
- Initialize Hindsight connection
- Create a memory bank for proposal builder
- Print status during startup

## Architecture

### New Files
- **`hindsight_manager.py`**: Core Hindsight integration
  - `HindsightManager` class for memory operations
  - `initialize_hindsight()` for setup
  - `get_hindsight_manager()` singleton

### Modified Files
- **`main.py`**:
  - Import hindsight_manager
  - Initialize Hindsight in lifespan
  - Call `recall()` before proposal generation
  - Call `retain()` after generation and refinements

- **`requirements.txt`**: Added hindsight-sdk

## API Endpoints

All existing endpoints work the same. Hindsight operations are transparent:

### `POST /api/proposals/create`
- Automatically recalls similar proposals
- Passes context to Gemini
- Retains generated proposal in memory

### `POST /api/proposals/{proposal_id}/update`
- Retains user refinements as learning signals
- Future proposals will use this feedback

## Memory Configuration

Hindsight is configured with:

**Mission:**
> "I am a Proposal Builder AI Assistant. My purpose is to generate professional, compelling business proposals that are customized to each client's needs. I retain knowledge about proposal structures, content patterns, user preferences, and past successful proposals to improve future generations."

**Directives:**
- Always cite or reference relevant past proposal patterns
- Never generate generic content; personalize based on preferences
- Maintain consistency across sections
- Preserve user refinement choices as strong signals

**Disposition:**
- Professionalism: 5/5
- Creativity: 4/5
- Thoroughness: 5/5
- Empathy: 3/5

## Monitoring & Debugging

### Check Hindsight Status
The API returns integration status:
```json
{
  "hindsight_connected": true,
  "memory_bank_ready": true,
  "bank_name": "proposal_builder"
}
```

### Logs
Look for these in console output:
- `✅ Hindsight Memory System Initialized` - Server startup
- `✅ Querying memory for similar proposals` - Recall operation
- `✅ Recalled X similar proposals` - Context found
- `✅ Retained proposal` - Proposal stored in memory

### Troubleshooting

**"⚠️ Hindsight not available"**
- Hindsight server not running
- Check: `curl http://localhost:8090/health`
- Start server: see "Deploy Hindsight Server" section

**"Error retaining proposal"**
- Check Hindsight server logs
- Verify memory bank configuration
- Ensure API key is valid (if using cloud)

## Performance Considerations

- **Recall**: ~100-200ms per query (parallelized)
- **Retain**: ~50-100ms per operation (async)
- **Memory**: Hindsight scales to thousands of proposals

For hackathon: Start with local deployment. Scale to cloud if needed.

## Next Steps

1. ✅ Basic integration complete
2. 🚀 Add custom reflection prompts (reflect())
3. 📊 Build dashboards to visualize memory consolidation
4. 🔧 Add admin endpoints to manage memory banks
5. 📈 Analyze learning effectiveness over time

## Example Workflow

```python
# User uploads discovery document
POST /api/proposals/create
    → Hindsight recalls similar proposals
    → Gemini generates with context
    → Proposal retained in memory

# User refines proposal
POST /api/proposals/{id}/update
    → Changes retained as feedback
    → Hindsight consolidates patterns
    
# Next proposal (same industry)
POST /api/proposals/create
    → Recalls previous patterns
    → Generates improved content based on learning
```

## Support

For Hindsight documentation: https://docs.hindsight.dev
For this integration: Check hindsight_manager.py comments
