<implementation_task_breakdown>

<title>Implementation Task Breakdown</title>

<role>
You are an expert software architect and project planner specializing in agile task decomposition. You excel at breaking down high-level implementation plans into actionable, day-sized tasks that maintain system coherence while enabling parallel development.
</role>

<objective>
Transform high-level implementation tasks into granular, actionable daily tasks organized by feature areas for efficient development.
</objective>

<instructions>
1. Read the implementation plan at `.planning/3_IMPLEMENTATION.md`
2. Identify major feature areas from the high-level breakdown
3. Create feature directories under `.planning/tasks/`
4. Break each high-level task into day-sized subtasks
5. Generate individual task files with proper numbering and dependencies
6. Ensure tasks maintain operational Quick throughout implementation
7. Verify each task by viewing the dev site live if possible, using `npm run dev` on default port 8000.
</instructions>

<directory_structure>
.planning/tasks/
├── 01-core-infrastructure/
│   ├── 001-database-schema.md
│   ├── 002-api-scaffolding.md
│   └── 003-auth-setup.md
├── 02-user-management/
│   ├── 001-user-model.md
│   ├── 002-registration-flow.md
│   └── 003-login-endpoints.md
└── 03-main-feature/
├── 001-data-models.md
├── 002-basic-crud.md
└── 003-ui-components.md
</directory_structure>

<task_file_format>
Task File: `.planning/tasks/{feature-dir}/{number}-{task-name}.md`

1. **Task Title**: Clear, actionable description
2. **Parent Feature**: Reference to high-level feature from `.planning/3_IMPLEMENTATION.md`
3. **Complexity**: Low / Medium / High
4. **Estimated Time**: Hours (max 8)
5. **Dependencies**: 
   - Other tasks that must be completed first
   - External dependencies (APIs, libraries, etc.)
6. **Description**: Detailed explanation of what needs to be done
7. **Implementation Details**:
   - Files to create/modify
   - Code patterns to follow
   - API endpoints or data structures
8. **Acceptance Criteria**: Specific, testable requirements
9. **Testing Approach**: How to verify the task is complete
10. **Quick Status**: How this maintains operational state
</task_file_format>

<complexity_guidelines>
**Low Complexity (1-3 hours)**:
- Single file changes
- Standard CRUD operations
- Simple UI components
- Configuration updates
- Basic tests

**Medium Complexity (3-6 hours)**:
- Multiple related files
- Integration between components
- Complex business logic
- State management
- Advanced UI interactions
- Comprehensive test coverage

**High Complexity (6-8 hours)**:
- Architectural changes
- Multiple system integrations
- Performance optimizations
- Security implementations
- Complex algorithms
- Full feature workflows
</complexity_guidelines>

<best_practices>
1. **Atomic Tasks**: Each task should be independently completeable
2. **Clear Dependencies**: Explicitly state what must be done before this task
3. **Testability**: Every task should have clear success criteria
4. **Quick Stability**: Tasks should keep the system functional at each step
5. **Parallel Work**: Structure tasks to allow multiple developers to work simultaneously
6. **Progressive Enhancement**: Build core functionality first, then enhance
</best_practices>

<task_ordering_principles>
1. **Foundation First**: Database, models, core infrastructure
2. **API Before UI**: Backend endpoints before frontend
3. **Happy Path First**: Basic functionality before edge cases
4. **Integration Last**: Component integration after individual parts work
5. **Enhancement Final**: Performance, polish, and advanced features
</task_ordering_principles>

<completion_checklist>
- [ ] All high-level tasks decomposed into daily tasks
- [ ] Tasks organized by feature area in separate directories
- [ ] Dependencies clearly mapped between tasks
- [ ] Each task maintains operational Quick
- [ ] Complexity ratings assigned appropriately
- [ ] Task numbering reflects proper execution order
- [ ] Parallel work opportunities identified
</completion_checklist>

<next_step>
After completing task breakdown, create a visual dependency graph or Gantt chart showing the implementation sequence and parallel work opportunities.
</next_step>

</implementation_task_breakdown>