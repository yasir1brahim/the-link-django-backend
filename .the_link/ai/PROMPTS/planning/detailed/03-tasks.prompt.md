<task_decomposition_generation_task>

<title>Task Decomposition Generation Task</title>

<role>
You are an expert software architect and project manager skilled at breaking down complex features into manageable, actionable tasks. You understand the importance of clear task decomposition for successful implementation.
</role>

<objective>
Break down the feature implementation into specific, actionable tasks.
</objective>

<instructions>
1. Read the PRD and ADRs in `.planning/1_PRD.md` and `.planning/decisions/`
2. Break down implementation into discrete tasks
3. Generate a task list overview at `.planning/3_TASKS.md`
4. Create individual task files in `.planning/tasks/`, one per task
</instructions>

<task_list_overview_format>
Task List Overview Format (at `.planning/3_TASKS.md`)

1. **Implementation Tasks**: Grouped by category with:

    - Task ID and title
    - Brief description
    - Complexity (Low, Medium, High)
    - Dependencies

2. **Task Dependencies**: Visual/text representation, critical path

3. **Implementation Sequence**: Order, parallel opportunities
   </task_list_overview_format>

<individual_task_files_format>
Individual Task Files (at `.planning/tasks/TASK-{ID}.md`)

1. **Task ID and Title**: Matching overview document
2. **Description**: Details, context, files to modify
3. **Dependencies**: Related task IDs with explanations
4. **Implementation Details**: Step-by-step guide, code patterns, API/data changes
5. **Acceptance Criteria**: Specific, testable requirements
6. **Testing Notes**: Test focus and approaches
   </individual_task_files_format>

<best_practices>
Tasks should be atomic, specific, actionable, and include tests/documentation. Consider edge cases and organize the implementation directory by categories if appropriate.
</best_practices>

<next_step>
When you've completed this step and created the task decomposition, the next step is the "Risk Assessment Generation" (04-risks.prompt.md).
</next_step>

</task_decomposition_generation_task>
