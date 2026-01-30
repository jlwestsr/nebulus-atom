# Feature: Multimodal Input (Image Understanding)

## 1. Overview
**Branch**: `feat/multimodal-input`

Enable Nebulus Atom to process images alongside text. This allows users to share screenshots, diagrams, or mockups, which the agent can analyze using a vision-capable model (like Gemini Pro Vision or GPT-4o).

## 2. Requirements
- [x] Add `scan_image <path>` tool to add an image to the context.
- [x] Update `OpenAIService` to support `image_url` or base64 image payloads in messages (via tool output).
- [ ] Handle CLI drag-and-drop file paths (detect if input is an image path).
- [ ] Support "vision" capability in the LLM configuration.

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/openai_service.py` (Modify payload construction).
    - `nebulus_atom/controllers/agent_controller.py` (Handle image inputs).
- **Dependencies**: None (API support).
- **Data**: Temp storage for processed images if needed.

## 4. Verification Plan
- [x] Download a test image (UI mockup).
- [x] Run `scan_image mockup.png`.
- [x] Ask "Describe this UI".
- [x] Verify accurate description from the agent.

## 5. Workflow Checklist
- [x] Create branch `feat/multimodal-input`
- [x] Implementation
- [x] Verification
