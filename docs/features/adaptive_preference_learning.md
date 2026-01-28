# Feature: Adaptive Preference Learning

## 1. Overview
**Branch**: `feat/adaptive-preference-learning`

This feature enables the agent to learn from user interactions and feedback to adjust its behavior over time. It will store user preferences and common patterns, using them to refine future responses and tool usage.

## 2. Requirements
- [ ] **Preference Storage**: A persistent store (JSON or DB) for user preferences (e.g., preferred languages, brevity, tools).
- [ ] **Feedback Mechanism**: A way for users to explicitly set preferences or provide feedback (e.g., "I prefer Python").
- [ ] **Context Injection**: Automatically inject relevant preferences into the system prompt.
- [ ] **Learning**: (Optional/Advanced) Infer preferences from repeated corrections (e.g., if user always asks for "shorter", set brevity=high).

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
- [ ] `tests/test_preference_learning.py`:
    - Set a preference.
    - Verify persistence.
    - Verify injection string generation.

**Manual Verification**:
- [ ] Run `python -m mini_nebulus.main start`.
- [ ] Command: "Set preference coding_style to 'verbose'".
- [ ] Verify subsequent prompts include this preference.

## 5. Workflow Checklist
- [ ] **Branch**: `feat/adaptive-preference-learning`
- [ ] **Work**: Implement PreferenceService and tools
- [ ] **Test**: `pytest` passes
- [ ] **Doc**: Updated docs
- [ ] **Merge**: `develop`
