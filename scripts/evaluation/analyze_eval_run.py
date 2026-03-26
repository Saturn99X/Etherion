#!/usr/bin/env python3
"""Analyze evaluation run from Cloud Run logs."""

import json
import sys
from datetime import datetime
from collections import defaultdict

# Job IDs from state.json
JOB_IDS = [
    "job_3y-g2A5ICiqTFzvX",  # Q1
    "job_TuBwm8A_KCMbxpSk",  # Q2
    "job_S-A3DzS8yFB-TtDC",  # Q3
    "job_SSY5aB-paa94PMz-",  # Q4
    "job_A9GP67utiAboLbnH",  # Q5
    "job_wJZkx0kQke3GRu8X",  # Q6
    "job_iHRmICrROCIv8fTq",  # Q7
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

def main():
    with open('/tmp/eval_run_jan16_logs.json', 'r') as f:
        logs = json.load(f)
    
    print(f"Total log entries: {len(logs)}")
    print()
    
    # Group logs by job_id
    job_logs = defaultdict(list)
    api_logs = []
    worker_logs = []
    
    for entry in logs:
        text = entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', '')
        service = entry.get('resource', {}).get('labels', {}).get('service_name', '')
        timestamp = entry.get('timestamp', '')
        
        # Categorize by service
        if 'api' in service:
            api_logs.append((timestamp, text))
        elif 'worker' in service:
            worker_logs.append((timestamp, text))
        
        # Find job_id in text
        for job_id in JOB_IDS:
            if job_id in str(text):
                job_logs[job_id].append({
                    'timestamp': timestamp,
                    'service': service,
                    'text': text
                })
    
    print("="*80)
    print("JOB ANALYSIS")
    print("="*80)
    
    for idx, job_id in enumerate(JOB_IDS, 1):
        logs_for_job = job_logs.get(job_id, [])
        print(f"\nQ{idx}: {QUESTIONS[idx-1][:80]}...")
        print(f"Job ID: {job_id}")
        print(f"Log entries: {len(logs_for_job)}")
        
        if not logs_for_job:
            print("  ❌ NO LOGS FOUND - Job may not have executed")
            continue
        
        # Find key events
        events = []
        for log in logs_for_job:
            text = str(log['text'])
            ts = log['timestamp']
            
            if 'Dispatched orchestration to Celery' in text:
                events.append(('DISPATCHED', ts))
            elif 'Starting goal orchestration' in text:
                events.append(('WORKER_START', ts))
            elif 'Completed goal orchestration' in text:
                events.append(('WORKER_END', ts))
            elif 'DUAL_SEARCH_START' in text or 'Starting Dual Search' in text:
                events.append(('DUAL_SEARCH_START', ts))
            elif 'DUAL_SEARCH_END' in text or 'Dual Search completed' in text:
                events.append(('DUAL_SEARCH_END', ts))
            elif 'TEAM_LOAD' in text:
                events.append(('TEAM_LOAD', ts))
            elif 'THINK_START' in text:
                events.append(('THINK_START', ts))
            elif 'ACT_START' in text:
                events.append(('ACT_START', ts))
            elif 'TOOL_START' in text:
                events.append(('TOOL_START', ts))
            elif 'SPECIALIST_REQUEST' in text:
                events.append(('SPECIALIST_REQUEST', ts))
            elif 'execution_trace_end' in text or 'END' in text:
                events.append(('END', ts))
        
        if events:
            print(f"  Timeline:")
            start_time = None
            for event_type, ts in events:
                dt = parse_timestamp(ts)
                if start_time is None:
                    start_time = dt
                    elapsed = "0.0s"
                else:
                    elapsed = f"{(dt - start_time).total_seconds():.1f}s"
                print(f"    {ts} (+{elapsed:>8}) - {event_type}")
            
            # Calculate total duration
            if len(events) >= 2:
                start_dt = parse_timestamp(events[0][1])
                end_dt = parse_timestamp(events[-1][1])
                if start_dt and end_dt:
                    duration = (end_dt - start_dt).total_seconds()
                    print(f"  Total duration: {duration:.1f}s ({duration/60:.1f}m)")
        else:
            print("  ⚠️  No key events found in logs")
    
    print("\n" + "="*80)
    print("REDIS/WEBSOCKET ANALYSIS")
    print("="*80)
    
    redis_events = []
    for entry in logs:
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        ts = entry.get('timestamp', '')
        
        if 'Subscribed to channel: job_trace_' in text:
            redis_events.append(('SUBSCRIBE', ts, text))
        elif 'publish_execution_trace' in text:
            redis_events.append(('PUBLISH', ts, text))
        elif 'Redis' in text and 'error' in text.lower():
            redis_events.append(('REDIS_ERROR', ts, text))
    
    print(f"\nRedis events found: {len(redis_events)}")
    for event_type, ts, text in redis_events[:20]:  # Show first 20
        print(f"  {ts} - {event_type}: {text[:100]}")
    
    print("\n" + "="*80)
    print("ERROR ANALYSIS")
    print("="*80)
    
    errors = []
    for entry in logs:
        severity = entry.get('severity', '')
        text = str(entry.get('textPayload', '') or entry.get('jsonPayload', {}).get('message', ''))
        ts = entry.get('timestamp', '')
        
        if severity in ['ERROR', 'CRITICAL'] or 'error' in text.lower() or 'fail' in text.lower():
            errors.append((ts, severity, text))
    
    print(f"\nErrors/warnings found: {len(errors)}")
    for ts, severity, text in errors[:30]:  # Show first 30
        print(f"  {ts} [{severity}]: {text[:150]}")

if __name__ == '__main__':
    main()
