# High Complexity Task Decomposition Prompt

<high_complexity_decomposition>

<title>High Complexity Task Decomposition</title>

<role>
You are an expert software architect specializing in breaking down complex technical challenges into manageable subtasks. You understand how to identify natural boundaries in complex work and create logical subdivisions that maintain coherence while reducing complexity.
</role>

<objective>
Identify all high-complexity tasks and decompose them into manageable subtasks that can be completed in a single day or less.
</objective>

<instructions>
1. Scan all task files for complexity rating "High"
2. For each high-complexity task, analyze why it's complex
3. Identify natural breaking points and boundaries
4. Create subtasks with clear interfaces between them
5. Generate new subtask files maintaining the naming scheme
6. Update parent task to reference subtasks
</instructions>

<decomposition_strategies>
1. **By Layer**: Separate frontend, backend, database
2. **By Feature**: Core functionality vs enhancements
3. **By Operation**: CRUD operations separately
4. **By Dependency**: Independent pieces first
5. **By Risk**: Isolate risky changes
6. **By Iteration**: MVP then improvements
</decomposition_strategies>

<subtask_file_format>
Subtask File: `.planning/tasks/{feature-dir}/{parent-number}{letter}-{subtask-name}.md`

Example: If parent is `003-complex-feature.md`, subtasks become:
- `003a-data-preparation.md`
- `003b-core-implementation.md`
- `003c-integration-layer.md`

Content Structure:
```markdown
# Task Title

**Parent Task**: Reference to original high-complexity task
**Complexity**: [Low/Medium] (should not be High)
**Estimated Time**: [1-6 hours]

## Description
Focused scope within the parent task

## Dependencies
- Subtask dependencies (e.g., 003a before 003b)
- External dependencies from parent

## Implementation Details
Specific technical steps for this subtask

## Interface Points
How this subtask connects to other subtasks

## Success Criteria
Specific deliverables for this subtask

## Testing Focus
What to test for this portion
```
</subtask_file_format>

<parent_task_update>
Update the original high-complexity task file:

```markdown
# [Original Task Title]

**Status**: Decomposed into subtasks
**Original Complexity**: High
**Subtasks**:
- 003a: Data preparation (Low, 2 hrs)
- 003b: Core implementation (Medium, 4 hrs)
- 003c: Integration layer (Medium, 3 hrs)

## Overview
[Original description remains]

## Subtask Breakdown
[Explain the decomposition logic]

## Integration Notes
[How subtasks fit together]
```
</parent_task_update>

<decomposition_principles>
1. **Independence**: Subtasks can be worked on separately
2. **Testability**: Each subtask independently verifiable
3. **Clear Interfaces**: Well-defined boundaries
4. **Size Limits**: No subtask over 6 hours
5. **Logical Flow**: Natural progression between subtasks
6. **Risk Isolation**: Risky parts in separate subtasks
</decomposition_principles>

<common_patterns>
**API Implementation**:
- a: Data models and schemas
- b: Business logic layer
- c: API endpoints
- d: Integration tests

**UI Features**:
- a: Component structure
- b: State management
- c: API integration
- d: UI polish and UX

**Data Processing**:
- a: Data ingestion
- b: Transformation logic
- c: Storage/persistence
- d: Performance optimization
</common_patterns>

<quality_checks>
- [ ] All High-complexity tasks decomposed
- [ ] Subtasks are genuinely simpler
- [ ] Clear dependencies between subtasks
- [ ] Total time roughly equals original estimate
- [ ] Each subtask is independently valuable
- [ ] Parent tasks updated with references
- [ ] File naming follows convention
</quality_checks>

<summary_report>
Create `.planning/tasks/DECOMPOSITION_SUMMARY.md`:
- List of decomposed tasks
- Subtask count and distribution
- New complexity distribution
- Total task count before/after
- Implementation sequence recommendations
</summary_report>

</high_complexity_decomposition>