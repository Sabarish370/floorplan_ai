# Indian Residential Floor Plan Generator - Phase 1

## Purpose
Phase 1 of the Natural Language Driven Indian Residential Floor Plan Generator. This prototype takes a natural language description of floor plan requirements, extracts them using Google's Gemini API, validates the requirements, generates a basic deterministic room layout, and renders an SVG floor plan.

## Architecture
- **Gemini (LLM):** Natural language -> Structured JSON requirements (using `pydantic`).
- **Python Layout Generator:** Structured requirements -> Deterministic layout (x, y, width, depth coordinates).
- **Shapely:** Validates geometry (no overlaps, fits inside plot boundary).
- **SVG Renderer:** Validated geometry -> SVG visualization.
- **Streamlit:** UI flow and interaction.

## Setup Instructions
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure Gemini API Key:
   Create a `.env` file in the root directory and add your API key:
   ```
   GEMINI_API_KEY=your_actual_api_key_here
   ```

## Installation & Run Command
Install the required packages and run the application using Streamlit:
```bash
pip install streamlit google-genai pydantic shapely python-dotenv pytest
streamlit run app.py
```

## Example Input
"I have 40x50 land. I want 2 bedrooms, 1 hall, 1 kitchen, 2 bathrooms, 1 pooja room and parking. House should face east."

## Current Phase 1 Limitations
- The layout generation algorithm is a very basic grid packing script and not architecturally optimal.
- Rooms might be squeezed vertically to fit if they exceed plot depth.
- No Vastu logic is applied.
- All rooms are simple rectangles.
- Does not support complex user units conversion.

## Planned Future Phases
- **Phase 2:** Vastu Rule Engine
- **Phase 3:** NetworkX room graph
- **Phase 4:** OR-Tools CP-SAT optimization
- **Phase 5:** Multiple candidate layouts
- **Phase 6:** Indian floor-plan dataset
- **Phase 7:** ML/diffusion-based layout proposal
