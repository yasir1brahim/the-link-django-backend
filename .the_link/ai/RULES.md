# RULES

The rules here in the RULES.md file are meant to be a living document.  You can and should update the RULES.md file with new information and rules that should be remembered.

## PROMPT LIBRARY

We have various prompts that can be used for workflows.  The prompts are grouped into function and stored in separate files in the .the_link/ai/PROMPTS/**/*.md directory and are named *.prompt.md.

### Prompt Library Rules

If you are asked to do a task that relates to prompts in the list, you should read in any prompt files that seem applicable.  Don't ask for prompt files that don't apply to the current task.

Example user prompt and action:
"Please test this function." You should load in a testing prompt.
"Let's plan out a feature." You should load in a planning prompt.

### Prompt Library List

* Documentation: A workflow for generating and maintaining project documentation:
  * .the_link/ai/PROMPTS/documentation/generate-documentation.prompt.md - Generate comprehensive project documentation
  * .the_link/ai/PROMPTS/documentation/update-documentation.prompt.md - Update existing documentation
  * .the_link/ai/PROMPTS/documentation/update-readme.prompt.md - Update README files

* Feature Planning: A comprehensive feature planning workflow that follows a systematic sequence:
  * **Quick Planning:**
    * .the_link/ai/PROMPTS/planning/quick/01-quick-planning.prompt.md - Quick Proof of Concept planning
  * **Detailed Planning:**
    * .the_link/ai/PROMPTS/planning/detailed/01-prd.prompt.md - Product Requirements Document generation
    * .the_link/ai/PROMPTS/planning/detailed/02-adr.prompt.md - Architecture Decision Records creation
    * .the_link/ai/PROMPTS/planning/detailed/03-tasks.prompt.md - Task breakdown
    * .the_link/ai/PROMPTS/planning/detailed/04-task-decomposition.prompt.md - Detailed task decomposition
    * .the_link/ai/PROMPTS/planning/detailed/05-testing.prompt.md - Testing strategy
    * .the_link/ai/PROMPTS/planning/detailed/06-summary.prompt.md - Planning summary

* Task Breakdown: A workflow for breaking down development tasks:
  * **Quick Task Breakdown:**
    * .the_link/ai/PROMPTS/task_breakdown/quick/01-quick-task-breakdown.prompt.md - Quick task breakdown for projects
  * **Detailed Task Breakdown:**
    * .the_link/ai/PROMPTS/task_breakdown/detailed/01-task-breakdown.prompt.md - Initial task breakdown
    * .the_link/ai/PROMPTS/task_breakdown/detailed/02-task-complexity-rating.prompt.md - Rating task complexity
    * .the_link/ai/PROMPTS/task_breakdown/detailed/03-task-decomposition.prompt.md - Detailed task decomposition

* Task Execution: A workflow for implementing planned tasks:
  * **Detailed Task Execution:**
    * .the_link/ai/PROMPTS/task_execution/01-task-execution.prompt.md - Sequential task execution with validation

* UI Mockup Generation: A workflow for creating comprehensive UI mockups using the_link Design System:
  * **Quick Mockups:**
    * .the_link/ai/PROMPTS/mockups/quick/01-quick-mockup.prompt.md - Quick Proof of Concept mockups
  * **Detailed Mockups:**
    * .the_link/ai/PROMPTS/mockups/detailed/00-overview.prompt.md - Overview of the mockup generation workflow
    * .the_link/ai/PROMPTS/mockups/detailed/01-analysis.prompt.md - Analysis of UI/UX requirements
    * .the_link/ai/PROMPTS/mockups/detailed/01b-component-library.prompt.md - Component library supplement
    * .the_link/ai/PROMPTS/mockups/detailed/02-component-library.prompt.md - Creation of reusable IDS components
    * .the_link/ai/PROMPTS/mockups/detailed/02b-component-library.prompt.md - Component library additional guide
    * .the_link/ai/PROMPTS/mockups/detailed/02c-component-library.prompt.md - Component library final guide
    * .the_link/ai/PROMPTS/mockups/detailed/03-screens.prompt.md - Building individual screen mockups
    * .the_link/ai/PROMPTS/mockups/detailed/04-showcase.prompt.md - Assembling a navigable showcase page
    * .the_link/ai/PROMPTS/mockups/detailed/05-validation.prompt.md - Validating mockups against requirements
    * .the_link/ai/PROMPTS/mockups/detailed/06-storybook-integration.prompt.md - Integrating with Storybook
    * .the_link/ai/PROMPTS/mockups/detailed/setup-mockup-system.prompt.md - Setting up the mockup system

* Verification: A workflow for verifying completed tasks:
  * **Detailed Verification:**
    * .the_link/ai/PROMPTS/verification/01-verification.prompt.md - Thorough verification and merge request preparation


### Common Pitfalls to Avoid

AI TODO: Add notes here as problems are discovered.

## Documentation

TODO: this should reference documentation mcp tooling

## Coding

Adhere to any coding practices listed here.  If you are asked to start doing a best practice, or stop using some coding pattern, you should suggest adding it as a rule here.  By default use common best practices for whatever language you are coding in.

### Coding Rules

Use test driven development for all work.


## Tests

Adhere to any testing practices listed here.  If you are asked to start doing a best practice, or stop using some coding pattern, you should suggest adding it as a rule here.  This can include specific testing patterns, libraries, naming conventions, etc.

### Testing Rules
Do not edit tests to make them pass unless there is a legitimate issue with a test case

AI TODO: Fill this in