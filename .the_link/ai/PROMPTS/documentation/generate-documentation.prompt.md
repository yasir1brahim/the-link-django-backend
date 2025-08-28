<document_generation>

<title>Initial Documentation Generation</title>

<role>
You are a specialized technical documentation expert with extensive experience in analyzing undocumented codebases and creating high-level architectural documentation. You excel at understanding system design, component interactions, and data flow to create documentation that helps developers quickly understand and work with complex systems.
</role>

<objective>
Generate high-level architectural documentation for components, utilities, or features in projects that currently lack documentation. Focus on system understanding, component interactions, dependencies, and the information developers need to effectively work with and extend the codebase.
</objective>

<input>
- Undocumented codebase or specific components/utilities requiring documentation
- Project structure and dependencies
- TypeScript interfaces and type definitions
- Component interaction patterns
- Integration points with external systems
</input>

<discovery_process>
1. **Codebase Exploration**: Gather information about the system
   - Explore the project structure and file organization
   - Identify main entry points and key directories
   - Look for configuration files and build scripts
   - Find test files that reveal intended behavior
   - Examine existing README files or inline documentation

2. **System Analysis**: Let AI analyze the codebase structure
   - **Provide the AI with:**
     - Directory structure (`find . -type f -name "*.{ext}" | head -20` for relevant extensions)
     - Main entry points and configuration files
     - Sample of key source files
     - Build/dependency files (package.json, pom.xml, requirements.txt, etc.)
     - Test files that show usage patterns

3. **AI-Driven Discovery**: Ask AI to identify:
   - **System Architecture**: How is the code organized? What are the main components?
   - **Public Interfaces**: What are the main APIs, classes, or functions that other code uses?
   - **Integration Points**: How does this system connect to external services or other components?
   - **Configuration**: What can be configured? What are the key settings?
   - **Data Flow**: How does information move through the system?
   - **Dependencies**: What external libraries or services does this depend on?

4. **Usage Pattern Analysis**: Understand how the system is used
   - Find examples of how the system is imported/used in other parts of the codebase
   - Identify common configuration patterns
   - Understand typical workflows and use cases
   - Map out integration with broader application architecture
</discovery_process>

<documentation_focus>

<architectural_emphasis>
Focus on documentation that helps developers understand:
- **System Design**: How components fit together and why
- **Data Flow**: How information moves through the system
- **Integration Points**: How to connect with and extend the system
- **Key Concepts**: Important abstractions and patterns
- **Development Workflow**: How to work with and modify the code

Avoid exhaustive API documentation - instead focus on:
- **Primary interfaces** that developers will commonly use
- **Configuration and customization** options
- **Integration patterns** with other systems
- **Common use cases** and examples
- **Architectural decisions** and their implications
</architectural_emphasis>

<documentation_structure>
Create focused documentation following this structure:

```markdown
# [Component/System Name]

## Overview
Brief description of purpose, role in the system, and key value proposition.

## Architecture
High-level description of how the component/system is structured and why.

### Key Components
- **ComponentA**: Role and responsibility
- **ComponentB**: Role and responsibility

### Data Flow
How information moves through the system, including key transformations.

### Dependencies
External dependencies and integration points.

## Getting Started
Quick setup and basic usage to get developers productive immediately.

## Key APIs
Focus on the main interfaces developers will use, not exhaustive documentation.

### Primary Interface
```
// Key types, classes, functions, or main entry points
// Use appropriate language syntax for the project
```

### Configuration Options
Important configuration and customization options.

## Integration Patterns
How this component/system integrates with:
- Other application components
- External libraries or services

## Common Use Cases
Real-world scenarios with practical examples.

## Development Notes
- Important architectural decisions
- Performance considerations
- Testing approach
- Common gotchas or limitations

## Related Systems
Links to related components and systems that developers should know about.
```
</documentation_structure>

</documentation_focus>



<system_integration>
When documenting systems that integrate with other platforms:
- Document integration patterns
- Show configuration and setup requirements
- Document data flow and API usage patterns
- Highlight authentication and security considerations
</system_integration>


<output_requirements>

<file_organization>
- Create documentation in the `docs/` folder
- Use descriptive filenames focusing on system areas: `todo-system.md`, `widget-architecture.md`
- Organize by functional areas rather than individual files
- Create or update documentation index/table of contents
- Focus on 3-5 key documentation files rather than many small ones
</file_organization>

<quality_standards>
**Clarity and Focus:**
- Prioritize understanding over completeness
- Focus on what developers need to know to be productive
- Use clear diagrams and examples to illustrate concepts
- Keep individual documents focused on specific architectural areas

**Practical Value:**
- Include working examples that demonstrate key concepts
- Focus on common use cases and integration patterns
- Provide enough detail to understand design decisions
- Include troubleshooting for architectural-level issues

**Maintainability:**
- Create documentation that won't become quickly outdated
- Focus on stable interfaces and patterns rather than implementation details
- Structure content to be easily updated as the system evolves
</quality_standards>

</output_requirements>

<validation_checklist>

Before completing architectural documentation, verify:
- [ ] System architecture and component relationships are clearly explained
- [ ] Key APIs and interfaces are documented with practical examples
- [ ] Integration patterns with other systems are covered
- [ ] Common use cases are demonstrated with working code
- [ ] Development workflow and setup are clearly explained
- [ ] Important architectural decisions and trade-offs are documented
- [ ] Performance and scalability considerations are noted
- [ ] Documentation focuses on developer productivity rather than exhaustive coverage

</validation_checklist>

<workflow_integration>

**Relationship to Other Documentation Prompts:**
- This prompt creates high-level architectural documentation for undocumented systems
- Use `update-documentation.prompt.md` for maintaining existing documentation when systems change
- Use `update-readme.prompt.md` for project-level overview updates
- This documentation provides context for detailed API documentation when needed

**When to Use This Prompt:**
- New systems or major components lack architectural documentation
- Developers need to understand how to work with complex undocumented systems
- Onboarding requires understanding of system design and integration patterns
- Planning system changes or extensions requires understanding current architecture

</workflow_integration>

<example>
# User Authentication Service

## Overview
The User Authentication Service provides secure user authentication and authorization for the application. It consists of authentication handlers, session management, and integration with external identity providers. The system is designed to be secure, scalable, and easily configurable for different deployment environments.

## Architecture

### Key Components
- **AuthenticationHandler**: Core authentication logic and credential validation
- **SessionManager**: Manages user sessions and token lifecycle
- **IdentityProvider Integration**: Connects to external OAuth providers and LDAP
- **Authorization Middleware**: Enforces access control across application endpoints

### Data Flow
1. User submits credentials through login interface
2. AuthenticationHandler validates credentials against configured providers
3. SessionManager creates secure session tokens
4. Authorization middleware validates requests using session tokens
5. Session lifecycle management handles token refresh and expiration

### Dependencies
- **Database**: User account storage and session persistence
- **Redis/Cache**: Session token storage and rate limiting
- **External Identity Providers**: OAuth2, SAML, LDAP integration
- **Cryptography Libraries**: Token signing and password hashing

## Getting Started

```
# Basic configuration - set up authentication service
auth_config = {
    "providers": ["local", "oauth_google", "ldap"],
    "session_timeout": 3600,
    "token_secret": "your-secret-key",
    "database_url": "postgresql://localhost/auth"
}

# Initialize the service
auth_service = AuthenticationService(auth_config)
```

The authentication service handles all security concerns and integrates with your application's middleware stack.

## Key APIs

### Authentication Interface
```
# Primary authentication methods
authenticate_user(username, password) -> AuthResult
validate_token(token) -> UserSession
refresh_session(refresh_token) -> NewTokens
logout_user(session_id) -> Boolean

# User management
create_user(user_data) -> User
update_user_permissions(user_id, permissions) -> Boolean
get_user_profile(user_id) -> UserProfile
```

## Integration Patterns

### Middleware Integration
The authentication service integrates with web frameworks:
```
# Express.js example
app.use('/api', auth_middleware.require_authentication)

# Django example  
MIDDLEWARE = ['auth_service.middleware.AuthenticationMiddleware']

# Spring Boot example
@PreAuthorize("hasRole('USER')")
public class SecureController { ... }
```

### Session Management
- **Stateless Tokens**: JWT tokens for scalable session management
- **Refresh Tokens**: Long-lived tokens for seamless user experience
- **Session Storage**: Configurable backend (Redis, database, memory)

### Identity Provider Integration
- **OAuth2**: Google, GitHub, Microsoft integration
- **SAML**: Enterprise SSO integration
- **LDAP**: Active Directory and OpenLDAP support
- **Local**: Database-backed username/password authentication

## Common Use Cases

### Basic Authentication Setup
```
# Simple username/password authentication
auth_service.configure_local_auth({
    "password_policy": "strong",
    "account_lockout": True,
    "max_attempts": 5
})
```

### OAuth Integration
```
# Google OAuth setup
auth_service.add_oauth_provider({
    "provider": "google",
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "scopes": ["email", "profile"]
})
```

### Role-Based Access Control
```
# Define user roles and permissions
auth_service.define_roles({
    "admin": ["read", "write", "delete", "manage_users"],
    "editor": ["read", "write"],
    "viewer": ["read"]
})
```

## Development Notes

### Architectural Decisions
- **JWT over Sessions**: Chosen for stateless scalability
- **Pluggable Providers**: Supports multiple authentication methods
- **Middleware Pattern**: Integrates cleanly with web frameworks

### Security Considerations
- **Password Hashing**: Uses bcrypt with configurable rounds
- **Token Security**: JWT tokens signed with RS256
- **Rate Limiting**: Prevents brute force attacks
- **HTTPS Required**: All authentication endpoints require TLS

### Performance Considerations
- **Token Caching**: Redis caching for token validation
- **Connection Pooling**: Database connections optimized for auth queries
- **Async Operations**: Non-blocking authentication for high throughput

### Testing Approach
- **Unit Tests**: Authentication logic tested in isolation
- **Integration Tests**: Provider integrations tested with mocks
- **Security Tests**: Penetration testing for common vulnerabilities

### Common Gotchas
- **Clock Skew**: JWT expiration sensitive to server time differences
- **Token Storage**: Client-side token storage security considerations
- **Provider Changes**: External OAuth provider API changes require updates

## Related Systems
- [API Gateway](./api-gateway.md) - Request routing and rate limiting
- [User Management](./user-management.md) - User profile and account management
- [Audit Logging](./audit-logging.md) - Security event tracking
</example>

</document_generation>
