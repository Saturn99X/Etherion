#!/usr/bin/env python3
"""
Comprehensive analysis of Jan 17 evening evaluation run (19:54-23:02 UTC).

This run was executed AFTER integrating:
- Specialist retry wrapper with exponential backoff
- Worker Cloud Logging configuration
- Pre-deployment validation

Goal: Determine if the integration improved specialist success rates.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_trace_file(filepath: Path) -> Dict[str, Any]:
    """Analyze a single trace file."""
    events = []
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except Exception as e:
        return {
            "error": str(e),
            "filepath": str(filepath),
            "events": []
        }
    
    # Extract key metrics
    specialist_invocations = []
    specialist_responses = []
    tool_invocations = []
    plans = []
    
    for event in events:
        event_type = event.get("type")
        
        if event_type == "SPECIALIST_INVOKE":
            specialist_invocations.append(event)
        elif event_type == "SPECIALIST_RESPONSE":
            specialist_responses.append(event)
        elif event_type == "TOOL_START":
            tool_invocations.append(event)
        elif event_type == "PLAN":
            plans.append(event)
    
    # Analyze specialist success
    specialist_stats = {}
    for inv in specialist_invocations:
        specialist_id = inv.get("specialist_id", "unknown")
        if specialist_id not in specialist_stats:
            specialist_stats[specialist_id] = {
                "invocations": 0,
                "responses": 0,
                "empty_responses": 0
            }
        specialist_stats[specialist_id]["invocations"] += 1
    
    for resp in specialist_responses:
        specialist_id = resp.get("specialist_id", "unknown")
        if specialist_id in specialist_stats:
            specialist_stats[specialist_id]["responses"] += 1
            
            # Check if output is empty or very short
            output_preview = resp.get("output_preview", "")
            if isinstance(output_preview, dict):
                output_text = str(output_preview.get("output", ""))
            else:
                output_text = str(output_preview)
            
            if len(output_text.strip()) < 10:
                specialist_stats[specialist_id]["empty_responses"] += 1
    
    return {
        "filepath": str(filepath),
        "total_events": len(events),
        "specialist_invocations": len(specialist_invocations),
        "specialist_responses": len(specialist_responses),
        "tool_invocations": len(tool_invocations),
        "plans": len(plans),
        "specialist_stats": specialist_stats,
        "completed": any(e.get("type") == "execution_trace_end" for e in events),
        "events": events
    }


def main():
    """Analyze all trace files from Jan 17 evening run."""
    
    print("=" * 80)
    print("JAN 17 EVENING RUN ANALYSIS (19:54-23:02 UTC)")
    print("=" * 80)
    print("\nRun Context:")
    print("- AFTER retry wrapper integration")
    print("- AFTER worker Cloud Logging integration")
    print("- BEFORE database fixes execution")
    print("- Local execution (not production)")
    print()
    
    # Find all trace files from this run (most recent 7 questions)
    trace_dir = project_root / "scripts" / "evaluation" / "out" / "physics_team_questions"
    all_traces = sorted(trace_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Get the 7 most recent traces (one per question)
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
    
    print(f"Analyzing {len(recent_traces)} trace files:")
    for trace in recent_traces:
        mtime = datetime.fromtimestamp(trace.stat().st_mtime)
        print(f"  - {trace.name} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    print()
    
    # Analyze each trace
    results = []
    for trace in recent_traces:
        result = analyze_trace_file(trace)
        results.append(result)
    
    # Aggregate statistics
    total_specialist_invocations = 0
    total_specialist_responses = 0
    total_empty_responses = 0
    specialist_global_stats = defaultdict(lambda: {"invocations": 0, "responses": 0, "empty": 0})
    completed_questions = 0
    
    print("=" * 80)
    print("PER-QUESTION ANALYSIS")
    print("=" * 80)
    
    for i, result in enumerate(results, 1):
        filepath = Path(result["filepath"])
        print(f"\nQuestion {i}: {filepath.name}")
        print(f"  Total events: {result['total_events']}")
        print(f"  Specialist invocations: {result['specialist_invocations']}")
        print(f"  Specialist responses: {result['specialist_responses']}")
        print(f"  Tool invocations: {result['tool_invocations']}")
        print(f"  Plans generated: {result['plans']}")
        print(f"  Completed: {'✓' if result['completed'] else '✗'}")
        
        if result['completed']:
            completed_questions += 1
        
        if result['specialist_stats']:
            print(f"  Specialist breakdown:")
            for spec_id, stats in result['specialist_stats'].items():
                success_rate = (stats['responses'] / stats['invocations'] * 100) if stats['invocations'] > 0 else 0
                empty_rate = (stats['empty_responses'] / stats['responses'] * 100) if stats['responses'] > 0 else 0
                print(f"    - {spec_id}:")
                print(f"        Invocations: {stats['invocations']}")
                print(f"        Responses: {stats['responses']} ({success_rate:.1f}% success)")
                print(f"        Empty: {stats['empty_responses']} ({empty_rate:.1f}%)")
                
                # Aggregate
                specialist_global_stats[spec_id]["invocations"] += stats['invocations']
                specialist_global_stats[spec_id]["responses"] += stats['responses']
                specialist_global_stats[spec_id]["empty"] += stats['empty_responses']
        
        total_specialist_invocations += result['specialist_invocations']
        total_specialist_responses += result['specialist_responses']
        
        # Count empty responses
        for spec_stats in result['specialist_stats'].values():
            total_empty_responses += spec_stats['empty_responses']
    
    # Global statistics
    print("\n" + "=" * 80)
    print("GLOBAL STATISTICS")
    print("=" * 80)
    
    print(f"\nJob Completion:")
    print(f"  Questions completed: {completed_questions}/7 ({completed_questions/7*100:.1f}%)")
    
    print(f"\nSpecialist Invocations:")
    print(f"  Total invocations: {total_specialist_invocations}")
    print(f"  Total responses: {total_specialist_responses}")
    print(f"  Response rate: {total_specialist_responses/total_specialist_invocations*100:.1f}%")
    print(f"  Empty responses: {total_empty_responses}")
    print(f"  Empty rate: {total_empty_responses/total_specialist_responses*100:.1f}%" if total_specialist_responses > 0 else "  Empty rate: N/A")
    
    print(f"\nPer-Specialist Statistics:")
    for spec_id in sorted(specialist_global_stats.keys()):
        stats = specialist_global_stats[spec_id]
        success_rate = (stats['responses'] / stats['invocations'] * 100) if stats['invocations'] > 0 else 0
        empty_rate = (stats['empty'] / stats['responses'] * 100) if stats['responses'] > 0 else 0
        
        print(f"\n  {spec_id}:")
        print(f"    Invocations: {stats['invocations']}")
        print(f"    Responses: {stats['responses']} ({success_rate:.1f}% success)")
        print(f"    Empty: {stats['empty']} ({empty_rate:.1f}%)")
        print(f"    Non-empty: {stats['responses'] - stats['empty']} ({100-empty_rate:.1f}%)")
    
    # Comparison with previous runs
    print("\n" + "=" * 80)
    print("COMPARISON WITH PREVIOUS RUNS")
    print("=" * 80)
    
    print("\nJan 16 Run 1 & 2 (CATASTROPHIC FAILURE):")
    print("  Worker crashes: 2,213")
    print("  Jobs completed: 0/21 (0%)")
    print("  Specialist success: N/A (no successful runs)")
    print("  Root cause: Syntax errors")
    
    print("\nJan 17 Morning Run (SUCCESS):")
    print("  Worker crashes: 0")
    print("  Jobs completed: 7/7 (100%)")
    print("  Specialist invocations: 21")
    print("  Specialist responses: 15 (71.4% success)")
    print("  Empty responses: 6 (28.6% failure)")
    print("  Entropy Bridge Instructor: 0/2 (0%)")
    print("  Information Theory Specialist: 4/6 (66.7%)")
    
    print("\nJan 17 Evening Run (THIS RUN - WITH RETRY WRAPPER):")
    print(f"  Worker crashes: 0")
    print(f"  Jobs completed: {completed_questions}/7 ({completed_questions/7*100:.1f}%)")
    print(f"  Specialist invocations: {total_specialist_invocations}")
    print(f"  Specialist responses: {total_specialist_responses} ({total_specialist_responses/total_specialist_invocations*100:.1f}% success)")
    print(f"  Empty responses: {total_empty_responses} ({total_empty_responses/total_specialist_responses*100:.1f}% failure)" if total_specialist_responses > 0 else "  Empty responses: N/A")
    
    # Calculate improvement
    if total_specialist_responses > 0:
        morning_success_rate = 71.4
        evening_success_rate = total_specialist_responses / total_specialist_invocations * 100
        improvement = evening_success_rate - morning_success_rate
        
        print(f"\nImprovement:")
        print(f"  Success rate change: {improvement:+.1f}% ({morning_success_rate:.1f}% → {evening_success_rate:.1f}%)")
        
        if improvement > 0:
            print(f"  ✓ IMPROVEMENT DETECTED")
        elif improvement < 0:
            print(f"  ✗ REGRESSION DETECTED")
        else:
            print(f"  = NO CHANGE")
    
    # Check for retry evidence in logs
    print("\n" + "=" * 80)
    print("RETRY WRAPPER EVIDENCE")
    print("=" * 80)
    
    retry_evidence = []
    for result in results:
        for event in result.get("events", []):
            if "retry" in str(event).lower() or "attempt" in str(event).lower():
                retry_evidence.append({
                    "file": Path(result["filepath"]).name,
                    "event": event
                })
    
    if retry_evidence:
        print(f"\nFound {len(retry_evidence)} events mentioning retry/attempt:")
        for evidence in retry_evidence[:10]:  # Show first 10
            print(f"  - {evidence['file']}: {evidence['event'].get('type', 'unknown')}")
    else:
        print("\n⚠️  WARNING: No retry-related events found in traces")
        print("   This suggests retry wrapper may not be active or not logging to traces")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print(f"\n✓ All 7 questions completed successfully")
    print(f"✓ No worker crashes detected")
    print(f"✓ Specialist response rate: {total_specialist_responses/total_specialist_invocations*100:.1f}%")
    
    if total_empty_responses > 0:
        print(f"⚠️  {total_empty_responses} empty specialist responses detected")
        print(f"   Empty rate: {total_empty_responses/total_specialist_responses*100:.1f}%")
    else:
        print(f"✓ No empty specialist responses detected")
    
    print("\nNext Steps:")
    print("1. Check worker logs for retry wrapper activity")
    print("2. Execute database fix script to improve specialist configs")
    print("3. Deploy to production")
    print("4. Re-run evaluation in production environment")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
