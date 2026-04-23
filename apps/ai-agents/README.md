# Go Life - AI Agents Service

AI/ML service for the Go Life mobile app, built with **LangChain** and monitored with **LangSmith**.

## Tech Stack

- **Runtime**: Python 3.11+
- **Framework**: FastAPI
- **LLM Framework**: LangChain 0.1+
- **Observability**: LangSmith
- **LLM Providers**: OpenAI GPT-4 / Anthropic Claude
- **Vector Store**: PostgreSQL + pgvector (via LangChain)
- **Type Checking**: Pyright (strict)

## Features

- **Avatar Conversation Chain**: Personalized responses using LangChain
- **Insight Extraction Chain**: Extract user insights from messages
- **Vector Memory**: Semantic search with pgvector
- **Full Tracing**: All LLM calls traced in LangSmith

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 16 with pgvector extension
- Redis 7
- LangSmith account (https://smith.langchain.com)

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt

# Copy environment file
cp .env.example .env
# Edit .env with your API keys (OpenAI, LangSmith)

# Run development server
uvicorn app.main:app --reload --port 8000
```

### Environment Variables

Required:
- `LANGSMITH_API_KEY` - Get from https://smith.langchain.com
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM provider

## Development

```bash
# Run tests
pytest

# Run linting
ruff check app/

# Format code
black app/
isort app/

# Type check
pyright app/
```

## LangSmith Dashboard

View all LLM traces at: https://smith.langchain.com

Traces include:
- Avatar response generation
- Insight extraction
- Vector similarity search
- Token usage and costs

## Project Structure

```
app/
├── chains/          # LangChain chains (avatar, insight, sentiment)
├── prompts/         # Prompt templates
├── memory/          # LangChain memory (vector store)
├── llm/             # LLM provider configuration
├── services/        # Business logic orchestration
├── api/             # FastAPI routes
└── config/          # Settings, LangSmith config
```

## Architecture

```
API-BACKEND (Django) → AI-AGENTS (this) → OpenAI/Claude
                            ↓
                      PostgreSQL + pgvector
                      LangSmith (traces)
```

See `.cursorrules` for detailed guidelines.
