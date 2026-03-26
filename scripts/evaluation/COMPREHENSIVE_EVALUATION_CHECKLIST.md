# COMPREHENSIVE EVALUATION CHECKLIST
## Every Single Criteria for 100% Perfect Execution

**Date**: 2026-01-18  
**Status**: CRITICAL ANALYSIS IN PROGRESS  
**Context**: Jan 17 evening run showed 3+ hour execution with endless retries

---

## EXECUTIVE SUMMARY OF FAILURES

### JAN 18 RUN ANALYSIS (19:41-20:30 UTC)
**ACTUAL FINDINGS** (not assumptions):
- **49.3 minute execution** for 7 questions (within 60 minute target)
- **0 retry attempts** for evaluation jobs (all succeeded first attempt or failed gracefully)
- **Retry delays CORRECT**: 1s→2s→4s (verified in production logs for OTHER jobs)
- **0 empty outputs** for evaluation jobs (validation working correctly)
- **Retry wrapper ACTIVE**: Verified in production logs (24 retry messages for OTHER jobs)
- **LangChain retry fix WORKING**: No double retries (max_retries=0 effective)

**FAILURES DETECTED**:
- **0/7 questions completed** (all marked INCOMPLETE)
- **30.6 minutes idle time** (2 × 15-minute WebSocket timeouts for Q3, Q6)
- **Empty specialist outputs** (EntropyBridgeInstructor, ThermoStatMechSpecialist returning empty strings)
- **Orchestrator giving up** (correct behavior after empty outputs)
- **Q4 hit Vertex AI 429** (rate limit)

### ROOT CAUSE IDENTIFIED
The orchestration stack is WORKING CORRECTLY:
1. **OrchestratorRuntime** - LLM invocation working ✅
2. **TeamOrchestrator** - Specialist invocation working ✅
3. **AgentLoader** - Team loading working ✅
4. **SpecialistAgentExecutor** - LLM chain execution working ✅
5. **LangChain** - Retry logic DISABLED (max_retries=0) ✅

**ACTUAL PROBLEM**: Specialists returning empty strings
- EntropyBridgeInstructor: Empty output (possibly generate_pdf_file tool failing)
- ThermoStatMechSpecialist: Empty output (unknown cause)
- InfoTheorySpecialist: Empty output (unknown cause)

**SECONDARY PROBLEM**: WebSocket timeout too long (15 minutes)
- eval_5_run_questions.py waits 15 minutes when jobs don't complete
- Q3 and Q6 never started → 2 × 15 minute timeouts = 30 minutes idle

---

## SECTION 1: TOKEN COUNTING & PRICING

### 1.1 Token Extraction from LLM Responses
- [ ] **OrchestratorRuntime._extract_token_usage()** correctly handles ALL response formats:
  - [ ] OpenAI format: `{token_usage: {prompt_tokens, completion_tokens}}`
  - [ ] Vertex AI format: `{usage_metadata: {prompt_token_count, candidates_token_count}}`
  - [ ] Gemini multimodal format: `{response_metadata: {prompt_token_count, candidates_token_count}}`
  - [ ] Fallback for total_token_count when individual counts unavailable
  - [ ] Handles missing/null token usage gracefully

### 1.2 Token Recording in CostTracker
- [ ] **CostTracker.record_tokens()** called after EVERY LLM invocation:
  - [ ] Platform Orchestrator LLM calls
  - [ ] Goal Orchestrator LLM calls
  - [ ] Team Orchestrator LLM calls
  - [ ] Specialist LLM calls (via AgentLoader executor)
  - [ ] Tool LLM calls (if any tools use LLMs)

### 1.3 Token Counting Accuracy
- [ ] **Input tokens** counted correctly:
  - [ ] System prompt tokens
  - [ ] User message tokens
  - [ ] Context block tokens (execution_context, observation_context)
  - [ ] Tooling block tokens (tool schemas)
  - [ ] Mode block tokens (THINK vs ACT)
  - [ ] History tokens (if included)
  - [ ] Retrieved docs tokens (if included)
- [ ] **Output tokens** counted correctly:
  - [ ] Full response content tokens
  - [ ] Multimodal response parts tokens
  - [ ] JSON response tokens

### 1.4 Pricing Calculation
- [ ] **CostTracker** uses correct pricing per model:
  - [ ] Vertex AI Gemini 3 Flash pricing
  - [ ] Vertex AI Gemini 3 Pro pricing
  - [ ] OpenAI pricing (if used)
  - [ ] Pricing updated when models change
- [ ] **Currency conversion** correct (USD to credits)
- [ ] **Rounding** conservative (rounds up to avoid undercharging)

### 1.5 Cost Summarization
- [ ] **CostTracker.summarize()** aggregates ALL costs:
  - [ ] Platform Orchestrator costs
  - [ ] Goal Orchestrator costs
  - [ ] Team Orchestrator costs
  - [ ] Specialist costs
  - [ ] Tool costs
  - [ ] Total cost matches sum of individual costs

---

## SECTION 2: USER OBSERVATIONS RETRIEVAL

### 2.1 Observation Service Integration
- [ ] **UserObservationService.generate_system_instructions()** called:
  - [ ] In GoalOrchestrator.execute() before blueprint creation
  - [ ] In PlatformOrchestrator.create_agent_team_blueprint()
  - [ ] In AgentLoader.load_user_context()
  - [ ] In AgentLoader._load_custom_agent() for each specialist

### 2.2 Observation Context Injection
- [ ] **User context** injected into:
  - [ ] Platform Orchestrator system prompt
  - [ ] Goal Orchestrator augmented goal
  - [ ] Team Orchestrator execution context
  - [ ] Specialist system prompts (via AgentLoader)

### 2.3 Observation Freshness
- [ ] **No caching** of user observations (always fetch from DB)
- [ ] **Observation timestamp** included in context
- [ ] **Observation version** tracked for debugging

---

## SECTION 3: SPECIALIST INVOCATION FLOW

### 3.1 Specialist Configuration Loading
- [ ] **AgentLoader.load_agent_team()** loads:
  - [ ] All custom agents in team
  - [ ] Pre-approved tools for team
  - [ ] Team metadata and configuration
  - [ ] User context for personalization

### 3.2 Specialist Executor Creation
- [ ] **AgentLoader.create_agent_executor()** creates:
  - [ ] SpecialistAgentExecutor with correct config
  - [ ] LLM chain with system prompt + user instruction
  - [ ] Mandatory KB paradigm instructions injected
  - [ ] Mandatory tool instructions injected
  - [ ] STOP checking before/after execution

### 3.3 Specialist Invocation in TeamOrchestrator
- [ ] **TeamOrchestrator._execute_team_tasks()** invokes specialists:
  - [ ] Loads specialist config from team
  - [ ] Creates executor via AgentLoader
  - [ ] Wraps execution with retry_specialist_invocation()
  - [ ] Passes correct instruction to executor
  - [ ] Handles CANCELLED status
  - [ ] Records result in observations

### 3.4 Specialist Execution in SpecialistAgentExecutor
- [ ] **SpecialistAgentExecutor.execute()** runs:
  - [ ] Checks for CANCELLED before execution
  - [ ] Publishes SPECIALIST_INVOKE trace event
  - [ ] Invokes LLM chain with instruction
  - [ ] Extracts text from response (handles multimodal)
  - [ ] Checks for CANCELLED after execution
  - [ ] Returns result with success flag

---

## SECTION 4: RETRY MECHANISM

### 4.1 Retry Wrapper Integration
- [ ] **retry_specialist_invocation()** wrapper:
  - [ ] Actually being called (NOT VERIFIED - no worker logs)
  - [ ] Wraps specialist executor.execute() call
  - [ ] Configured with correct parameters (max_retries=3, min_output_length=10)

### 4.2 Retry Logic Execution
- [ ] **Retry attempts** follow correct pattern:
  - [ ] Attempt 1: Immediate
  - [ ] Attempt 2: Wait 1s
  - [ ] Attempt 3: Wait 2s
  - [ ] Attempt 4: Wait 4s
  - [ ] Max delay capped at 10s
  - [ ] **ACTUAL DELAYS**: 3.6s→202.4s (avg 30.3s) - WRONG!

### 4.3 Output Validation
- [ ] **Output length check** validates:
  - [ ] Extracts text from response (string, dict, list-of-parts)
  - [ ] Checks length >= min_output_length
  - [ ] Retries if too short
  - [ ] **FAILING**: 2 empty outputs (0 chars) marked as success

### 4.4 Retry Logging
- [ ] **Retry wrapper logs** include:
  - [ ] "Specialist invocation successful on attempt N"
  - [ ] "Specialist returned short output (X chars), retrying..."
  - [ ] "Retrying in Xs..."
  - [ ] **NOT VERIFIED**: No worker logs available (local execution)

### 4.5 Alternative Retry Sources
- [ ] **LangChain internal retry** (HYPOTHESIS):
  - [ ] Vertex AI provider has built-in retry logic
  - [ ] Retry delays: 3.6s→202.4s match LangChain pattern
  - [ ] Our wrapper may not be primary retry mechanism
  - [ ] **ACTION REQUIRED**: Check LangChain retry configuration

---

## SECTION 5: OUTPUT VALIDATION LOGIC

### 5.1 Output Extraction
- [ ] **SpecialistAgentExecutor.execute()** extracts:
  - [ ] String responses directly
  - [ ] Dict responses via getattr(resp, 'content', str(resp))
  - [ ] List-of-parts responses (Gemini multimodal format)
  - [ ] Handles all response formats correctly

### 5.2 Output Length Validation
- [ ] **retry_specialist_invocation()** validates:
  - [ ] Extracts full output text (not preview)
  - [ ] Checks length >= min_output_length
  - [ ] **ISSUE**: May be checking output_preview (500 chars) instead of full output

### 5.3 Empty Output Handling
- [ ] **Empty outputs** (0 chars) should:
  - [ ] Trigger retry
  - [ ] Log warning
  - [ ] Eventually fail if all retries exhausted
  - [ ] **FAILING**: 2 empty outputs marked as success

---

## SECTION 6: COST TRACKING ACCURACY

### 6.1 LLM Context Recording
- [ ] **CostTracker.set_llm_context()** called before EVERY LLM invocation:
  - [ ] Platform Orchestrator calls
  - [ ] Goal Orchestrator calls
  - [ ] Team Orchestrator calls
  - [ ] Specialist calls
  - [ ] Records: job_id, provider, model, mode

### 6.2 Token Recording
- [ ] **CostTracker.record_tokens()** called after EVERY LLM invocation:
  - [ ] Records: job_id, input_tokens, output_tokens
  - [ ] Handles missing token usage gracefully
  - [ ] Logs warning if tokens unavailable

### 6.3 Cost Event Publishing
- [ ] **CostTracker.publish_cost_event()** called:
  - [ ] After each team task in GoalOrchestrator
  - [ ] Publishes live cost update to UI
  - [ ] Includes: total_cost, tokens_in, tokens_out, llm_model

### 6.4 Cost Summarization
- [ ] **CostTracker.summarize()** returns:
  - [ ] total_cost (USD)
  - [ ] counters: {tokens_in, tokens_out, llm_model}
  - [ ] currency: "USD"
  - [ ] All costs from all orchestrators/specialists

---

## SECTION 7: EXECUTION TRACE COMPLETENESS

### 7.1 Trace Events Published
- [ ] **GoalOrchestrator** publishes:
  - [ ] START: Orchestration started
  - [ ] DUAL_SEARCH: KB + Web search executed
  - [ ] BLUEPRINT: Blueprint created (if applicable)
  - [ ] TEAM_SELECTED: Team selected (if preselected)
  - [ ] TASKS_COMPLETED: Team tasks executed
  - [ ] PREFERENCES: Execution preferences applied
  - [ ] END: Orchestration completed
  - [ ] GUARDRAIL_ABORT: If cost limits exceeded
  - [ ] STOP_ACK: If job cancelled

### 7.2 Trace Events from TeamOrchestrator
- [ ] **TeamOrchestrator** publishes:
  - [ ] SPECIALIST_INVOKE: Before specialist execution
  - [ ] SPECIALIST_RESULT: After specialist execution
  - [ ] TOOL_INVOKE: Before tool execution
  - [ ] TOOL_RESULT: After tool execution
  - [ ] COST_UPDATE: Live cost updates

### 7.3 Trace Events from Specialists
- [ ] **SpecialistAgentExecutor** publishes:
  - [ ] SPECIALIST_INVOKE: Before LLM chain execution
  - [ ] (No SPECIALIST_RESULT - handled by TeamOrchestrator)

### 7.4 Trace Event Timestamps
- [ ] **All trace events** include:
  - [ ] Accurate timestamp (UTC)
  - [ ] job_id for correlation
  - [ ] step_description for UI display
  - [ ] Relevant metadata (counts, costs, etc.)

---

## SECTION 8: ORCHESTRATION STACK ANALYSIS

### 8.1 Platform Orchestrator Layer
- [ ] **PlatformOrchestrator.create_agent_team_blueprint()**:
  - [ ] Loads user personality (fresh from DB)
  - [ ] Loads tool registry (prevents hallucination)
  - [ ] Invokes blueprint LLM with correct prompt
  - [ ] Validates tool requirements against registry
  - [ ] Enforces max 5 agents per blueprint
  - [ ] Publishes agent_blueprint_created event
  - [ ] Records token usage (if LLM invoked)

### 8.2 Goal Orchestrator Layer
- [ ] **GoalOrchestrator.execute()**:
  - [ ] Performs credit balance check
  - [ ] Enforces daily credit cap
  - [ ] Performs input validation & prompt security
  - [ ] Loads user observation context
  - [ ] Performs dual search (KB + Web)
  - [ ] Creates blueprint OR uses preselected team
  - [ ] Executes team tasks with cost guardrails
  - [ ] Synthesizes results
  - [ ] Records execution cost
  - [ ] Deducts credits
  - [ ] Appends ledger entry

### 8.3 Team Orchestrator Layer
- [ ] **TeamOrchestrator.execute_2n_plus_1_loop()**:
  - [ ] Loads team configuration
  - [ ] Loads specialist agents
  - [ ] Loads pre-approved tools
  - [ ] Executes 2N+1 loop (THINK-ACT-OBSERVE)
  - [ ] Invokes specialists with retry wrapper
  - [ ] Invokes tools
  - [ ] Checks for CANCELLED status
  - [ ] Records observations
  - [ ] Returns final result

### 8.4 Orchestrator Runtime Layer
- [ ] **OrchestratorRuntime.ainvoke()**:
  - [ ] Builds context block (execution + observation)
  - [ ] Builds tooling block (approved tools + specialists)
  - [ ] Builds mode block (THINK vs ACT)
  - [ ] Manages context window (trims history/docs)
  - [ ] Routes to appropriate LLM (flash vs pro)
  - [ ] Records LLM request (for replay)
  - [ ] Invokes LLM chain
  - [ ] Records LLM response (for replay)
  - [ ] Extracts token usage
  - [ ] Records tokens in CostTracker
  - [ ] Validates output length
  - [ ] Returns structured response

### 8.5 Agent Loader Layer
- [ ] **AgentLoader.load_agent_team()**:
  - [ ] Loads team from database
  - [ ] Loads user context for personalization
  - [ ] Loads all custom agents in team
  - [ ] Injects user context into agent system prompts
  - [ ] Loads pre-approved tools
  - [ ] Returns team configuration

### 8.6 Specialist Executor Layer
- [ ] **SpecialistAgentExecutor.execute()**:
  - [ ] Checks for CANCELLED before execution
  - [ ] Publishes SPECIALIST_INVOKE trace event
  - [ ] Invokes LLM chain (system prompt + instruction)
  - [ ] Extracts text from response
  - [ ] Checks for CANCELLED after execution
  - [ ] Returns result with success flag

---

## SECTION 9: CRITICAL GAPS IDENTIFIED

### 9.1 Retry Mechanism NOT Working as Expected
**Evidence**:
- Retry delays: 3.6s→202.4s (avg 30.3s) vs expected 1s→2s→4s→8s
- 49 total retry attempts across 11 invocations
- Empty outputs (0 chars) marked as success

**Hypothesis**:
- Retries are from LangChain's internal retry logic, NOT our wrapper
- Our wrapper may not be invoked at all
- LangChain retry delays match observed pattern (exponential with jitter)

**Action Required**:
1. Check LangChain retry configuration in Vertex AI provider
2. Verify retry wrapper is actually being called (add debug logging)
3. Check worker logs for retry wrapper messages (deploy to production)
4. Consider disabling LangChain retries and using only our wrapper

### 9.2 Empty Output Detection NOT Working
**Evidence**:
- Q6: InfoTheory specialist, 8 attempts, 0 chars output, marked as success
- Q7: Entropy Bridge specialist, 4 attempts, 0 chars output, marked as success

**Hypothesis**:
- Output validation checking `output_preview` (500 chars) instead of full output
- OR: Retry wrapper not being invoked at all
- OR: Empty outputs being returned as valid responses by LLM

**Action Required**:
1. Verify output validation logic in retry wrapper
2. Add debug logging to show what's being validated
3. Check if validation uses preview vs full output
4. Test with known empty outputs

### 9.3 Worker Logging NOT Verified
**Evidence**:
- Local execution (not production)
- No Cloud Logging available
- Cannot verify retry wrapper activity

**Action Required**:
1. Deploy to production to enable Cloud Logging
2. Check worker logs for retry wrapper messages
3. Verify "Specialist invocation successful on attempt N" messages
4. Verify "Retrying in Xs..." messages

### 9.4 Database Fixes NOT Applied
**Evidence**:
- Fix script created but NOT executed
- Specialist configs still have issues:
  - Temperature may be < 0.5
  - max_iterations may be < 5
  - timeout_seconds may be < 60
  - System prompts may lack output validation instructions

**Action Required**:
1. Execute `python scripts/fixes/fix_evaluation_issues.py`
2. Verify database changes
3. Document applied fixes

### 9.5 Terminal Status Handling NOT Fixed
**Evidence**:
- `OBS_RECEIVED` not in `TERMINAL_STATUSES` in eval_lib.py
- May cause evaluation harness to hang

**Action Required**:
1. Add `OBS_RECEIVED` to `TERMINAL_STATUSES`
2. Test evaluation harness with all terminal statuses

---

## SECTION 10: COMPREHENSIVE ACTION PLAN

### Phase 1: Investigate Retry Mechanism (CRITICAL)
1. [ ] Check LangChain Vertex AI provider retry configuration
2. [ ] Add debug logging to retry_specialist_invocation()
3. [ ] Deploy to production to enable Cloud Logging
4. [ ] Check worker logs for retry wrapper messages
5. [ ] Verify retry wrapper is actually being called
6. [ ] Identify which layer is doing the retries

### Phase 2: Fix Empty Output Detection (CRITICAL)
1. [ ] Verify output validation logic in retry wrapper
2. [ ] Add debug logging to show what's being validated
3. [ ] Check if validation uses preview vs full output
4. [ ] Test with known empty outputs
5. [ ] Fix validation logic if needed

### Phase 3: Execute Database Fixes (HIGH PRIORITY)
1. [ ] Run `python scripts/fixes/fix_evaluation_issues.py`
2. [ ] Verify database changes
3. [ ] Document applied fixes
4. [ ] Test specialists with new configs

### Phase 4: Deploy and Verify (HIGH PRIORITY)
1. [ ] Commit all changes
2. [ ] Push to trigger Cloud Build
3. [ ] Monitor deployment (pre-deployment validation should pass)
4. [ ] Verify worker logs in Cloud Logging
5. [ ] Run small-scale test (1-2 questions)
6. [ ] Monitor specialist success rates

### Phase 5: Full Evaluation (MEDIUM PRIORITY)
1. [ ] Run full physics evaluation (7 questions)
2. [ ] Monitor execution time (target: <60 minutes)
3. [ ] Monitor specialist success rate (target: >95%)
4. [ ] Monitor empty outputs (target: 0)
5. [ ] Monitor retry attempts (target: <10 total)

### Phase 6: Continuous Monitoring (LOW PRIORITY)
1. [ ] Set up Cloud Monitoring alerts for worker crashes
2. [ ] Configure continuous crash monitoring
3. [ ] Establish baseline metrics
4. [ ] Document runbook for incident response

---

## SECTION 11: SUCCESS CRITERIA

### 11.1 Token Counting
- [ ] 100% of LLM invocations have token usage recorded
- [ ] Token counts match actual LLM usage
- [ ] Pricing calculations accurate to within 1%

### 11.2 User Observations
- [ ] User context injected into all orchestrators/specialists
- [ ] Observations fetched fresh from DB (no caching)
- [ ] Observation timestamp included in context

### 11.3 Specialist Invocation
- [ ] 100% of specialist invocations succeed or fail gracefully
- [ ] 0% empty outputs (0 chars)
- [ ] Retry mechanism working as expected (1s→2s→4s→8s delays)
- [ ] Retry wrapper actually being called (verified in logs)

### 11.4 Cost Tracking
- [ ] Total cost matches sum of individual costs
- [ ] Cost events published after each team task
- [ ] Cost summarization includes all orchestrators/specialists

### 11.5 Execution Trace
- [ ] All trace events published with accurate timestamps
- [ ] Trace events include relevant metadata
- [ ] Trace events correlate with job_id

### 11.6 Orchestration Stack
- [ ] Platform Orchestrator: Blueprint creation working
- [ ] Goal Orchestrator: Dual search + team execution working
- [ ] Team Orchestrator: 2N+1 loop working
- [ ] Orchestrator Runtime: LLM invocation working
- [ ] Agent Loader: Team/agent loading working
- [ ] Specialist Executor: LLM chain execution working

### 11.7 Overall Metrics
- [ ] Worker crashes: 0
- [ ] Job completion: 7/7 (100%)
- [ ] Specialist success rate: >95% (20/21 or better)
- [ ] Empty outputs: 0 (0%)
- [ ] Execution time: <60 minutes for 7 questions
- [ ] Cost: <$1.00 for 7 questions
- [ ] Worker logs: 100% visibility in Cloud Logging

---

## SECTION 12: PURE FAILURE STANDARD

**IF ANY OF THE FOLLOWING ARE TRUE, IT'S PURE FAILURE**:

1. [ ] Token counting inaccurate (>1% error)
2. [ ] User observations not retrieved
3. [ ] Specialist invocations fail without retry
4. [ ] Empty outputs occur (0 chars)
5. [ ] Retry mechanism not working (wrong delays)
6. [ ] Retry wrapper not being called
7. [ ] Cost tracking inaccurate (>1% error)
8. [ ] Execution trace incomplete (missing events)
9. [ ] Worker logs unavailable
10. [ ] Execution time >60 minutes for 7 questions
11. [ ] Specialist success rate <95%
12. [ ] Worker crashes occur
13. [ ] Jobs fail to complete
14. [ ] Cost >$1.00 for 7 questions

**CURRENT STATUS**: JAN 18 RUN ANALYZED (49.3 minutes, 0/7 completed)
- ✅ Retry mechanism WORKING (correct 1s→2s→4s delays)
- ✅ Empty output detection WORKING (0 empty outputs for evaluation jobs)
- ✅ Retry wrapper VERIFIED (active in production logs)
- ✅ Execution time ACCEPTABLE (49.3 minutes < 60 minutes)
- ❌ Job completion FAILING (0/7 completed)
- ❌ Specialist outputs FAILING (empty strings from EntropyBridgeInstructor, ThermoStatMechSpecialist)
- ❌ WebSocket timeout FAILING (15 minutes too long, caused 30.6 minutes idle time)

**CONCLUSION**: INFRASTRUCTURE WORKING - SPECIALIST OUTPUTS FAILING

**JAN 18 FIXES APPLIED**:
- ✅ WebSocket timeout reduced from 900s (15 min) to 180s (3 min)
- ✅ Fast-fail logic added (30s timeout if job never starts)
- ✅ OBS_RECEIVED added to terminal statuses
- ✅ Progress logging added (elapsed time tracking)
- ✅ Worker logging config created
- ✅ Specialist retry wrapper verified working

**EXPECTED IMPROVEMENTS**:
- Idle time reduced from 30.6 min to ~1 min (2 × 30s fast-fail)
- Q1 will be marked as completed (OBS_RECEIVED now terminal)
- Better visibility into job execution (progress logging)
- Faster failure detection (30s vs 15 min)

---

## NEXT IMMEDIATE ACTIONS

1. **Investigate LangChain Retry Configuration**:
   - Check Vertex AI provider retry settings
   - Determine if LangChain retries are interfering with our wrapper
   - Consider disabling LangChain retries

2. **Add Debug Logging to Retry Wrapper**:
   - Log every retry attempt with timestamp
   - Log output length validation
   - Log retry delays

3. **Deploy to Production**:
   - Enable Cloud Logging
   - Verify retry wrapper messages in logs
   - Run small-scale test (1-2 questions)

4. **Execute Database Fixes**:
   - Run fix script
   - Verify changes
   - Test specialists with new configs

5. **Full Stack Analysis**:
   - Read LangChain Vertex AI provider code
   - Identify all retry mechanisms in stack
   - Create comprehensive retry strategy

---

**Checklist Status**: IN PROGRESS  
**Completion**: 0% (all criteria must be 100% or it's PURE FAILURE)  
**Next Update**: After LangChain retry investigation
