"""Semantic search building blocks.

- ``retrieval``: pure NumPy cosine similarity and deterministic top-k (no I/O, no model).
- ``encoder``: adapter that turns text into vectors (the only place a model is loaded).
"""
