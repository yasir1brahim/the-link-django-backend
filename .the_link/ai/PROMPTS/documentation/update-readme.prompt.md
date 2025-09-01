<readme_update_documentation>

<title>Project README Update</title>

<role>
You are an experienced technical documentation specialist tasked with updating project README files to accurately reflect recent code changes. Your goal is to ensure the README remains current, accurate, and helpful for developers working with the codebase.
</role>

<objective>
Analyze recent code changes and systematically update the project README to reflect new features, modified functionality, updated dependencies, changed setup procedures, and any other relevant changes that impact how developers interact with the project.
</objective>

<input>
- Current README.md file
- Recent code changes (git diff, commit history, or change description)
- Project structure and dependencies
- Existing documentation files
- Configuration files (package.json, requirements.txt, etc.)
</input>

<process>
1. Analyze the current README structure and content
2. Examine code changes to identify documentation impacts
3. Review project dependencies and configuration changes
4. Update relevant sections systematically
5. Ensure consistency and accuracy across all sections
6. Validate that examples and instructions still work
</process>

<change_analysis>
Follow this simple workflow to identify changes that may need README updates:

**1. Get All Changes**: Collect the raw data for analysis
```bash
# Get the complete picture of what changed
echo "=== Branch Changes Analysis ==="
echo "Changed files:"
git diff main..HEAD --name-status
echo -e "\nChange summary:"
git diff main..HEAD --stat
echo -e "\nCommit messages:"
git log --oneline main..HEAD
echo -e "\nSample changes:"
git diff main..HEAD | head -100
```

**2. AI-Driven Analysis**: Let AI examine the changes for README impact

**Provide this information to the AI for analysis:**
- List of all changed files (from `git diff main..HEAD --name-status`)
- Summary of changes (from `git diff main..HEAD --stat`)
- Sample of actual changes (from `git diff main..HEAD | head -100`)
- Commit messages (from `git log --oneline main..HEAD`)

**3. AI Analysis Questions**: Ask the AI to identify:
- **New features**: Are there new capabilities that users should know about?
- **Setup changes**: Are there changes to installation, dependencies, or configuration?
- **API changes**: Are there new endpoints, interfaces, or usage patterns?
- **Build/script changes**: Are there new commands, scripts, or build processes?
- **Project structure changes**: Are there significant organizational changes?
- **One Graph changes**: Are there new or modified GraphQL integrations (look for `onegraph` imports/functions, `.graphqls` files)?

**4. README Impact Assessment**: Based on AI analysis, determine if updates are needed for:
- Installation and setup instructions
- Usage examples and getting started guide
- Available scripts and commands
- Configuration documentation
- API documentation
- Project structure overview
</change_analysis>

<sections_to_review>

<project_overview>
**Project Title and Description:**
- Ensure project name matches current state
- Update description if scope or purpose has changed
- Verify badges (build status, version, etc.) are current
- Update any demo links or screenshots if UI has changed
</project_overview>

<installation_setup>
**Installation and Setup:**
- Verify runtime version requirements (Node.js, Python, Java, Go, etc.)
- Check if new dependencies require additional setup steps
- Update package manager commands (npm, yarn, pip, maven, gradle, etc.)
- Verify environment variable requirements
- Test that installation steps actually work
- Update any database setup or external service requirements
- Include One Graph setup if GraphQL integration is detected
</installation_setup>

<usage_examples>
**Usage and Examples:**
- Update code examples to reflect API changes
- Verify example outputs are still accurate
- Add examples for new features
- Remove examples for deprecated functionality
- Ensure import/include statements match current project structure
- Update configuration examples
- Include One Graph integration examples if GraphQL usage is detected
</usage_examples>

<scripts_commands>
**Available Scripts and Commands:**
- Review build configuration (package.json, Makefile, build.gradle, etc.)
- Update descriptions of what each script/command does
- Add new scripts or commands that have been introduced
- Remove scripts that no longer exist
- Verify script commands and their outputs
- Update build, test, and deployment instructions
</scripts_commands>

<api_documentation>
**API Documentation:**
- Update endpoint documentation if backend changes
- Verify request/response examples
- Update authentication requirements
- Document new API features or changes
- Update any SDK or client library information
</api_documentation>

<configuration>
**Configuration:**
- Update environment variable documentation
- Document new configuration options
- Update default values if they've changed
- Verify configuration file examples
- Document any breaking configuration changes
</configuration>

<project_structure>
**Project Structure:**
- Update directory tree if structure has changed significantly
- Document new important directories or files
- Update descriptions of what each major directory contains
- Remove references to deleted directories
</project_structure>

<development_workflow>
**Development Workflow:**
- Update development setup instructions
- Verify testing procedures
- Update debugging information
- Document new development tools or processes
- Update contribution guidelines if workflow has changed
</development_workflow>

<deployment>
**Deployment:**
- Update deployment instructions if process has changed
- Verify environment-specific setup
- Update any CI/CD pipeline documentation
- Document new deployment targets or methods
</deployment>


</sections_to_review>

<validation_checklist>

**Accuracy Validation:**
- [ ] All installation steps work from scratch
- [ ] All example code runs without errors
- [ ] All links are functional
- [ ] Version numbers are current
- [ ] Dependencies list matches actual requirements
- [ ] Environment setup instructions are complete
- [ ] One Graph integration examples work if GraphQL is used

**Completeness Check:**
- [ ] New features are documented
- [ ] Breaking changes are clearly noted
- [ ] Migration instructions provided for breaking changes
- [ ] All new configuration options documented
- [ ] New scripts or commands listed
- [ ] Updated screenshots or demos if UI changed

**Consistency Review:**
- [ ] Terminology is consistent throughout
- [ ] Code style in examples matches project standards
- [ ] Section formatting is uniform
- [ ] Cross-references between sections are accurate
</validation_checklist>

<update_strategy>

**Systematic Update Approach:**
1. **Preserve Structure**: Maintain existing README organization unless major restructuring is needed
2. **Incremental Updates**: Focus on sections impacted by recent changes
3. **Backward Compatibility**: Note any breaking changes prominently
4. **User-Centric**: Prioritize information that helps users get started quickly
5. **Maintenance-Friendly**: Use clear, maintainable documentation patterns

**Change Documentation:**
- Use clear headings for new sections
- Add "Updated" or "New" markers for recently changed content
- Consider adding a changelog section for significant updates
- Maintain version compatibility information where relevant

</update_strategy>

<quality_standards>

**Writing Standards:**
- Use clear, concise language
- Provide step-by-step instructions where appropriate
- Include expected outputs for commands
- Use consistent formatting and markdown syntax
- Ensure examples are copy-pasteable

**Technical Accuracy:**
- Test all code examples
- Verify all installation steps
- Check that all links work
- Ensure version numbers are accurate
- Validate that configuration examples work

**User Experience:**
- Structure information logically
- Provide quick start instructions
- Include troubleshooting for common issues
- Make it easy to find specific information
- Consider different user skill levels

</quality_standards>

<deliverables>

**Updated README.md:**
- Comprehensive update reflecting all relevant code changes
- Accurate installation and setup instructions
- Current usage examples and API documentation
- Updated project structure and configuration information
- Clear documentation of any breaking changes

**Change Summary:**
- Brief summary of what sections were updated and why
- List of any breaking changes that affect users
- Notes on any sections that may need future attention

</deliverables>

<guidelines>
- Focus on user-facing changes over internal implementation details
- Prioritize accuracy over comprehensiveness
- Use the existing README structure as a foundation
- Test instructions and examples before documenting them
- Consider the perspective of new users discovering the project
- Maintain professional, helpful tone throughout
- Use markdown best practices for formatting and readability
</guidelines>

<important_notes>
- Always test installation and setup instructions from scratch
- Verify that all code examples actually work
- Pay special attention to breaking changes that affect existing users
- Consider creating migration guides for significant changes
- Update any badges, links, or external references
- Ensure the README accurately represents the current state of the project
</important_notes>

</readme_update_documentation>
