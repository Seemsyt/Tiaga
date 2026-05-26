#!/usr/bin/env python3
"""
Benchmark tool to measure performance bottlenecks in Tiaga.

Measures:
1. Planner LLM call time
2. Executor LLM call time  
3. Tool execution time
4. Total request latency
"""

import asyncio
import time
import sys
from pathlib import Path
from tiaga.config.loader import load_config
from tiaga.agent.agent import Agent
from tiaga.agent.events import AgentEventType

async def main():
    print("=" * 70)
    print("TIAGA PERFORMANCE BENCHMARK")
    print("=" * 70)
    
    # Load config
    config = load_config(Path.cwd())
    print(f"\n📋 Configuration:")
    print(f"   Model: {config.model_name or 'NOT SET'}")
    print(f"   API Key: {'SET' if config.api_key else 'NOT SET'}")
    print(f"   Base URL: {config.base_url or 'NOT SET'}")
    print(f"   Cwd: {config.cwd}")
    
    if not config.api_key or config.api_key == "set_api_key":
        print("\n❌ ERROR: API_KEY not set!")
        print("   Set it with: export TIAGA_API_KEY='your-key'")
        return
    
    if not config.base_url or config.base_url == "set_base_url":
        print("\n❌ ERROR: BASE_URL not set!")
        print("   Set it with: export TIAGA_BASE_URL='https://api.example.com/v1'")
        return
    
    if not config.model_name:
        print("\n❌ ERROR: Model not set!")
        print("   Set it in config or: /model modelname")
        return
    
    print("\n" + "=" * 70)
    print("STARTING BENCHMARK...")
    print("=" * 70)
    
    # Simple test request
    test_prompt = "Create a simple HTML file that displays 'read an any python file ' centered on the page."
    
    print(f"\n📝 Test Prompt: {test_prompt}\n")
    
    async with Agent(config) as agent:
        start_time = time.time()
        planner_time = None
        first_tool_time = None
        executor_time = None
        
        event_times = {}
        phase = "planning"
        
        async for event in agent.run(test_prompt):
            elapsed = time.time() - start_time
            event_type = event.type
            
            print(f"[{elapsed:6.2f}s] {event_type.value:20} → {phase}")
            
            # Track phase transitions
            if event_type == AgentEventType.AGENT_START:
                phase = "planning"
                event_times["agent_start"] = elapsed
                
            elif event_type == AgentEventType.PLAN:
                planner_time = elapsed
                phase = "tool_execution"
                event_times["plan"] = elapsed
                steps = event.data.get("steps", [])
                print(f"             └─ Plan has {len(steps)} steps")
                
            elif event_type == AgentEventType.TOOL_CALL_START:
                if first_tool_time is None:
                    first_tool_time = elapsed
                tool_name = event.data.get("name", "unknown")
                print(f"             └─ Tool: {tool_name}")
                
            elif event_type == AgentEventType.TOOL_CALL_END:
                tool_name = event.data.get("name", "unknown")
                success = event.data.get("success", False)
                status = "✓" if success else "✗"
                print(f"             └─ {status} {tool_name} complete")
                
            elif event_type == AgentEventType.TEXT_DELTA:
                phase = "generation"
                executor_time = executor_time or elapsed
                
            elif event_type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                detail = event.data.get("detail", "")
                print(f"             └─ ERROR: {error}")
                if detail:
                    print(f"             └─ DETAIL: {detail}")
                    
            elif event_type == AgentEventType.AGENT_END:
                total_time = elapsed
                event_times["agent_end"] = elapsed
        
        # Print summary
        print("\n" + "=" * 70)
        print("BENCHMARK RESULTS")
        print("=" * 70)
        
        if planner_time is not None:
            print(f"⏱️  Planner (Planning) took: {planner_time:.2f} seconds")
        
        if first_tool_time is not None and planner_time is not None:
            tool_phase = first_tool_time - planner_time
            print(f"⏱️  Tool Execution phase took: {tool_phase:.2f} seconds")
        
        if executor_time is not None and first_tool_time is not None:
            gen_phase = executor_time - first_tool_time
            print(f"⏱️  Generation phase took: {gen_phase:.2f} seconds")
        
        print(f"⏱️  Total time: {total_time:.2f} seconds")
        
        # Analysis
        print("\n" + "=" * 70)
        print("ANALYSIS")
        print("=" * 70)
        
        if planner_time and planner_time > 10:
            print("⚠️  SLOW PLANNER: Planning took > 10s")
            print("   → This is likely a WEAK LLM MODEL or HIGH API LATENCY")
            print("   → Try a faster model (not a free tier model)")
        
        if executor_time and (total_time - executor_time) > 20:
            print("⚠️  SLOW EXECUTOR: Generation took > 20s after planning")
            print("   → This is a WEAK LLM MODEL generating code too slowly")
            print("   → Try a faster/stronger model")
        
        if total_time > 30:
            print("⚠️  SLOW OVERALL: Total took > 30 seconds")
            print("   → Root cause: Check which phase took longest above ↑")

if __name__ == "__main__":
    asyncio.run(main())
