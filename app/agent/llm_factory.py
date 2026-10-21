import os
import json
import re
from typing import Type, TypeVar, Optional, Any
from pydantic import BaseModel
from app.config import settings

T = TypeVar("T", bound=BaseModel)

def get_chat_model(provider: Optional[str] = None, api_key: Optional[str] = None, model_name: Optional[str] = None):
    """
    Factory function to instantiate the configured Chat LLM (Groq or NVIDIA).
    Returns None if provider is simulated or keys are absent.
    """
    prov = (provider or settings.LLM_PROVIDER).lower()
    
    if prov == "groq":
        key = api_key or settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
        if not key:
            return None
        from langchain_groq import ChatGroq
        model = model_name or settings.GROQ_MODEL
        return ChatGroq(
            api_key=key,
            model=model,
            temperature=0.2,
            max_retries=2
        )
        
    elif prov == "nvidia":
        key = api_key or settings.NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY", "")
        if not key:
            return None
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        model = model_name or settings.NVIDIA_MODEL
        return ChatNVIDIA(
            nvidia_api_key=key,
            model=model,
            temperature=0.2
        )
        
    return None

def invoke_structured(
    schema: Type[T],
    messages: list,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    fallback_generator: Optional[callable] = None
) -> T:
    """
    Invokes the LLM with structured output enforcement.
    Falls back gracefully to fallback_generator if LLM fails or is unconfigured.
    """
    llm = get_chat_model(provider=provider, api_key=api_key, model_name=model_name)
    
    if llm is not None:
        try:
            # 1. Try native with_structured_output
            structured_runnable = llm.with_structured_output(schema)
            result = structured_runnable.invoke(messages)
            if isinstance(result, schema):
                return result
            elif isinstance(result, dict):
                return schema(**result)
        except Exception as e:
            print(f"[llm_factory] structured_output exception: {e}. Trying raw invoke with JSON parse...")
            try:
                # 2. Fallback: prompt LLM for raw JSON and parse into Pydantic schema
                schema_json = json.dumps(schema.model_json_schema(), indent=2)
                augmented_messages = messages + [
                    ("human", f"Respond ONLY with a valid JSON object matching this schema:\n{schema_json}")
                ]
                raw_resp = llm.invoke(augmented_messages)
                content = raw_resp.content if hasattr(raw_resp, "content") else str(raw_resp)
                
                # Extract JSON block
                json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                json_str = json_match.group(1) if json_match else content.strip()
                parsed = json.loads(json_str)
                return schema(**parsed)
            except Exception as e2:
                print(f"[llm_factory] raw json parsing also failed: {e2}")

    # 3. If no LLM available or both calls failed, use the topic-aware simulation fallback generator
    if fallback_generator:
        return fallback_generator()
        
    raise RuntimeError("No LLM available and no fallback generator provided.")
