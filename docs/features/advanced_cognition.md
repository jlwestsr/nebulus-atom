# Feature: Advanced Cognition ("System 2" Thinking)

## 1. Overview
**Branch**: `feat/advanced-cognition`

Implements deeper reasoning capabilities inspired by Daniel Kahneman's "System 2" thinking - slow, deliberate, analytical reasoning vs fast intuitive responses. This enables the agent to handle complex multi-step problems more reliably.

## 2. Core Concepts

### System 1 vs System 2
- **System 1** (Current): Fast, automatic tool execution based on pattern matching
- **System 2** (New): Deliberate reasoning with explicit problem decomposition and self-verification

### Key Capabilities
1. **Reasoning Chains**: Explicit step-by-step thinking before action
2. **Problem Decomposition**: Breaking complex tasks into manageable sub-tasks
3. **Self-Critique**: Evaluating outputs before finalizing
4. **Uncertainty Awareness**: Knowing when to ask for clarification
5. **Verification Loops**: Checking work before declaring completion

## 3. Requirements

### Phase 1: Reasoning Engine ✅
- [x] **CognitionService**: New service to manage reasoning processes
- [x] **Task Complexity Analysis**: Classify tasks as simple/moderate/complex
- [x] **Reasoning Chain Generation**: Generate explicit thinking steps
- [x] **Thought Logging**: Persist reasoning for observability

### Phase 2: Self-Critique ✅
- [x] **Output Verification**: Review tool outputs for correctness
- [x] **Error Anticipation**: Predict potential failure modes
- [x] **Confidence Scoring**: Track certainty levels (0-100%)

### Phase 3: Adaptive Behavior ✅
- [x] **Complexity-Based Routing**: Simple tasks → fast path, Complex → deep reasoning
- [x] **Clarification Triggers**: Auto-detect ambiguous requests
- [x] **Learning from Mistakes**: Track failure patterns, adjust confidence scoring

## 4. Technical Implementation

### New Files
- `nebulus_atom/services/cognition_service.py`: Core reasoning engine
- `nebulus_atom/models/cognition.py`: Data models for thoughts/reasoning
- `nebulus_atom/services/failure_memory_service.py`: Failure tracking, pattern recognition, confidence penalties
- `nebulus_atom/models/failure_memory.py`: Data models for failure records, patterns, and context
- `tests/test_cognition_service.py`: Cognition unit tests
- `tests/test_failure_memory_service.py`: Failure memory unit tests (35 tests, 97% coverage)

### Modified Files
- `nebulus_atom/controllers/turn_processor.py`: Integrate cognition and failure context before tool execution
- `nebulus_atom/controllers/agent_controller.py`: Add cognition hooks
- `nebulus_atom/services/tool_executor.py`: Record failures on error, append failure summary to recovery hints

### Data Models
```python
@dataclass
class ReasoningStep:
    step_number: int
    thought: str
    conclusion: str
    confidence: float  # 0.0 - 1.0

@dataclass
class CognitionResult:
    task_complexity: str  # "simple" | "moderate" | "complex"
    reasoning_chain: List[ReasoningStep]
    recommended_approach: str
    clarification_needed: bool
    clarification_questions: List[str]
```

### Complexity Classification
| Complexity | Criteria | Behavior |
|------------|----------|----------|
| Simple | Single tool, clear intent | Direct execution |
| Moderate | 2-3 tools, some ambiguity | Brief reasoning |
| Complex | Multi-step, dependencies, unclear | Full reasoning chain |

## 5. Verification Plan

### Automated Tests
- [x] `tests/test_cognition_service.py` (25 tests):
  - Test complexity classification accuracy
  - Test reasoning chain generation
  - Test confidence scoring
  - Test clarification detection
- [x] `tests/test_failure_memory_service.py` (35 tests):
  - Test error classification (8 error types)
  - Test argument sanitization
  - Test confidence penalty math and caps
  - Test SQLite record/query/resolve operations
  - Test cognition integration (confidence reduction, risk injection, backward compat)

### Manual Verification
- [ ] Simple task: "List files" → Direct execution, no deep reasoning
- [ ] Moderate task: "Create a Python function" → Brief analysis
- [ ] Complex task: "Refactor the authentication system" → Full reasoning chain with clarifications

## 6. Example Flow

**User**: "Add user authentication to the app"

**System 2 Response**:
```
🧠 Analyzing task complexity... [COMPLEX]

Reasoning Chain:
1. This requires multiple components: login, logout, session management
2. Need to understand current app architecture first
3. Multiple implementation approaches possible (JWT, sessions, OAuth)
4. Security implications require careful consideration

Clarification Needed:
- What authentication method do you prefer? (JWT/Session/OAuth)
- Should it integrate with existing user model?
- What routes need protection?

Confidence: 45% (needs clarification before proceeding)
```

## 7. Workflow Checklist
- [x] **Branch**: Created `feat/advanced-cognition` branch
- [x] **Phase 1**: Implement CognitionService
- [x] **Phase 2**: Implement self-critique
- [x] **Phase 3**: Integrate with turn processor
- [x] **Test**: All tests pass (`pytest`) — 474 tests passing
- [x] **Doc**: Update README and wiki
