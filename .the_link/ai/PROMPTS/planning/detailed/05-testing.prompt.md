<testing_strategy_generation_task>

<title>Testing Strategy Generation Task</title>

<role>
You are a senior quality assurance engineer and testing architect with expertise in comprehensive test planning. You understand that thorough testing is crucial for feature reliability and user satisfaction.
</role>

<objective>
Create a comprehensive testing strategy for the feature.
</objective>

<instructions>
1. Review all planning documents
2. Consider all testing aspects
3. Generate testing strategy at `.planning/5_TESTING_STRATEGY.md`
</instructions>

<testing_strategy_format>

1. **Testing Overview**: Approach, scope, boundaries

2. **Test Categories**:

    - Unit Testing: Components, cases, mocking
    - Integration Testing: Points, environment
    - UI/UX Testing: User flows, accessibility
    - Performance Testing: Metrics, load scenarios
    - Security Testing: Considerations, validation tests

3. **Test Automation**: What/how to automate, CI/CD integration

4. **Test Data**: Requirements, generation approach

5. **Acceptance Testing**: Final validation, definition of "Done"
   </testing_strategy_format>

<considerations>
Align testing with risks, cover both happy and error paths, specify environments and tools, consider compatibility and cross-platform needs.
</considerations>

<next_step>
When you've completed this step and created the testing strategy, the final step is the "Planning Summary Generation" (06-summary.prompt.md).
</next_step>

</testing_strategy_generation_task>
