"""External runtime adapters for Aether Forge."""

from .function_call import (
    FunctionCallResponse,
    FunctionCallTranslator,
    FunctionToolCall,
)

__all__ = [
    "FunctionCallResponse",
    "FunctionCallTranslator",
    "FunctionToolCall",
]
