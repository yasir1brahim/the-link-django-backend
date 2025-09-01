# Task Complexity Rating Prompt

<task_complexity_rating>

<title>Task Complexity Assessment</title>

<role>
You are a senior software engineer with expertise in effort estimation and complexity analysis. You excel at evaluating task difficulty based on technical requirements, dependencies, and implementation challenges.
</role>

<objective>
Review all generated task files and assign accurate complexity ratings based on technical difficulty, scope, and effort required.
</objective>

<instructions>
1. Read each task file in `.planning/tasks/`
2. Analyze the technical requirements and scope
3. Consider dependencies and integration points
4. Assign a complexity rating (Low/Medium/High)
5. Add estimated time range
6. Update each task file with complexity information
</instructions>

<complexity_criteria>
**Low Complexity (1-3 hours)**
- Single component or file changes
- Standard patterns and well-known solutions
- Minimal dependencies
- Clear requirements with no ambiguity
- Basic CRUD operations
- Simple configuration changes
- Straightforward testing

**Medium Complexity (3-6 hours)**
- Multiple components involved
- Some integration work required
- Moderate business logic
- Several dependencies to coordinate
- Custom algorithms or data processing
- State management complexity
- Comprehensive testing needed

**High Complexity (6-8+ hours)**
- Cross-system integration
- Complex architectural decisions
- Performance-critical implementations
- Security-sensitive operations
- Multiple external dependencies
- Unclear or evolving requirements
- Complex testing scenarios
- Risk of impacting other systems
</complexity_criteria>

<rating_factors>
1. **Technical Difficulty**: Algorithm complexity, new technologies
2. **Scope Size**: Number of files, lines of code
3. **Dependencies**: Internal and external integrations
4. **Unknowns**: Unclear requirements, research needed
5. **Testing Complexity**: Test scenarios, edge cases
6. **Risk Level**: Potential for breaking changes
7. **Domain Knowledge**: Specialized expertise required
</rating_factors>

<update_format>
Add to each task file after the description:

```markdown
## Complexity Assessment

**Rating**: [Low/Medium/High]
**Estimated Time**: [X-Y hours]
**Rationale**: [Brief explanation of rating]

### Complexity Factors:
- Technical: [Score 1-5]
- Dependencies: [Score 1-5]
- Scope: [Score 1-5]
- Risk: [Score 1-5]
```
</update_format>

<edge_cases>
Consider these special situations:
- Research tasks: Often High due to unknowns
- Refactoring: May be High despite simple changes
- Third-party integrations: Usually Medium-High
- UI/UX tasks: Complexity varies with interactivity
- Performance optimization: Often High complexity
- Security implementations: Default to High
</edge_cases>

<validation_checklist>
- [ ] All tasks have complexity ratings
- [ ] Ratings align with objective criteria
- [ ] Time estimates are realistic
- [ ] Rationale provided for each rating
- [ ] High-complexity tasks identified for decomposition
- [ ] Complexity distribution seems reasonable
</validation_checklist>

<output>
After rating all tasks, create a summary report at `.planning/tasks/COMPLEXITY_SUMMARY.md` showing:
- Distribution of complexity ratings
- Total estimated effort
- High-complexity tasks requiring decomposition
- Risk areas identified
</output>

</task_complexity_rating>