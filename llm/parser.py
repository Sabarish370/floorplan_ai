import json
import os
from google.genai import types
from models.requirements import FloorPlanRequirements
from llm.gemini_client import get_client

def get_gemini_schema():
    """
    Returns a Gemini-compatible JSON schema that strictly defines room properties
    so the LLM knows how to populate the rooms object, and omits Vastu/Area 
    to prevent hallucinations.
    """
    return {
        "type": "OBJECT",
        "properties": {
            "plot": {
                "type": "OBJECT",
                "properties": {
                    "width": {"type": "NUMBER"},
                    "depth": {"type": "NUMBER"},
                    "unit": {"type": "STRING"},
                    "facing": {"type": "STRING"}
                },
                "required": ["width", "depth", "unit", "facing"]
            },
            "rooms": {
                "type": "OBJECT",
                "properties": {
                    "bedroom": {"type": "INTEGER"},
                    "hall": {"type": "INTEGER"},
                    "kitchen": {"type": "INTEGER"},
                    "bathroom": {"type": "INTEGER"},
                    "pooja": {"type": "INTEGER"},
                    "dining": {"type": "INTEGER"},
                    "utility": {"type": "INTEGER"}
                },
                "description": "Room counts. Only include rooms that are explicitly requested. Omit rooms that are not requested."
            },
            "parking": {"type": "BOOLEAN"}
        },
        "required": ["plot", "rooms", "parking"]
    }

def parse_requirements(user_input: str, test_case_name: str = "UNKNOWN TEST CASE") -> FloorPlanRequirements:
    import time
    import uuid
    client = get_client()
    model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    
    request_id = uuid.uuid4().hex[:8]
    print(f"[REQUEST {request_id}][{test_case_name}] Starting Gemini request for model: {model_name}")
    
    prompt = f"""
    Extract the floor plan requirements from the following user description.
    Focus on extracting the plot dimensions (width, depth), unit (usually 'ft'), facing (north, south, east, west).
    Also extract the number of required rooms (e.g., bedroom, hall, kitchen, bathroom, pooja) and whether parking is required.
    
    Interpret standard abbreviations like '2BHK' as 2 bedrooms, 1 hall, 1 kitchen.
    Standardize room names to: 'bedroom', 'hall', 'kitchen', 'bathroom', 'pooja', 'dining', 'utility'.
    If facing is not specified, output 'unknown'.
    If a required value cannot be reliably extracted, use 'unknown' if allowed by schema, or omit.
    Do not invent or guess information.
    
    User Input: "{user_input}"
    """

    MAX_RETRIES = 3
    base_delay = 2
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=get_gemini_schema(),
                    temperature=0.0,
                ),
            )
            print(f"[REQUEST {request_id}] Gemini attempt {attempt}/{MAX_RETRIES} succeeded.")
            break
        except Exception as e:
            error_str = str(e).upper()
            is_429 = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "QUOTA EXCEEDED" in error_str
            is_503 = "503" in error_str or "UNAVAILABLE" in error_str
            
            if is_429:
                print(f"[REQUEST {request_id}] Gemini API Quota Exhausted ({model_name}): {e}")
                raise ValueError("Gemini API quota/rate limit has been exceeded. Please check your API quota or switch to an available model.")
            elif is_503:
                if attempt < MAX_RETRIES:
                    delay = base_delay * (2 ** (attempt - 1))
                    print(f"[REQUEST {request_id}] Gemini API 503 Unavailable. Retrying in {delay} seconds (Attempt {attempt}/{MAX_RETRIES})...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"[REQUEST {request_id}] Gemini API 503 Unavailable. Final attempt failed (Attempt {attempt}/{MAX_RETRIES}).")
                    raise ValueError("Gemini is temporarily busy. Retrying automatically... If the service remains unavailable, please try again in a few minutes.")
            else:
                print(f"[REQUEST {request_id}] Gemini API request failed: {e}")
                raise ValueError("An unexpected error occurred while communicating with the Gemini API. Please try again later.")


    
    try:
        data = json.loads(response.text)
    except Exception as e:
        print(f"DEBUG: Failed to parse JSON response: {response.text}")
        raise ValueError(f"Failed to parse JSON response from Gemini: {e}")
        
    # Python deterministic derivations
    
    # 1. Deterministic Area Calculation
    if "plot" in data and "width" in data["plot"] and "depth" in data["plot"]:
        try:
            w = float(data["plot"]["width"])
            d = float(data["plot"]["depth"])
            data["plot"]["area"] = w * d
        except ValueError:
            pass
            
    # 2. Vastu Override (Phase 1)
    data["vastu_enabled"] = False
    
    # 3. Clean up rooms (remove nulls or 0s)
    if "rooms" in data and isinstance(data["rooms"], dict):
        clean_rooms = {}
        for k, v in data["rooms"].items():
            if v is not None and v > 0:
                clean_rooms[k] = v
        data["rooms"] = clean_rooms
        
    try:
        req = FloorPlanRequirements.model_validate(data)
        
        # Validation: Must have at least one room
        if not req.rooms:
            raise ValueError("No valid rooms were extracted from the description. Please specify the rooms you want (e.g. '2 bedrooms, 1 kitchen').")
            
        req.request_id = request_id
        req.test_case_name = test_case_name
        return req
    except Exception as e:
        if isinstance(e, ValueError) and "No valid rooms" in str(e):
            raise e
        print(f"DEBUG: Pydantic validation failed: {e}\nData: {data}")
        print(f"[REQUEST {request_id}][{test_case_name}] Error parsing requirements: {e}")
        raise ValueError(f"Extracted requirements failed validation: {e}")

