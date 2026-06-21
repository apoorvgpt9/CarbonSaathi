"""Service-layer modules for the CarbonSaathi pipeline.

- emission_service: emission-factor lookup (India-specific grid/transport/food).
- firestore_service: typed async wrapper around Firestore for activities,
  insights, recommendations, and generation state.
- orchestrator: insight-generation pipeline driving Analyst → Coach with
  SSE-streamed reasoning.
- staleness: cache-staleness logic for the orchestrator's generation state.
"""
