"""LangChain chains for the AI Agents service.

Contains the core chain implementations:
- AvatarChain: Main avatar conversation generation.
- InsightExtractionChain: Extract insights from user messages.
- SentimentChain: Sentiment and emotion analysis.

All chains use @traceable for LangSmith observability and compose
using the LangChain | operator (prompt | llm | parser).
"""
