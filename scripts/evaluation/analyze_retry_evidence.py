#!/usr/bin/env python3
"""
Analyze retry wrapper evidence in Jan 17 evening evaluation run.

This script specifically looks for:
1. Multiple SPECIALIST_INVOKE events for the same specialist
2. Time gaps between invocations (retry delays)
3. Success/failure patterns
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp."""
    return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))


def analyze_retries_in_trace(filepath: Path) -> Dict[str, Any]:
    """Analyze retry patterns in a single trace file."""
    events = []
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except Exception as e:
        return {"error": str(e), "filepath": str(filepath)}
    
    # Group SPECIALIST_INVOKE events by specialist_id
    specialist_invocations = defaultdict(list)
    specialist_responses = {}
    
    for event in events:
        event_type = event.get("type") or event.get("status")
        
        if event_type == "SPECIALIST_INVOKE":
            agent_id = event.get("agent_id") or event.get("additional_data", {}).get("agent_id")
            if agent_id:
                specialist_invocations[agent_id].append(event)
        
        elif event_type == "SPECIALIST_RESPONSE":
            spec_id = event.get("specialist_id") or event.get("additional_data", {}).get("specialist_id")
            if spec_id:
                specialist_responses[spec_id] = event
    
    # Analyze retry patterns
    retry_patterns = []
    
    for agent_id, invocations in specialist_invocations.items():
        if len(invocations) > 1:
            # Multiple invocations = retry detected!
            timestamps = []
            for inv in invocations:
                ts_str = inv.get("timestamp") or inv.get("additional_data", {}).get("timestamp")
                if ts_str:
                    timestamps.append(parse_timestamp(ts_str))
            
            # Calculate delays between attempts
            delays = []
            for i in range(1, len(timestamps)):
                delay = (timestamps[i] - timestamps[i-1]).total_seconds()
                delays.append(delay)
            
            # Get response info
            response = specialist_responses.get(agent_id, {})
            output_preview = response.get("additional_data", {}).get("output_preview", {})
            output_text = str(output_preview.get("output", ""))
            
            retry_patterns.append({
                "agent_id": agent_id,
                "total_attempts": len(invocations),
                "timestamps": [ts.isoformat() for ts in timestamps],
                "delays_seconds": delays,
                "final_output_length": len(output_text),
                "success": response.get("additional_data", {}).get("success", False)
            })
    
    return {
        "filepath": str(filepath),
        "total_specialists": len(specialist_invocations),
        "specialists_with_retries": len(retry_patterns),
        "retry_patterns": retry_patterns
    }


def main():
    """Analyze all recent trace files for retry evidence."""
    
    print("=" * 80)
    print("RETRY WRAPPER EVIDENCE ANALYSIS")
    print("=" * 80)
    print("\nLooking for multiple SPECIALIST_INVOKE events (retry pattern)...")
    print()
    
    # Find most recent 7 trace files
    trace_dir = project_root / "scripts" / "evaluation" / "out" / "physics_team_questions"
    all_traces = sorted(trace_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    recent_traces = []
    questions_seen = set()
    
    for trace in all_traces:
        question_num = trace.name.split("_")[0]
        if question_num not in questions_seen:
            questions_seen.add(question_num)
            recent_traces.append(trace)
            if len(recent_traces) == 7:
                break
    
    recent_traces = sorted(recent_traces, key=lambda p: p.name)
    
    # Analyze each trace
    all_retry_patterns = []
    total_retries_detected = 0
    
    for trace in recent_traces:
        result = analyze_retries_in_trace(trace)
        
        if "error" in result:
            print(f"✗ {trace.name}: ERROR - {result['error']}")
            continue
        
        question_num = trace.name.split("_")[0]
        retries = result["specialists_with_retries"]
        
        if retries > 0:
            print(f"✓ {question_num}: {retries} specialist(s) with retry detected")
            total_retries_detected += retries
            
            for pattern in result["retry_patterns"]:
                all_retry_patterns.append({
                    "question": question_num,
                    "file": trace.name,
                    **pattern
                })
                
                print(f"    Agent: {pattern['agent_id']}")
                print(f"    Attempts: {pattern['total_attempts']}")
                print(f"    Delays: {[f'{d:.1f}s' for d in pattern['delays_seconds']]}")
                print(f"    Final output length: {pattern['final_output_length']} chars")
                print(f"    Success: {pattern['success']}")
                print()
        else:
            print(f"  {question_num}: No retries detected")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print(f"\nTotal questions analyzed: {len(recent_traces)}")
    print(f"Questions with retries: {len([r for r in all_retry_patterns if r])} ")
    print(f"Total retry events detected: {total_retries_detected}")
    
    if all_retry_patterns:
        print(f"\n✓ RETRY WRAPPER IS ACTIVE!")
        print(f"\nDetailed Retry Patterns:")
        
        for pattern in all_retry_patterns:
            print(f"\n  {pattern['question']} - {pattern['agent_id']}:")
            print(f"    Total attempts: {pattern['total_attempts']}")
            print(f"    Retry delays: {', '.join([f'{d:.1f}s' for d in pattern['delays_seconds']])}")
            print(f"    Final output: {pattern['final_output_length']} chars")
            print(f"    Success: {pattern['success']}")
        
        # Analyze delay patterns
        all_delays = []
        for pattern in all_retry_patterns:
            all_delays.extend(pattern['delays_seconds'])
        
        if all_delays:
            print(f"\nRetry Delay Statistics:")
            print(f"  Min delay: {min(all_delays):.1f}s")
            print(f"  Max delay: {max(all_delays):.1f}s")
            print(f"  Avg delay: {sum(all_delays)/len(all_delays):.1f}s")
            print(f"  Total delays: {all_delays}")
            
            # Check if delays match expected exponential backoff (1s, 2s, 4s, 8s)
            expected_pattern = [1.0, 2.0, 4.0, 8.0]
            print(f"\n  Expected pattern (exponential backoff): {expected_pattern}")
            print(f"  Actual delays: {[f'{d:.1f}s' for d in all_delays]}")
            
            # Check if delays are roughly exponential
            if len(all_delays) >= 2:
                ratios = [all_delays[i] / all_delays[i-1] for i in range(1, len(all_delays))]
                avg_ratio = sum(ratios) / len(ratios)
                print(f"  Delay ratio (should be ~2.0 for exponential): {avg_ratio:.2f}")
    else:
        print(f"\n⚠️  NO RETRY PATTERNS DETECTED")
        print(f"   This could mean:")
        print(f"   1. All specialists succeeded on first attempt (good!)")
        print(f"   2. Retry wrapper is not active (needs investigation)")
        print(f"   3. Trace format changed (needs investigation)")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
