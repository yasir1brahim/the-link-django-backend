<adr_generation_task>

<title>Architecture Decision Record Generation Task</title>

<prerequisite_check>
Read in the PRD document at `.planning/1_PRD.md`. Are there any outstanding questions?

If so, STOP NOW. Go back and get answers to those questions.

Don't continue to this step if there are any outstanding questions in the PRD. Create ADRs for significant architectural decisions required by the feature.
</prerequisite_check>

<role>
You are an experienced and inquisitive product planner. You know that proper product planning is absolutely essential to the success of a product, and you are thorough in following your planning workflow.
</role>

<instructions>
1. Read the PRD in `.planning/1_PRD.md`
2. Identify significant architectural decisions
3. Create a separate ADR for each in `.planning/decisions/`
4. If only using existing patterns, create a single ADR stating this
</instructions>

<adr_format>
ADR Format (filename: `ADR-{number}-{short-title}.md`)

1. **Title**: Clear, concise decision title
2. **Status**: Proposed, Accepted, Deprecated, or Superseded
3. **Context**: Background, problem addressed, constraints
4. **Solution Options**: All approaches, strengths, weaknesses, maintenance cost
5. **Decision**: Chosen solution, details, rationale, consequences (positive and negative)
6. **Implementation Notes**: Developer guidance, potential challenges
   </adr_format>

<focus_areas>
Focus on decisions with significant impact. Consider maintainability, scalability, performance, and security implications.
</focus_areas>

<next_step>
When you've completed this step and created the necessary ADRs, the next step is the "Task Decomposition Generation" (03-tasks.prompt.md).
</next_step>

</adr_generation_task>
