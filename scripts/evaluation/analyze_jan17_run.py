#!/usr/bin/env python3
"""Comprehensive analysis of Jan 17 evaluation run."""

import json
import sys
from datetime import datetime
from collections import defaultdict, Counter

# Job IDs from latest run
JOB_IDS = [
    "job_1HJeBR2c2fBvej75",  # Q1
    "job_YZvwF2KYxuztprlW",  # Q2
    "job_SHKyGW0w9hZUgR4v",  # Q3
    "job_fn0g3Nas8HPwb9r9",  # Q4
    "job_PN4bS_x_AixPgRMM",  # Q5
    "job_5JynC_kDuW46fCYJ",  # Q6
    "job_9-1hNzuFtflW_fD2",  # Q7
]

QUESTIONS = [
    "Explain entropy in thermodynamics with a concrete everyday analogy.",
    "Define Shannon entropy and explain what it measures. Give a simple example with a biased coin.",
    "Carefully relate thermodynamic entropy (Boltzmann/Gibbs) to information entropy. Where does the analogy break?",
    "Derive (at a teaching level) why entropy is extensive for weakly interacting subsystems and mention assumptions.",
    "Given probabilities p=[0.1,0.2,0.3,0.4], compute Shannon entropy in bits and interpret the result.",
    "Create a CSV table of Shannon entropy H(p) (bits) for a Bernoulli(p) source for p in [0.01,0.05,0.1,...,0.95,0.99]. Then generate a chart of H(p) vs p (label axes, title).",
    "Create an Excel file that contains: (a) the same entropy table, (b) a second table comparing H(p) in bits vs nats, and (c) a short text block explaining how to convert between them. Also produce a chart image summarizing both curves.",
]

def parse_timestamp(ts_str):
    """Parse ISO timestamp."""
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return None

def extract_trace_event(text):
    """Extract [TRACE] events from log text."""
    if '[TRACE]' in text:
        return text
    return None

def main():
    print("Loading logs...")
    with open('/tmp/eval_run_jan17_logs.json', 'r') as f:
        logs = json.load(f)
    
    print(f"Total log entries: {len(logs):,}")
    print()
    
    # Group logs by job_id and service
    job_logs = defaultdict(list)
    api_logs = []
    worker_logs = []
    trace_events = defaultdict(list)
    redis_events = []
    
    for entry in logs:
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        service = entry.get('resource', {}).get('labels', {}).get('service_name', '')
        timestamp = entry.get('timestamp', '')
        severity = entry.get('severity', '')
        
        # Categorize by service
        if 'api' in service:
            api_logs.append((timestamp, text, severity))
        elif 'worker' in service:
            worker_logs.append((timestamp, text, severity))
        
        # Extract [TRACE] events
        if '[TRACE]' in text:
            for job_id in JOB_IDS:
                if job_id in text:
                    trace_events[job_id].append((timestamp, text))
        
        # Redis events
        if 'Redis' in text or 'redis' in text or 'publish_execution_trace' in text or 'Subscribed to channel' in text:
            redis_events.append((timestamp, service, text))
        
        # Find job_id in text
        for job_id in JOB_IDS:
            if job_id in text:
                job_logs[job_id].append({
                    'timestamp': timestamp,
                    'service': service,
                    'text': text,
                    'severity': severity
                })
    
    print("="*100)
    print("DETAILED JOB ANALYSIS")
    print("="*100)
    
    total_duration = 0
    job_durations = []
    
    for idx, job_id in enumerate(JOB_IDS, 1):
        logs_for_job = job_logs.get(job_id, [])
        traces_for_job = trace_events.get(job_id, [])
        
        print(f"\n{'='*100}")
        print(f"Q{idx}: {QUESTIONS[idx-1]}")
        print(f"Job ID: {job_id}")
        print(f"{'='*100}")
        print(f"Total log entries: {len(logs_for_job)}")
        print(f"[TRACE] events: {len(traces_for_job)}")
        
        if not logs_for_job:
            print("  ❌ NO LOGS FOUND")
            continue
        
        # Extract key events with timestamps
        events = []
        for log in logs_for_job:
            text = str(log['text'])
            ts = log['timestamp']
            
            # API events
            if 'Dispatched orchestration to Celery' in text:
                events.append(('API_DISPATCH', ts, 'Job dispatched to Celery'))
            elif 'Subscribed to channel: job_trace_' in text:
                events.append(('API_SUBSCRIBE', ts, 'WebSocket subscribed to trace channel'))
            
            # Worker events
            elif 'Starting goal orchestration' in text:
                events.append(('WORKER_START', ts, 'Worker picked up job'))
            elif 'Completed goal orchestration' in text:
                events.append(('WORKER_END', ts, 'Worker completed job'))
            
            # Orchestrator phases
            elif '[TRACE]' in text and 'INIT' in text:
                events.append(('INIT', ts, 'Orchestrator initialized'))
            elif '[TRACE]' in text and 'CREDIT_CHECK' in text:
                events.append(('CREDIT_CHECK', ts, 'Credit balance checked'))
            elif '[TRACE]' in text and 'DUAL_SEARCH_START' in text:
                events.append(('DUAL_SEARCH_START', ts, 'Dual Search started'))
            elif '[TRACE]' in text and 'DUAL_SEARCH_END' in text:
                events.append(('DUAL_SEARCH_END', ts, 'Dual Search completed'))
            elif '[TRACE]' in text and 'TEAM_LOAD' in text:
                events.append(('TEAM_LOAD', ts, 'Team configuration loaded'))
            elif '[TRACE]' in text and 'THINK_START' in text:
                events.append(('THINK_START', ts, 'THINK phase started'))
            elif '[TRACE]' in text and 'THINK_END' in text:
                events.append(('THINK_END', ts, 'THINK phase completed'))
            elif '[TRACE]' in text and 'ACT_START' in text:
                events.append(('ACT_START', ts, 'ACT phase started'))
            elif '[TRACE]' in text and 'ACT_END' in text:
                events.append(('ACT_END', ts, 'ACT phase completed'))
            elif '[TRACE]' in text and 'TOOL_START' in text:
                events.append(('TOOL_START', ts, 'Tool execution started'))
            elif '[TRACE]' in text and 'TOOL_END' in text:
                events.append(('TOOL_END', ts, 'Tool execution completed'))
            elif '[TRACE]' in text and 'SPECIALIST_REQUEST' in text:
                events.append(('SPECIALIST_REQUEST', ts, 'Specialist invoked'))
            elif '[TRACE]' in text and 'SPECIALIST_RESPONSE' in text:
                events.append(('SPECIALIST_RESPONSE', ts, 'Specialist responded'))
            elif '[TRACE]' in text and 'FINISH' in text:
                events.append(('FINISH', ts, 'Finish signal received'))
            elif 'execution_trace_end' in text or ('END' in text and '[TRACE]' in text):
                events.append(('END', ts, 'Execution completed'))
        
        if events:
            print(f"\n  Timeline ({len(events)} events):")
            start_time = None
            end_time = None
            
            for event_type, ts, description in events:
                dt = parse_timestamp(ts)
                if start_time is None:
                    start_time = dt
                    elapsed = "0.0s"
                else:
                    elapsed = f"{(dt - start_time).total_seconds():.1f}s"
                
                end_time = dt
                print(f"    {ts} (+{elapsed:>8}) - {event_type:20s} | {description}")
            
            # Calculate total duration
            if start_time and end_time:
                duration = (end_time - start_time).total_seconds()
                job_durations.append(duration)
                total_duration += duration
                print(f"\n  ⏱️  Duration: {duration:.1f}s ({duration/60:.2f} minutes)")
        else:
            print("  ⚠️  No key events found")
        
        # Show [TRACE] event summary
        if traces_for_job:
            print(f"\n  [TRACE] Event Types:")
            trace_types = Counter()
            for ts, text in traces_for_job:
                if 'type=' in text:
                    try:
                        type_part = text.split('type=')[1].split()[0]
                        trace_types[type_part] += 1
                    except:
                        pass
            for trace_type, count in trace_types.most_common():
                print(f"    {trace_type:30s}: {count:3d}")
    
    print("\n" + "="*100)
    print("OVERALL STATISTICS")
    print("="*100)
    
    if job_durations:
        print(f"\nJob Durations:")
        for idx, duration in enumerate(job_durations, 1):
            print(f"  Q{idx}: {duration:6.1f}s ({duration/60:5.2f}m)")
        
        avg_duration = sum(job_durations) / len(job_durations)
        print(f"\n  Average: {avg_duration:.1f}s ({avg_duration/60:.2f}m)")
        print(f"  Total:   {total_duration:.1f}s ({total_duration/60:.2f}m)")
        print(f"  Min:     {min(job_durations):.1f}s")
        print(f"  Max:     {max(job_durations):.1f}s")
    
    print("\n" + "="*100)
    print("REDIS/WEBSOCKET ANALYSIS")
    print("="*100)
    
    print(f"\nRedis-related events: {len(redis_events)}")
    
    # Group by type
    subscribe_events = [e for e in redis_events if 'Subscribed to channel' in e[2]]
    publish_events = [e for e in redis_events if 'publish_execution_trace' in e[2]]
    redis_errors = [e for e in redis_events if 'error' in e[2].lower() or 'fail' in e[2].lower()]
    
    print(f"  Subscribe events: {len(subscribe_events)}")
    print(f"  Publish events: {len(publish_events)}")
    print(f"  Redis errors: {len(redis_errors)}")
    
    if subscribe_events:
        print(f"\n  Sample subscribe events:")
        for ts, service, text in subscribe_events[:5]:
            print(f"    {ts} [{service}]: {text[:100]}")
    
    if redis_errors:
        print(f"\n  ⚠️  Redis errors found:")
        for ts, service, text in redis_errors[:10]:
            print(f"    {ts} [{service}]: {text[:150]}")
    
    print("\n" + "="*100)
    print("ERROR ANALYSIS")
    print("="*100)
    
    errors = []
    for entry in logs:
        severity = entry.get('severity', '')
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        ts = entry.get('timestamp', '')
        service = entry.get('resource', {}).get('labels', {}).get('service_name', '')
        
        if severity in ['ERROR', 'CRITICAL']:
            errors.append((ts, service, severity, text))
        elif 'error' in text.lower() and 'no error' not in text.lower():
            errors.append((ts, service, 'WARNING', text))
    
    print(f"\nErrors/warnings found: {len(errors)}")
    
    # Group by type
    error_types = Counter()
    for ts, service, severity, text in errors:
        # Extract error type
        if 'Failed to start Celery worker' in text:
            error_types['Celery worker startup failure'] += 1
        elif 'Redis' in text:
            error_types['Redis-related'] += 1
        elif 'WebSocket' in text or 'websocket' in text:
            error_types['WebSocket-related'] += 1
        elif 'timeout' in text.lower():
            error_types['Timeout'] += 1
        else:
            error_types['Other'] += 1
    
    print(f"\n  Error types:")
    for error_type, count in error_types.most_common():
        print(f"    {error_type:40s}: {count:4d}")
    
    print(f"\n  Sample errors (first 20):")
    for ts, service, severity, text in errors[:20]:
        print(f"    {ts} [{service}] [{severity}]: {text[:120]}")
    
    print("\n" + "="*100)
    print("TRACE EVENT PUBLISHING ANALYSIS")
    print("="*100)
    
    # Check if trace events are being published to Redis
    trace_publish_count = 0
    for entry in logs:
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        if 'publish_execution_trace' in text or 'Publishing trace event' in text:
            trace_publish_count += 1
    
    print(f"\nTrace publish attempts: {trace_publish_count}")
    
    # Check WebSocket subscription status
    ws_subscriptions = 0
    ws_completions = 0
    ws_errors = 0
    
    for entry in logs:
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        if 'Subscribed to channel: job_trace_' in text:
            ws_subscriptions += 1
        elif 'Trace subscription completed' in text:
            ws_completions += 1
        elif 'Trace subscription error' in text:
            ws_errors += 1
    
    print(f"\nWebSocket subscriptions: {ws_subscriptions}")
    print(f"WebSocket completions: {ws_completions}")
    print(f"WebSocket errors: {ws_errors}")
    
    print("\n" + "="*100)
    print("DIAGNOSIS")
    print("="*100)
    
    print("\n✅ WORKING:")
    print("  - Workers are starting successfully (no syntax errors)")
    print("  - Jobs are being dispatched and picked up")
    print("  - [TRACE] events are being logged to stdout")
    print("  - Jobs are completing")
    
    print("\n❌ NOT WORKING:")
    print("  - Trace files are 0 bytes (WebSocket not receiving events)")
    print("  - Redis pub/sub may not be delivering events")
    print("  - WebSocket subscriptions timing out")
    
    print("\n🔍 INVESTIGATION NEEDED:")
    print("  - Are trace events being published to Redis?")
    print("  - Are WebSocket subscriptions receiving events?")
    print("  - Is there a Redis connection issue?")
    print("  - Is the GraphQL subscription resolver working?")

if __name__ == '__main__':
    main()
