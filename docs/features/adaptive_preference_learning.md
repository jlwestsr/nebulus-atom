# Feature: Adaptive Preference Learning

## 1. Overview
**Branch**: `feat/adaptive-preference-learning`

This feature enables the agent to learn from user interactions and feedback to adjust its behavior over time. It will store user preferences and common patterns, using them to refine future responses and tool usage.

## 2. Requirements
- [x] **Preference Storage**: A persistent store (JSON or DB) for user preferences (e.g., preferred languages, brevity, tools).
- [x] **Feedback Mechanism**: A way for users to explicitly set preferences or provide feedback (e.g., "I prefer Python").
- [x] **Context Injection**: Automatically inject relevant preferences into the system prompt.
- [x] **Learning**: (Optional/Advanced) Infer preferences from repeated corrections (e.g., if user always asks for "shorter", set brevity=high).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/preference_service.py`: New service to manage preferences.
    - `mini_nebulus/models/preference.py`: Data model for preferences.
    - `mini_nebulus/controllers/agent_controller.py`: Inject preferences into system prompt.
    - `mini_nebulus/services/tool_executor.py`: Add tools `set_preference`, `get_preference`.
- **Data**:
    - Storage: `.mini_nebulus/preferences.json`

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_preference_learning.py`:
    - Set a preference.
    - Verify persistence.
    - Verify injection string generation.

**Manual Verification**:
- [x] Run `python -m mini_nebulus.main start`.
- [x] Command: "Set preference coding_style to 'verbose'".
- [x] Verify subsequent prompts include this preference.

## 5. Workflow Checklist
- [x] **Branch**: `feat/adaptive-preference-learning`
- [x] **Work**: Implement PreferenceService and tools
- [x] **Test**: `pytest` passes
- [x] **Doc**: Updated docs
- [x] **Merge**: `develop`
