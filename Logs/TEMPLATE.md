# Contribution Log Template

**Date**: YYYY-MM-DD HH:MM:SS UTC  
**Contributor**: @yourgithubusername  
**Task**: Brief one-line description of what you accomplished

## Context

Describe the problem or feature you were addressing. What was the state of the system before your changes?

- What issue were you solving?
- What feature were you adding?
- What was the motivation?

## Files Affected

List all files you created, modified, or deleted:

- `path/to/file1.py` - Created new service for X
- `path/to/file2.ts` - Modified to add Y functionality
- `path/to/file3.sql` - Added migration for Z
- `path/to/file4.md` - Updated documentation

## Technical Explanation

Provide a detailed breakdown of what you implemented and how it works.

### Component 1: [Name]

Describe the first major component of your changes:
- What it does
- How it works
- Key implementation details

```python
# Include relevant code snippets if helpful
def example_function():
    pass
```

### Component 2: [Name]

Describe the second major component:
- What it does
- How it works
- Key implementation details

### Integration

Explain how the components work together.

## Reasoning (WHY)

Explain why you made these specific choices:

1. **Choice 1**: Why did you choose approach X over Y?
2. **Choice 2**: Why did you structure the code this way?
3. **Choice 3**: What alternatives did you consider?

Reference specific requirements or architectural principles from:
- `Z/tech.md` §X.Y
- `Z/Overview.md` Pillar X
- Related issue #123

## Integration Notes

Describe how your changes integrate with existing systems:

### Dependencies

- Depends on: [List dependencies]
- Required by: [List what depends on this]

### Database Changes

- [ ] Added new tables
- [ ] Modified existing tables
- [ ] Added/updated RLS policies
- [ ] Created Alembic migration

### API Changes

- [ ] Added new endpoints
- [ ] Modified existing endpoints
- [ ] Updated GraphQL schema
- [ ] Changed request/response formats

### Configuration Changes

- [ ] Added new environment variables
- [ ] Updated Terraform configuration
- [ ] Modified secrets management
- [ ] Changed deployment process

## Testing

Describe how you tested your changes:

### Unit Tests

```bash
# Commands you ran
pytest tests/unit/test_your_feature.py -v
```

Results:
- X tests passed
- Coverage: Y%

### Integration Tests

```bash
# Commands you ran
pytest tests/integration/test_your_integration.py -v
```

Results:
- X tests passed
- Tested against real GCP services

### Manual Testing

Describe manual testing steps:
1. Step 1
2. Step 2
3. Step 3

Results:
- What worked
- What you verified

### Evaluation Harness

If applicable:
```bash
# Commands you ran
python scripts/evaluation/eval_X.py
```

Results:
- Evaluation results
- Performance metrics

## Tech.md Updates

Reference the sections you added or updated in `Z/tech.md`:

- Added §X.Y: [Section name]
- Updated §A.B: [Section name]
- Cross-referenced §C.D

Summary of architectural documentation changes:
- What you documented
- Why it's important
- How it fits into the overall architecture

## Potential Improvements

List at least one suggestion for future enhancement or optimization:

1. **Improvement 1**: [Description]
   - Why: [Reasoning]
   - Complexity: [Low/Medium/High]

2. **Improvement 2**: [Description]
   - Why: [Reasoning]
   - Complexity: [Low/Medium/High]

## Research Summary

If you used external resources (documentation, Stack Overflow, research papers):

- **Resource 1**: [URL or citation]
  - Key finding: [What you learned]
  - How it influenced your implementation: [Description]

- **Resource 2**: [URL or citation]
  - Key finding: [What you learned]
  - How it influenced your implementation: [Description]

## Performance Impact

Describe any performance implications:

- **Before**: [Baseline metrics if applicable]
- **After**: [New metrics]
- **Impact**: [Positive/Negative/Neutral]

## Security Considerations

Document any security implications:

- [ ] No security impact
- [ ] Reviewed for injection vulnerabilities
- [ ] Reviewed for authentication/authorization
- [ ] Reviewed for data leakage
- [ ] Reviewed for tenant isolation

## Breaking Changes

- [ ] No breaking changes
- [ ] Breaking changes (describe below)

If breaking changes:
- What breaks: [Description]
- Migration path: [How to upgrade]
- Deprecation timeline: [If applicable]

## Rollback Plan

How can this change be rolled back if needed?

1. Step 1
2. Step 2
3. Step 3

## Additional Notes

Any other context, observations, or learnings:

- Challenges encountered
- Interesting discoveries
- Lessons learned
- Future considerations

## Related Work

Link to related issues, PRs, or logs:

- Related issue: #123
- Related PR: #456
- Related log: `Logs/Daily/log-YYYY-MM-DD-HH:MM:SS.md`
- Builds on: [Previous work]

---

**Checklist for Completion**:
- [ ] All sections filled out
- [ ] Code snippets included where helpful
- [ ] Tech.md updated and referenced
- [ ] Testing documented
- [ ] Integration notes complete
- [ ] Security reviewed
- [ ] Performance impact assessed
